/**
 * One local-notification scheduler, shared by domains (PRD 12, sections 34, 62).
 *
 * Section 62 asks for the notification service to be extended into a shared
 * scheduler with domain-specific wrappers, and -- in the same breath -- says
 * not to destabilise medication reminders while generalising. Both halves are
 * honoured literally:
 *
 * **This module is the shared engine.** Permission, the Android channel, the
 * stored map from source id to notification id, and the reconcile-to-plan
 * algorithm all live here once. A domain supplies a `Domain` describing where
 * its map is stored and which channel it posts to, plus a list of planned
 * notifications; the engine makes the operating system agree with that list.
 *
 * **PRD 5's and PRD 7's reminders were not migrated.** They work, they are
 * tested, and section 62's warning is about exactly this kind of change. They
 * keep their own copies of the machinery, and this engine is what PRD 12's
 * three domains use. Moving them across is a later PRD's job, deliberately
 * left undone rather than done carelessly -- and
 * `docs/architecture/daily-life-assistant.md` says so.
 *
 * **These are OS-scheduled local notifications, and nothing else.** The
 * JavaScript process is not running most of the time, so anything that
 * depended on it would simply not fire. The backend stays the source of truth;
 * this file's whole job is to mirror the next fortnight into the operating
 * system's own scheduler and keep that mirror honest.
 *
 * **Nothing here has ever fired on a physical phone.** The app has never been
 * run on a handset. Every test of this file is a recording stub, which is what
 * section 69 asks for and the most it can prove: *do not claim OS delivery.*
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';

import { createLogger } from '../../utils/logger';

const log = createLogger('notifications');

/**
 * iOS keeps at most 64 pending local notifications per app and silently drops
 * the rest. Medication reminders already claim up to 48 and appointments 12,
 * which leaves very little -- so the daily-life domains take a small share
 * each and the caps live on the domain rather than here.
 */
export interface Domain {
  /** Where this domain's source-id-to-notification-id map is kept. */
  storageKey: string;
  /** The Android channel. One per domain, so nothing is announced twice. */
  channelId: string;
  channelName: string;
  /** How many pending notifications this domain may hold. */
  max: number;
  /**
   * How noticeable the channel is. `high` for something time-critical; the
   * default for an ordinary reminder, which should be noticeable without
   * being an alarm.
   */
  importance?: 'default' | 'high';
}

/** One notification a domain wants the operating system to hold. */
export interface Planned {
  /**
   * A stable id for the thing this is about -- a reminder occurrence's id, or
   * an alarm plus the instant it is for. Section 34 asks for source ids to be
   * mapped to notification ids, and this is that id.
   */
  key: string;
  /** ISO instant it should fire. */
  fireAt: string;
  title: string;
  body: string;
  /** Carried on the notification so a tap handler can open the right row. */
  data?: Record<string, string>;
}

/** One the operating system has accepted, and the id needed to cancel it. */
export interface Scheduled {
  key: string;
  notificationId: string;
  fireAt: string;
}

export interface Reconciliation {
  toCancel: Scheduled[];
  toSchedule: Planned[];
  toKeep: Scheduled[];
}

// --- planning (pure) --------------------------------------------------------

/**
 * The smallest set of changes that makes the operating system agree with the
 * plan.
 *
 * Notifications whose key *and* time are unchanged are left alone rather than
 * cancelled and re-created, so an app that is opened five times in an hour
 * does not churn the tray. Anything whose time moved -- or whose source is no
 * longer waiting -- is cancelled.
 *
 * **This is what makes section 34's "retries must not duplicate" true.**
 * Reconciliation is idempotent: running it twice with the same plan schedules
 * nothing the second time, because the first run's entries match.
 */
export function reconcile(existing: Scheduled[], planned: Planned[]): Reconciliation {
  const wanted = new Map(planned.map((entry) => [entry.key, entry]));
  const toKeep: Scheduled[] = [];
  const toCancel: Scheduled[] = [];

  for (const entry of existing) {
    const match = wanted.get(entry.key);
    if (match !== undefined && match.fireAt === entry.fireAt) {
      toKeep.push(entry);
      wanted.delete(entry.key);
    } else {
      toCancel.push(entry);
    }
  }

  return { toCancel, toSchedule: Array.from(wanted.values()), toKeep };
}

/**
 * The notifications worth holding, soonest first and capped.
 *
 * Only ones in the future: an entry whose moment has gone has nothing left to
 * announce, and scheduling it would fire immediately.
 */
export function upcoming(planned: Planned[], now: Date, max: number): Planned[] {
  const from = now.getTime();
  return planned
    .filter((entry) => {
      const at = new Date(entry.fireAt).getTime();
      return Number.isFinite(at) && at > from;
    })
    .sort((left, right) => left.fireAt.localeCompare(right.fireAt))
    .slice(0, max);
}

// --- the OS side ------------------------------------------------------------

export async function loadScheduled(domain: Domain): Promise<Scheduled[]> {
  try {
    const raw = await AsyncStorage.getItem(domain.storageKey);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // Entries from an older build, or corrupted ones, are dropped rather than
    // allowed to crash the screen that reads them.
    return parsed.filter(
      (entry): entry is Scheduled =>
        entry !== null &&
        typeof entry === 'object' &&
        typeof (entry as Scheduled).key === 'string' &&
        typeof (entry as Scheduled).notificationId === 'string' &&
        typeof (entry as Scheduled).fireAt === 'string'
    );
  } catch {
    return [];
  }
}

async function saveScheduled(domain: Domain, entries: Scheduled[]): Promise<void> {
  if (entries.length === 0) {
    await AsyncStorage.removeItem(domain.storageKey);
    return;
  }
  await AsyncStorage.setItem(domain.storageKey, JSON.stringify(entries));
}

/**
 * Asks for notification permission -- and only ever when called.
 *
 * PRD 5 section 14's rule, which PRD 12 inherits: this is requested when
 * somebody turns reminders on, not at launch and not during onboarding, so the
 * prompt arrives with an obvious reason attached.
 */
export async function requestPermission(): Promise<boolean> {
  try {
    const current = await Notifications.getPermissionsAsync();
    if (current.granted) return true;
    if (!current.canAskAgain) return false;
    const asked = await Notifications.requestPermissionsAsync();
    return asked.granted;
  } catch {
    // A platform that cannot answer is treated as "no". The reminder is still
    // saved on the server, and the app still shows what is due (section 9).
    return false;
  }
}

export async function hasPermission(): Promise<boolean> {
  try {
    return (await Notifications.getPermissionsAsync()).granted;
  } catch {
    return false;
  }
}

async function ensureChannel(domain: Domain): Promise<void> {
  if (Platform.OS !== 'android') return;
  try {
    await Notifications.setNotificationChannelAsync(domain.channelId, {
      name: domain.channelName,
      importance:
        domain.importance === 'high'
          ? Notifications.AndroidImportance.HIGH
          : Notifications.AndroidImportance.DEFAULT,
      vibrationPattern: [0, 250],
      enableVibrate: true,
    });
  } catch {
    // Channel setup failing is not worth blocking a reminder over; the OS
    // falls back to a default channel.
  }
}

async function scheduleOne(domain: Domain, entry: Planned): Promise<string | null> {
  try {
    return await Notifications.scheduleNotificationAsync({
      content: {
        title: entry.title,
        body: entry.body,
        data: { key: entry.key, ...entry.data },
      },
      trigger: {
        type: Notifications.SchedulableTriggerInputTypes.DATE,
        date: new Date(entry.fireAt),
        channelId: domain.channelId,
      },
    });
  } catch {
    return null;
  }
}

async function cancelOne(notificationId: string): Promise<void> {
  try {
    await Notifications.cancelScheduledNotificationAsync(notificationId);
  } catch {
    // Already gone, or the OS forgot it. Either way there is nothing to do.
  }
}

export interface RebuildResult {
  scheduled: number;
  /** False when the operating system has refused. Section 9's case. */
  permitted: boolean;
  cancelled: number;
  added: number;
}

/**
 * Makes the phone's pending notifications for one domain match a plan.
 *
 * The single entry point section 34 asks for: called on app start and resume,
 * and after anything that could change what is due. Being idempotent is what
 * lets it be called that freely.
 *
 * Does nothing at all without permission, and says so in the return value, so
 * a screen can tell somebody their reminders are saved but silent rather than
 * pretending they will fire (section 9).
 */
export async function rebuild(
  domain: Domain,
  planned: Planned[],
  options: { now?: Date } = {}
): Promise<RebuildResult> {
  if (!(await hasPermission())) {
    return { scheduled: 0, permitted: false, cancelled: 0, added: 0 };
  }

  await ensureChannel(domain);

  const existing = await loadScheduled(domain);
  const wanted = upcoming(planned, options.now ?? new Date(), domain.max);
  const { toCancel, toSchedule, toKeep } = reconcile(existing, wanted);

  for (const entry of toCancel) {
    await cancelOne(entry.notificationId);
  }

  const added: Scheduled[] = [];
  for (const entry of toSchedule) {
    const notificationId = await scheduleOne(domain, entry);
    if (notificationId !== null) {
      added.push({ key: entry.key, notificationId, fireAt: entry.fireAt });
    }
  }

  const next = [...toKeep, ...added];
  await saveScheduled(domain, next);
  // Counts only -- never a title, a time or a source id (section 45).
  log.info('notifications rebuilt', {
    domain: domain.channelId,
    kept: toKeep.length,
    added: added.length,
    cancelled: toCancel.length,
  });
  return {
    scheduled: next.length,
    permitted: true,
    cancelled: toCancel.length,
    added: added.length,
  };
}

/** Removes every notification this domain holds, e.g. on sign-out. */
export async function cancelAll(domain: Domain): Promise<void> {
  for (const entry of await loadScheduled(domain)) {
    await cancelOne(entry.notificationId);
  }
  await saveScheduled(domain, []);
}
