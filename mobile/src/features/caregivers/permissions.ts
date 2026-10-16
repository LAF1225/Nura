/**
 * Permission-aware helpers for the app (PRD 9, sections 9, 18 and 62).
 *
 * Section 62 asks for helpers like `canView('medications')`. These are them, and
 * the comment section 62 ends with is the important part: **the server remains
 * authoritative.** Nothing here decides anything. Every function takes the
 * granted set the server sent and answers a question about it, so a bug in this
 * file can hide a section the caregiver is allowed to see -- it cannot reveal one
 * they are not.
 *
 * Section 9 says the same thing from the other side: hiding UI is not
 * authorization. The reason these helpers exist is so a screen does not render a
 * section that would come back empty, not so a screen can be trusted to decide.
 *
 * **A caregiver's home distinguishes three states, and so do these.** A category
 * can be *not granted* (the server omits it; `null`), *granted with nothing in
 * it* (`[]`), or *granted and populated*. Section 18 says the first must be
 * indistinguishable from a person who has nothing recorded, which is only true if
 * the app never renders a heading for it.
 */
import type { CaregiverHome, PermissionKey } from './types';

/**
 * Categories that can be granted but have nothing behind them today.
 *
 * `safety_alerts` because PRD 9 section 94 says the key may exist before its
 * event source does and that no alert should be fabricated; `routines` because
 * nothing in PRD 0-9 defines what a routine is. Both are granted faithfully and
 * unlock nothing, and the screens say so rather than showing an empty section.
 */
export const PERMISSIONS_WITHOUT_DATA: readonly PermissionKey[] = [
  'safety_alerts',
  'routines',
];

/** Whether this granted set includes a category. */
export function canView(
  granted: readonly PermissionKey[] | undefined,
  key: PermissionKey
): boolean {
  return (granted ?? []).includes(key);
}

/**
 * Granted *and* backed by something that exists.
 *
 * What a screen should use to decide whether to render a section: a granted
 * category with no source yet gets a sentence explaining that, not an empty list.
 */
export function canUse(
  granted: readonly PermissionKey[] | undefined,
  key: PermissionKey
): boolean {
  return canView(granted, key) && !PERMISSIONS_WITHOUT_DATA.includes(key);
}

/** True when nothing at all has been shared with this caregiver. */
export function hasNothingGranted(granted: readonly PermissionKey[]): boolean {
  return granted.length === 0;
}

/**
 * Which sections a caregiver home should actually draw.
 *
 * Driven by whether the payload *has* the section rather than by the granted
 * list, which is the same thing said twice on purpose: the server omits what was
 * not granted, so a section the app can see is one it may show. If the two ever
 * disagreed, this trusts the payload -- the narrower answer.
 */
export function homeSections(home: CaregiverHome): {
  medications: boolean;
  appointments: boolean;
  symptoms: boolean;
  reports: boolean;
  healthCounts: boolean;
  messages: boolean;
} {
  return {
    medications: home.medications !== null,
    appointments: home.appointments !== null,
    symptoms: home.symptoms !== null,
    reports: home.reports !== null,
    healthCounts: home.healthCounts !== null,
    messages: home.unreadMessages !== null,
  };
}

/**
 * The categories granted that currently do nothing, for the explanatory line.
 *
 * Taken from the server's own `grantedWithoutData` when it sent one, so the app
 * and the backend cannot disagree about which categories are waiting on a later
 * PRD.
 */
export function dormantPermissions(home: CaregiverHome): PermissionKey[] {
  if (home.grantedWithoutData.length > 0) return home.grantedWithoutData;
  return home.granted.filter((key) => PERMISSIONS_WITHOUT_DATA.includes(key));
}
