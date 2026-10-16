/**
 * Parsing the robot's endpoints, and the directions it is safe to guess in.
 *
 * PRD 11, sections 10, 12, 14, 22, 30, 47, 96, 104, 105 and 124.
 *
 * Four rules, and each one is a decision about what to do with something the
 * client does not recognise.
 *
 * **An unknown capability state reads as `not_connected`, never `available`.**
 * Guessing optimistically is how a screen ends up offering a volume control
 * for a speaker that does not exist (sections 12 and 47).
 *
 * **An unknown presentation status reads as `queued`, never `completed`.**
 * Section 14's whole point is that nothing may be assumed to have been shown.
 *
 * **`reducedMotion` keeps three states.** Null means *follow my accessibility
 * setting*, and collapsing it to false would silently stop the robot following
 * that setting (sections 30 and 105).
 *
 * **An unknown medication privacy level reads as `private`.** The conservative
 * default (section 104): an unrecognised value must never read as "show
 * everything" on a screen other people can see.
 */
import { readFileSync } from 'fs';
import { join } from 'path';

import {
  fetchPresentationHistory,
  fetchPresentationPreferences,
  fetchRobotCapabilities,
  fetchRobotStatus,
  updatePresentationPreferences,
} from '../src/features/robot/api';
import { setAuthTokenProvider } from '../src/services/api/client';
import {
  mockBackend,
  presentationFixture,
  presentationPreferencesFixture,
  robotCapabilitiesFixture,
  robotCapabilityRowsFixture,
  robotStatusFixture,
} from './helpers';

let backend: ReturnType<typeof mockBackend>;

beforeEach(() => {
  setAuthTokenProvider(async () => 'test-token');
  backend = mockBackend({});
});

afterEach(() => {
  backend.restore();
  // The provider is a function, not nullable: resetting it means installing
  // one that has no token, which is what an unauthenticated app has.
  setAuthTokenProvider(async () => null);
});

function bodyOf(index: number): Record<string, unknown> {
  const sent = backend.requests[index]?.body;
  return (sent ?? {}) as Record<string, unknown>;
}

describe('capabilities', () => {
  it('keeps both states and says when they differ', async () => {
    // Section 124: the device said the screen works, and the firmware it said
    // that under is no longer running -- so the state to act on is
    // "not tested yet" while the row still records what was reported.
    const rows = robotCapabilityRowsFixture();
    const display = rows.find((row) => row.key === 'display') as Record<string, unknown>;
    display.state = 'not_verified';
    display.reported_state = 'available';
    display.state_label = 'Not tested yet';
    display.stale = true;
    backend.state.robotCapabilities = robotCapabilitiesFixture({
      capabilities: rows,
      display_available: false,
      text_available: false,
    });

    const parsed = await fetchRobotCapabilities('device-1');
    const screen = parsed.capabilities.find((row) => row.key === 'display');
    expect(screen?.state).toBe('not_verified');
    expect(screen?.reportedState).toBe('available');
    expect(screen?.stale).toBe(true);
    expect(parsed.displayAvailable).toBe(false);
  });

  it('reads an unrecognised state as not reported rather than working', async () => {
    const rows = robotCapabilityRowsFixture();
    (rows[0] as Record<string, unknown>).state = 'probably_fine';
    backend.state.robotCapabilities = robotCapabilitiesFixture({ capabilities: rows });

    const parsed = await fetchRobotCapabilities('device-1');
    expect(parsed.capabilities[0]?.state).toBe('not_connected');
  });

  it('drops a capability key it does not know rather than rendering it', async () => {
    const rows = robotCapabilityRowsFixture();
    rows.push({
      key: 'laser',
      state: 'available',
      reported_state: 'available',
      label: 'Laser',
      state_label: 'Working',
      source: 'device_report',
      reported_at: null,
      firmware_version: null,
      stale: false,
    });
    backend.state.robotCapabilities = robotCapabilitiesFixture({ capabilities: rows });

    const parsed = await fetchRobotCapabilities('device-1');
    expect(parsed.capabilities).toHaveLength(12);
    expect(parsed.capabilities.map((row) => row.key)).not.toContain('laser');
  });

  it('returns all twelve keys even when nothing has been reported', async () => {
    backend.state.robotCapabilities = robotCapabilitiesFixture({
      capabilities: robotCapabilityRowsFixture(
        Object.fromEntries(
          robotCapabilityRowsFixture().map((row) => [row.key as string, 'not_connected'])
        )
      ),
    });
    const parsed = await fetchRobotCapabilities('device-1');
    expect(parsed.capabilities).toHaveLength(12);
    expect(parsed.displayAvailable).toBe(false);
  });
});

describe('preferences', () => {
  it('keeps null as a third state rather than reading it as off', async () => {
    const parsed = await fetchPresentationPreferences('device-1');
    expect(parsed.reducedMotion).toBeNull();
    expect(parsed.effectiveReducedMotion).toBe(false);
  });

  it('sends null explicitly when asked to follow the accessibility setting', async () => {
    await updatePresentationPreferences('device-1', { reducedMotion: null });
    expect(bodyOf(0).reduced_motion).toBeNull();
    expect('reduced_motion' in bodyOf(0)).toBe(true);
  });

  it('sends only what changed', async () => {
    await updatePresentationPreferences('device-1', { brightness: 25 });
    expect(bodyOf(0)).toEqual({ brightness: 25 });
  });

  it('reads an unrecognised privacy level as private', async () => {
    backend.state.robotPreferences = presentationPreferencesFixture({
      medication_privacy_level: 'everything',
    });
    const parsed = await fetchPresentationPreferences('device-1');
    expect(parsed.medicationPrivacyLevel).toBe('private');
  });

  it('clamps a level to the range the column allows', async () => {
    backend.state.robotPreferences = presentationPreferencesFixture({
      brightness: 480,
      volume: -20,
    });
    const parsed = await fetchPresentationPreferences('device-1');
    expect(parsed.brightness).toBe(100);
    expect(parsed.volume).toBe(0);
  });
});

describe('history', () => {
  it('keeps the rendered line verbatim', async () => {
    // Section 96, and section 14 underneath it: "sent to Nura" is the server's
    // sentence and the client does not rebuild it from the status.
    backend.state.robotPresentations = [
      presentationFixture({ status: 'sent' }),
      presentationFixture({ id: 'presentation-2', status: 'expired' }),
    ];
    const parsed = await fetchPresentationHistory('device-1');
    expect(parsed[0]?.line).toBe('Medication reminder — sent to Nura');
    expect(parsed[1]?.line).toBe('Medication reminder — expired');
  });

  it('reads an unrecognised status as waiting rather than shown', async () => {
    backend.state.robotPresentations = [
      presentationFixture({ status: 'probably_shown' }),
    ];
    const parsed = await fetchPresentationHistory('device-1');
    expect(parsed[0]?.status).toBe('queued');
  });

  it('carries the privacy-filtered summary and nothing more', async () => {
    backend.state.robotPresentations = [presentationFixture()];
    const parsed = await fetchPresentationHistory('device-1');
    expect(parsed[0]?.summary).toBe('Reminder due');
    expect(JSON.stringify(parsed[0])).not.toContain('Metformin');
  });
});

describe('status', () => {
  it('never reads an unrecognised connection as online', async () => {
    backend.state.robotStatus = robotStatusFixture({ connection_status: 'maybe' });
    const parsed = await fetchRobotStatus('device-1');
    expect(parsed.connectionStatus).toBe('unknown');
  });

  it('carries the offline note from the server', async () => {
    backend.state.robotStatus = robotStatusFixture({
      connection_status: 'offline',
      mode: 'offline',
      mode_label: 'Offline',
      offline_note: 'Robot offline — this item remains available on your phone.',
    });
    const parsed = await fetchRobotStatus('device-1');
    expect(parsed.offlineNote).toBe(
      'Robot offline — this item remains available on your phone.'
    );
  });

  it('has no current presentation, because nothing has acknowledged one', async () => {
    const parsed = await fetchRobotStatus('device-1');
    expect(parsed.current).toBeNull();
  });
});

describe('what the client cannot do', () => {
  it('has no function that could acknowledge a presentation', () => {
    // Sections 14 and 19: only a device may say what it drew, and the app
    // holds no device token. Checked by reading the module rather than its
    // exports, because a client that could acknowledge would also need the
    // ack endpoint -- and neither the path nor the word is in the file.
    const source = readFileSync(
      join(__dirname, '..', 'src', 'features', 'robot', 'api.ts'),
      'utf8'
    );
    const exported = [...source.matchAll(/^export async function (\w+)/gm)].map(
      (match) => match[1] as string
    );
    expect(exported.length).toBeGreaterThan(3);
    for (const name of exported) {
      expect(name.toLowerCase()).not.toContain('acknowledge');
      expect(name.toLowerCase()).not.toContain('ack');
    }
    expect(source).not.toContain('/ack');
    expect(source).not.toContain('device-actions');
  });
});
