/**
 * What each recovery button does, in one place, so every pairing screen
 * behaves the same way (PRD 2, section 50).
 */
import { useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { Linking } from 'react-native';

import { getBleTransport, type RecoveryAction } from '../services/provisioning';
import { useProvisioningFlow } from './useProvisioning';

export function usePairingRecovery() {
  const router = useRouter();
  const { flow } = useProvisioningFlow();
  const [busy, setBusy] = useState(false);

  const handle = useCallback(
    async (action: RecoveryAction) => {
      setBusy(true);
      try {
        switch (action) {
          case 'turnOnBluetooth': {
            const enabled = await getBleTransport().requestEnable();
            if (!enabled) await Linking.openSettings();
            break;
          }
          case 'openSettings':
            await Linking.openSettings();
            break;
          case 'pairingHelp':
            router.push('/pairing/help');
            break;
          case 'checkAgain':
            await flow.checkAgain();
            break;
          case 'retryPassword':
          case 'chooseNetwork':
          case 'tryAgain': {
            const outcome = await flow.tryAgain();
            if (outcome === 'wifi') {
              router.dismissTo('/pairing/wifi');
            } else if (outcome === 'restart') {
              await flow.cancel();
              router.dismissTo('/pairing/discover');
            }
            break;
          }
          case 'findAgain':
            await flow.cancel();
            router.dismissTo('/pairing/discover');
            break;
          case 'done':
            await flow.cancel();
            router.dismissAll();
            router.replace('/');
            break;
        }
      } finally {
        setBusy(false);
      }
    },
    [flow, router]
  );

  return { handle, busy };
}
