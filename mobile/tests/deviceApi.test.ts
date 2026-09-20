/**
 * Parsing device responses (PRD 2, sections 34 and 46).
 *
 * The rule worth testing: an unexpected value must never read as "online".
 */
import { parseDevice, parseDeviceStatus } from '../src/services/api/devices';
import { ApiError } from '../src/services/api/errors';
import { connectionSentence, connectionLabel } from '../src/components/DeviceStatus';
import { timeAgo } from '../src/utils/time';

const WIRE = {
  id: 'device-1',
  hardware_id: 'NURA-3C84279A1B2C',
  display_name: 'Bedroom Nura',
  device_type: 'xiao-esp32-s3',
  firmware_version: '0.1.0',
  provisioning_status: 'claimed',
  connection_status: 'online',
  last_seen_at: '2026-09-20T10:00:00Z',
  claimed_at: '2026-09-20T09:00:00Z',
  setup_completed_at: '2026-09-20T09:01:00Z',
  introduced_at: '2026-09-20T09:02:00Z',
  owner_profile_id: 'profile-1',
  created_at: '2026-09-20T09:00:00Z',
  updated_at: '2026-09-20T10:00:00Z',
};

describe('parsing a device', () => {
  it('maps the wire format to the app shape', () => {
    const device = parseDevice(WIRE);
    expect(device.displayName).toBe('Bedroom Nura');
    expect(device.hardwareId).toBe('NURA-3C84279A1B2C');
    expect(device.connectionStatus).toBe('online');
    expect(device.lastSeenAt).toBe('2026-09-20T10:00:00Z');
    expect(device.ownerProfileId).toBe('profile-1');
  });

  it('treats an unrecognised connection status as unknown, never online', () => {
    expect(
      parseDevice({ ...WIRE, connection_status: 'probably_fine' }).connectionStatus
    ).toBe('unknown');
    expect(parseDevice({ ...WIRE, connection_status: undefined }).connectionStatus).toBe(
      'unknown'
    );
  });

  it('treats a missing optional field as absent rather than crashing', () => {
    const device = parseDevice({ ...WIRE, firmware_version: null, introduced_at: null });
    expect(device.firmwareVersion).toBeNull();
    expect(device.introducedAt).toBeNull();
  });

  it('rejects a response missing something it must have', () => {
    expect(() => parseDevice({ ...WIRE, id: undefined })).toThrow(ApiError);
    expect(() => parseDevice('not an object')).toThrow(ApiError);
  });
});

describe('parsing device status', () => {
  it('defaults the online threshold and flags when the server omits them', () => {
    const status = parseDeviceStatus({ device_id: 'device-1' });
    expect(status.connectionStatus).toBe('unknown');
    expect(status.checkedInSinceClaim).toBe(false);
    expect(status.onlineThresholdSeconds).toBe(90);
    expect(status.introductionPending).toBe(false);
  });
});

describe('how a connection is described', () => {
  const now = Date.parse('2026-09-20T10:12:00Z');

  it('uses calm wording, never "device lost"', () => {
    expect(
      connectionSentence('Bedroom Nura', 'online', '2026-09-20T10:11:00Z', now)
    ).toBe('Bedroom Nura is online.');
    expect(
      connectionSentence('Bedroom Nura', 'offline', '2026-09-20T10:00:00Z', now)
    ).toBe('Bedroom Nura is currently offline. Last connected 12 minutes ago.');
    expect(connectionSentence('Nura', 'unknown', null, now)).toMatch(
      /hasn’t connected yet/
    );
  });

  it('labels the status for the chip', () => {
    expect(connectionLabel('online')).toBe('Online');
    expect(connectionLabel('offline')).toBe('Offline');
    expect(connectionLabel('unknown')).toBe('Not connected yet');
  });

  it('phrases elapsed time the way a person would', () => {
    const base = Date.parse('2026-09-20T12:00:00Z');
    expect(timeAgo('2026-09-20T11:59:30Z', base)).toBe('just now');
    expect(timeAgo('2026-09-20T11:59:00Z', base)).toBe('1 minute ago');
    expect(timeAgo('2026-09-20T11:48:00Z', base)).toBe('12 minutes ago');
    expect(timeAgo('2026-09-20T09:00:00Z', base)).toBe('3 hours ago');
    expect(timeAgo('2026-09-19T12:00:00Z', base)).toBe('yesterday');
    expect(timeAgo('2026-09-15T12:00:00Z', base)).toBe('5 days ago');
    expect(timeAgo('not a date', base)).toBe('some time ago');
  });
});
