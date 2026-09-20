/**
 * Finding Nura: what counts as a Nura, how the list is ordered, and what the
 * user is told when Bluetooth or permission stands in the way
 * (PRD 2, sections 8, 9, 18 and 19).
 */
import { PermissionsAndroid } from 'react-native';

import type { BleTransport, ScanResult } from '../src/services/provisioning/bleTransport';
import {
  isNuraAdvertisement,
  mergeScanResult,
  shortIdFromName,
  signalStrength,
} from '../src/services/provisioning/discovery';
import {
  blockedReasonFor,
  discoverNura,
  type DiscoveryState,
} from '../src/services/provisioning/discoverySession';
import {
  permissionsFor,
  requestBluetoothPermissions,
} from '../src/services/provisioning/permissions';
import { UUIDS } from '../src/services/provisioning/protocol';

const NURA: ScanResult = {
  id: 'AA:BB:CC:DD:1B:2C',
  name: 'Nura-1B2C',
  rssi: -55,
  serviceUuids: [UUIDS.service],
};
const HEADPHONES: ScanResult = {
  id: '11:22:33:44:55:66',
  name: 'WH-1000XM5',
  rssi: -40,
  serviceUuids: ['0000110b-0000-1000-8000-00805f9b34fb'],
};
/** A device that merely calls itself Nura, with no provisioning service. */
const IMPOSTER: ScanResult = {
  id: '99:99:99:99:99:99',
  name: 'Nura-FAKE',
  rssi: -30,
  serviceUuids: [],
};

describe('filtering scan results', () => {
  it('accepts only advertisements carrying the provisioning service', () => {
    expect(isNuraAdvertisement(NURA)).toBe(true);
    expect(isNuraAdvertisement(HEADPHONES)).toBe(false);
    expect(isNuraAdvertisement(IMPOSTER)).toBe(false);
  });

  it('matches the service UUID whatever case the platform reports', () => {
    expect(
      isNuraAdvertisement({ ...NURA, serviceUuids: [UUIDS.service.toUpperCase()] })
    ).toBe(true);
  });

  it('keeps unrelated devices out of the list', () => {
    let list = mergeScanResult([], HEADPHONES);
    list = mergeScanResult(list, IMPOSTER);
    expect(list).toEqual([]);

    list = mergeScanResult(list, NURA);
    expect(list).toHaveLength(1);
    expect(list[0]?.shortId).toBe('1B2C');
  });

  it('shows the strongest signal first', () => {
    const far = { ...NURA, id: 'far', name: 'Nura-92BC', rssi: -85 };
    const near = { ...NURA, id: 'near', name: 'Nura-1B2C', rssi: -45 };
    const list = mergeScanResult(mergeScanResult([], far), near);
    expect(list.map((device) => device.shortId)).toEqual(['1B2C', '92BC']);
  });

  it('updates a device already in the list rather than duplicating it', () => {
    const list = mergeScanResult(mergeScanResult([], NURA), { ...NURA, rssi: -70 });
    expect(list).toHaveLength(1);
    expect(list[0]?.rssi).toBe(-70);
  });

  it('remembers the short id when a later advertisement omits the name', () => {
    const list = mergeScanResult(mergeScanResult([], NURA), {
      ...NURA,
      name: null,
      rssi: -60,
    });
    expect(list[0]?.shortId).toBe('1B2C');
  });

  it('only treats a well-formed Nura name as a short id', () => {
    expect(shortIdFromName('Nura-1B2C')).toBe('1B2C');
    expect(shortIdFromName('Nura-lowercase')).toBeNull();
    expect(shortIdFromName('Bedroom speaker')).toBeNull();
    expect(shortIdFromName(null)).toBeNull();
  });

  it('describes signal strength in words', () => {
    expect(signalStrength(-45)).toBe('strong');
    expect(signalStrength(-70)).toBe('nearby');
    expect(signalStrength(-95)).toBe('weak');
  });
});

describe('Android permission model', () => {
  it('asks for scan and connect on Android 12 and later', () => {
    expect(permissionsFor({ OS: 'android', Version: 34 })).toEqual([
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
    ]);
  });

  it('asks for location on Android 11 and earlier, which the OS requires to scan', () => {
    expect(permissionsFor({ OS: 'android', Version: 30 })).toEqual([
      PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
    ]);
  });

  it('asks for nothing on iOS, where CoreBluetooth prompts by itself', () => {
    expect(permissionsFor({ OS: 'ios', Version: '18.0' })).toEqual([]);
  });

  it.each([
    ['granted', 'granted', 'granted'],
    ['granted', 'denied', 'denied'],
    ['granted', 'never_ask_again', 'blocked'],
  ])('reports %s + %s as %s', async (first, second, expected) => {
    const [scan, connect] = permissionsFor({ OS: 'android', Version: 34 });
    jest.spyOn(PermissionsAndroid, 'requestMultiple').mockResolvedValue({
      [String(scan)]: first,
      [String(connect)]: second,
    } as never);

    await expect(
      requestBluetoothPermissions({ OS: 'android', Version: 34 })
    ).resolves.toBe(expected);
  });
});

describe('what blocks discovery', () => {
  it.each([
    ['blocked', null, 'permissionBlocked'],
    ['denied', null, 'permissionDenied'],
    ['granted', 'off', 'bluetoothOff'],
    ['granted', 'unsupported', 'bluetoothUnsupported'],
    ['granted', 'unauthorized', 'permissionBlocked'],
    ['granted', 'on', null],
  ] as const)('permission %s with adapter %s', (permission, adapter, expected) => {
    expect(blockedReasonFor(permission, adapter)).toBe(expected);
  });
});

function fakeTransport(overrides: Partial<BleTransport> = {}): BleTransport {
  return {
    adapterState: async () => 'on',
    requestEnable: async () => true,
    scan: async () => undefined,
    stopScan: async () => undefined,
    connect: async () => undefined,
    disconnect: async () => undefined,
    read: async () => new Uint8Array(),
    write: async () => undefined,
    subscribe: async () => () => undefined,
    onDisconnect: () => () => undefined,
    ...overrides,
  };
}

describe('a discovery attempt', () => {
  const states: DiscoveryState[] = [];
  beforeEach(() => states.splice(0, states.length));
  const record = (state: DiscoveryState) => states.push(state);

  it('lists only the Nura among nearby devices', async () => {
    const transport = fakeTransport({
      scan: async (_seconds, onResult) => {
        onResult(HEADPHONES);
        onResult(NURA);
        onResult(IMPOSTER);
      },
    });

    const final = await discoverNura(
      { transport, requestPermissions: async () => 'granted' },
      record
    );

    expect(final.status).toBe('finished');
    expect(
      final.status === 'finished' && final.devices.map((item) => item.shortId)
    ).toEqual(['1B2C']);
  });

  it('ends with an empty list when the scan finds nothing', async () => {
    const final = await discoverNura(
      { transport: fakeTransport(), requestPermissions: async () => 'granted' },
      record
    );
    expect(final).toEqual({ status: 'finished', devices: [] });
  });

  it('stops before scanning when permission is refused', async () => {
    let scanned = false;
    const transport = fakeTransport({
      scan: async () => {
        scanned = true;
      },
    });

    const final = await discoverNura(
      { transport, requestPermissions: async () => 'denied' },
      record
    );

    expect(final).toEqual({ status: 'blocked', reason: 'permissionDenied' });
    expect(scanned).toBe(false);
  });

  it('stops when Bluetooth is switched off', async () => {
    const transport = fakeTransport({ adapterState: async () => 'off' });
    const final = await discoverNura(
      { transport, requestPermissions: async () => 'granted' },
      record
    );
    expect(final).toEqual({ status: 'blocked', reason: 'bluetoothOff' });
  });

  it('treats a scan that cannot start as Bluetooth being unavailable', async () => {
    const transport = fakeTransport({
      scan: async () => {
        throw new Error('scan failed');
      },
    });
    const final = await discoverNura(
      { transport, requestPermissions: async () => 'granted' },
      record
    );
    expect(final).toEqual({ status: 'blocked', reason: 'bluetoothOff' });
  });

  it('reports progress so the screen can show it is searching', async () => {
    const transport = fakeTransport({
      scan: async (_seconds, onResult) => onResult(NURA),
    });
    await discoverNura({ transport, requestPermissions: async () => 'granted' }, record);
    expect(states.map((state) => state.status)).toEqual([
      'checking',
      'scanning',
      'scanning',
      'finished',
    ]);
  });
});
