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
