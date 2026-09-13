/**
 * Server state for the account's robots (PRD 2, sections 42-47).
 *
 * Online/offline always comes from the backend. The app never decides a robot
 * is online on its own.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  completeDeviceSetup,
  fetchDevice,
  fetchDevices,
  fetchDeviceStatus,
  renameDevice,
} from '../services/api/devices';
import { useAppStore } from '../store/appStore';
import type { Device, DeviceStatus } from '../types/device';
import { onboardingQueryKey } from './useOnboarding';

export const devicesQueryKey = ['devices'] as const;
export const deviceQueryKey = (id: string) => ['devices', id] as const;
export const deviceStatusQueryKey = (id: string) => ['devices', id, 'status'] as const;

/** How often a visible status is refreshed. Well inside the 90 s threshold. */
const STATUS_REFRESH_MS = 30_000;

export function useDevices() {
  const authStatus = useAppStore((state) => state.authStatus);
  return useQuery<Device[]>({
    queryKey: devicesQueryKey,
    queryFn: ({ signal }) => fetchDevices(signal),
    enabled: authStatus === 'authenticated',
    refetchInterval: STATUS_REFRESH_MS,
  });
}

export function useDevice(id: string | undefined) {
  return useQuery<Device>({
    queryKey: deviceQueryKey(id ?? ''),
    queryFn: ({ signal }) => fetchDevice(id ?? '', signal),
    enabled: Boolean(id),
    refetchInterval: STATUS_REFRESH_MS,
  });
}

export function useDeviceStatus(id: string | undefined) {
  return useQuery<DeviceStatus>({
    queryKey: deviceStatusQueryKey(id ?? ''),
    queryFn: ({ signal }) => fetchDeviceStatus(id ?? '', signal),
    enabled: Boolean(id),
    refetchInterval: STATUS_REFRESH_MS,
  });
}

function useRefreshDevices() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: devicesQueryKey });
}

export function useRenameDevice() {
  const refresh = useRefreshDevices();
  return useMutation({
    mutationFn: ({ id, displayName }: { id: string; displayName: string }) =>
      renameDevice(id, displayName),
    onSuccess: refresh,
  });
}

export function useCompleteDeviceSetup() {
  const refresh = useRefreshDevices();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => completeDeviceSetup(id),
    onSuccess: async () => {
      await Promise.all([
        refresh(),
        // The server advanced onboarding to robot_connected.
        queryClient.invalidateQueries({ queryKey: onboardingQueryKey }),
      ]);
    },
  });
}
