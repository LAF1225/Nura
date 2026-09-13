/**
 * React access to the shared provisioning flow and to "Find my Nura".
 */
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';

import {
  findNura,
  getProvisioningFlow,
  type DiscoveryState,
  type FlowState,
} from '../services/provisioning';

/** The current flow state, re-rendering whenever it changes. */
export function useProvisioningFlow() {
  const flow = getProvisioningFlow();
  const state = useSyncExternalStore<FlowState>(
    (onChange) => flow.subscribe(onChange),
    () => flow.getState()
  );
  return { flow, state };
}

/** Runs discovery on demand and exposes its progress. */
export function useNuraDiscovery() {
  const [state, setState] = useState<DiscoveryState>({ status: 'idle' });
  const mounted = useRef(true);
  const running = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const start = useCallback(async () => {
    if (running.current) return;
    running.current = true;
    try {
      await findNura((next) => {
        if (mounted.current) setState(next);
      });
    } finally {
      running.current = false;
    }
  }, []);

  return { state, start };
}
