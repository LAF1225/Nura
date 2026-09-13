/**
 * Everything that can go wrong during pairing, in calm words, each with a way
 * forward (PRD 2, sections 47 and 50).
 */
import { isApiError } from '../api/errors';
import type { ProvisioningErrorName } from './protocol';

export type FlowErrorKind =
  | 'bluetoothOff'
  | 'bluetoothUnsupported'
  | 'permissionDenied'
  | 'permissionBlocked'
  | 'noNuraFound'
  | 'connectionFailed'
  | 'incompatibleFirmware'
  | 'notInPairingMode'
  | 'disconnected'
  | 'tooManyAttempts'
  | 'wifiAuthFailed'
  | 'wifiNotFound'
  | 'wifiTimeout'
  | 'wifiUnsupported'
  | 'sendFailed'
  | 'backendUnreachable'
  | 'robotCannotReachBackend'
  | 'registrationFailed'
  | 'alreadyClaimed'
  | 'identityMismatch'
  | 'onboardingIncomplete'
  | 'robotWentOffline'
  | 'unknown';

export type RecoveryAction =
  | 'turnOnBluetooth'
  | 'openSettings'
  | 'findAgain'
  | 'pairingHelp'
  | 'retryPassword'
  | 'chooseNetwork'
  | 'tryAgain'
  | 'checkAgain'
  | 'done';

export interface FlowErrorInfo {
  title: string;
  message: string;
  /** In priority order; the first is the primary button. */
  actions: RecoveryAction[];
}

export const FLOW_ERRORS: Record<FlowErrorKind, FlowErrorInfo> = {
  bluetoothOff: {
    title: 'Bluetooth is off',
    message: 'Turn on Bluetooth so your phone can find Nura. You only need it during setup.',
    actions: ['turnOnBluetooth', 'findAgain'],
  },
  bluetoothUnsupported: {
    title: 'Bluetooth isn’t available',
    message: 'This phone doesn’t support the Bluetooth Nura uses for setup.',
    actions: ['pairingHelp'],
  },
  permissionDenied: {
    title: 'Bluetooth permission needed',
    message:
      'Nura uses Bluetooth during setup to securely connect your phone to your robot.',
    actions: ['findAgain', 'openSettings'],
  },
  permissionBlocked: {
    title: 'Bluetooth permission is turned off',
    message:
      'Allow Nura to use Bluetooth in your phone’s settings, then come back and try again.',
    actions: ['openSettings', 'findAgain'],
  },
  noNuraFound: {
    title: 'We couldn’t find Nura',
    message: 'Make sure Nura is powered on, close by, and showing that it’s ready to pair.',
    actions: ['findAgain', 'pairingHelp'],
  },
  connectionFailed: {
    title: 'Couldn’t connect to Nura',
    message: 'Move your phone a little closer to Nura and try again.',
    actions: ['findAgain', 'pairingHelp'],
  },
  incompatibleFirmware: {
    title: 'Nura needs an update',
    message: 'This Nura is running software this app can’t set up yet.',
    actions: ['pairingHelp'],
  },
  notInPairingMode: {
    title: 'Nura isn’t ready to pair',
    message: 'Hold the button on Nura for 3 seconds until it shows it’s ready, then try again.',
    actions: ['findAgain', 'pairingHelp'],
  },
  disconnected: {
    title: 'Connection to Nura was lost',
    message: 'Keep your phone near Nura and start again.',
    actions: ['findAgain', 'pairingHelp'],
  },
  tooManyAttempts: {
    title: 'Too many incorrect codes',
    message: 'For your security, Nura has stopped this attempt. Find Nura again to get a new code.',
    actions: ['findAgain'],
  },
  wifiAuthFailed: {
    title: 'Wi-Fi password didn’t work',
    message: 'Nura couldn’t connect to this Wi-Fi network. Check the password and try again.',
    actions: ['retryPassword', 'chooseNetwork'],
  },
  wifiNotFound: {
    title: 'Nura couldn’t see that network',
    message:
      'Check the network name. Nura uses 2.4 GHz Wi-Fi, so a 5 GHz-only network won’t appear.',
    actions: ['chooseNetwork', 'retryPassword'],
  },
  wifiTimeout: {
    title: 'The network didn’t respond',
    message: 'Nura tried to join but didn’t hear back in time. Moving Nura closer to the router can help.',
    actions: ['tryAgain', 'chooseNetwork'],
  },
  wifiUnsupported: {
    title: 'This network isn’t supported',
    message: 'Nura works with home Wi-Fi (WPA2 or WPA3 Personal) on 2.4 GHz.',
    actions: ['chooseNetwork'],
  },
  sendFailed: {
    title: 'Couldn’t send the Wi-Fi details',
    message: 'Something went wrong sending the details to Nura. Please try again.',
    actions: ['tryAgain', 'findAgain'],
  },
  backendUnreachable: {
    title: 'Nura services are unreachable',
    message: 'Check your phone’s internet connection and try again.',
    actions: ['tryAgain'],
  },
  robotCannotReachBackend: {
    title: 'Nura can’t reach Nura services',
    message:
      'Nura joined your Wi-Fi but couldn’t get online. Check your internet connection is working.',
    actions: ['tryAgain', 'chooseNetwork'],
  },
  registrationFailed: {
    title: 'Couldn’t link Nura',
    message: 'The setup session ran out of time. Please try again.',
    actions: ['tryAgain', 'findAgain'],
  },
  alreadyClaimed: {
    title: 'This Nura is already linked',
    message: 'This Nura is already linked to another account.',
    actions: ['done', 'pairingHelp'],
  },
  identityMismatch: {
    title: 'Couldn’t confirm this Nura',
    message: 'This Nura’s identity doesn’t match our records, so it can’t be linked.',
    actions: ['done', 'pairingHelp'],
  },
  onboardingIncomplete: {
    title: 'Finish setting up your account',
    message: 'Complete your account setup first, then connect Nura.',
    actions: ['done'],
  },
  robotWentOffline: {
    title: 'Nura hasn’t come online yet',
    message:
      'Nura may still be connecting. Check again in a moment, or try setup again.',
    actions: ['checkAgain', 'tryAgain', 'pairingHelp'],
  },
  unknown: {
    title: 'Something went wrong',
    message: 'Please try again.',
    actions: ['tryAgain', 'pairingHelp'],
  },
};

/** Maps a robot STATUS error onto what the user sees. */
export function flowErrorForRobot(error: ProvisioningErrorName): FlowErrorKind {
  switch (error) {
    case 'WIFI_AUTH_FAILED':
      return 'wifiAuthFailed';
    case 'WIFI_NOT_FOUND':
      return 'wifiNotFound';
    case 'WIFI_TIMEOUT':
      return 'wifiTimeout';
    case 'WIFI_UNSUPPORTED':
      return 'wifiUnsupported';
    case 'BACKEND_UNREACHABLE':
      return 'robotCannotReachBackend';
    case 'REGISTRATION_REJECTED':
      return 'registrationFailed';
    case 'ALREADY_CLAIMED':
      return 'alreadyClaimed';
    case 'IDENTITY_MISMATCH':
      return 'identityMismatch';
    case 'INVALID_PAYLOAD':
    case 'NOT_VERIFIED':
    case 'NO_CREDENTIALS':
      return 'sendFailed';
    default:
      return 'unknown';
  }
}

/** Maps an error from the Nura backend onto what the user sees. */
export function flowErrorForApi(error: unknown): FlowErrorKind {
  if (!isApiError(error)) return 'unknown';
  switch (error.code) {
    case 'already_claimed':
      return 'alreadyClaimed';
    case 'onboarding_incomplete':
      return 'onboardingIncomplete';
    case 'identity_mismatch':
      return 'identityMismatch';
  }
  switch (error.kind) {
    case 'offline':
    case 'unavailable':
    case 'timeout':
    case 'server':
    case 'configuration':
      return 'backendUnreachable';
    default:
      return 'unknown';
  }
}

/** Errors the user can fix by sending different Wi-Fi details over the same connection. */
export function isWifiRetryable(kind: FlowErrorKind): boolean {
  return (
    kind === 'wifiAuthFailed' ||
    kind === 'wifiNotFound' ||
    kind === 'wifiTimeout' ||
    kind === 'wifiUnsupported' ||
    kind === 'robotCannotReachBackend' ||
    kind === 'sendFailed' ||
    kind === 'registrationFailed'
  );
}
