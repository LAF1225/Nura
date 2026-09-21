/**
 * Whether the phone currently has a usable connection (PRD 3, section 26).
 *
 * Used for the offline banner and for retrying a queued check-in the moment
 * connectivity returns. It is not used to decide whether to *try* a request --
 * the API client already reports `offline` on its own, and a request that
 * might work is always worth attempting.
 */
import NetInfo from '@react-native-community/netinfo';
import { useEffect, useState } from 'react';

/** `isInternetReachable` is null while undetermined; unknown counts as online. */
function offlineFrom(state: {
  isConnected: boolean | null;
  isInternetReachable: boolean | null;
}): boolean {
  return state.isConnected === false || state.isInternetReachable === false;
}

export function useIsOffline(): boolean {
  const [isOffline, setIsOffline] = useState(false);

  useEffect(() => {
    let active = true;

    const unsubscribe = NetInfo.addEventListener((state) => {
      if (active) setIsOffline(offlineFrom(state));
    });

    // The listener only fires on change, so ask once for the current state --
    // otherwise a launch with no signal shows no banner until it changes.
    void NetInfo.fetch()
      .then((state) => {
        if (active) setIsOffline(offlineFrom(state));
      })
      .catch(() => undefined);

    return () => {
      active = false;
      unsubscribe();
    };
  }, []);

  return isOffline;
}

/**
 * Runs `onReconnect` when the phone comes back online.
 *
 * Only on the transition, not on every network event: something that retries a
 * queued submission should not fire repeatedly while the connection is fine.
 */
export function useOnReconnect(onReconnect: () => void): void {
  useEffect(() => {
    let wasOffline = false;

    const unsubscribe = NetInfo.addEventListener((state) => {
      const offline = offlineFrom(state);
      if (wasOffline && !offline) onReconnect();
      wasOffline = offline;
    });

    return unsubscribe;
  }, [onReconnect]);
}
