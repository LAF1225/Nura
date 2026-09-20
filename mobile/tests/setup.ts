/**
 * Jest setup. Native modules have no implementation under Node, so the two
 * we rely on are swapped for the mocks their packages ship.
 *
 * `jest.mock` factories are hoisted above imports, so they must use
 * `require()` -- an `import` would not be available at that point.
 */
/* eslint-disable @typescript-eslint/no-require-imports */

jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

jest.mock('@react-native-community/netinfo', () =>
  require('@react-native-community/netinfo/jest/netinfo-mock')
);

// No radio under Node. Provisioning logic is tested through the BleTransport
// interface with a simulated robot (tests/fakeRobot.ts); this only stops the
// native module lookup from failing when a screen imports the real transport.
jest.mock('react-native-ble-manager', () => {
  const subscription = { remove: () => undefined };
  const rejectNoRadio = () => Promise.reject(new Error('No Bluetooth under Jest'));
  return {
    __esModule: true,
    default: {
      start: () => Promise.resolve(),
      checkState: () => Promise.resolve('off'),
      scan: rejectNoRadio,
      stopScan: () => Promise.resolve(),
      connect: rejectNoRadio,
      disconnect: () => Promise.resolve(),
      read: rejectNoRadio,
      write: rejectNoRadio,
      startNotification: rejectNoRadio,
      requestMTU: rejectNoRadio,
      retrieveServices: rejectNoRadio,
      enableBluetooth: rejectNoRadio,
      onDiscoverPeripheral: () => subscription,
      onStopScan: () => subscription,
      onDisconnectPeripheral: () => subscription,
      onDidUpdateValueForCharacteristic: () => subscription,
    },
    BleState: {
      On: 'on',
      Off: 'off',
      Unauthorized: 'unauthorized',
      Unsupported: 'unsupported',
      TurningOn: 'turning_on',
      TurningOff: 'turning_off',
      Unknown: 'unknown',
      Resetting: 'resetting',
    },
    BleScanMode: { LowLatency: 2 },
    BleScanMatchMode: { Aggressive: 1 },
    BleScanCallbackType: { AllMatches: 1 },
  };
});
