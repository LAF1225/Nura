/**
 * Server state for the robot's display and companion behaviour (PRD 11).
 *
 * Three things worth reading rather than skimming.
 *
 * **The status query polls only while the robot is online.** What it is showing
 * changes when the backend reconciles, which happens on the robot's own polls
 * -- so a Nura Device screen left open on an online robot refreshes, and one
 * showing an offline robot does not. Section 3's "not a notification
 * billboard" applies to the app's battery as much as to the robot's screen.
 *
 * **There is no acknowledgement mutation, and there cannot be.** Only a device
 * may say what it drew (sections 14 and 19), and the app holds no device token
 * -- PRD 2 put the user's credentials nowhere near the hardware and PRD 11
 * keeps it that way. Nothing in this file can mark a presentation displayed.
 *
 * **The device is resolved once, here.** Every robot screen needs the same
 * answer to "which robot?", and a screen that worked it out for itself would
 * be a second place that decision could be wrong. `useRobotDevice` is the one
 * place, and it answers null for an account with no robot -- which is every
 * account today.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';

import { useDevices } from '../../hooks/useDevices';
import { useAppStore } from '../../store/appStore';
import {
  fetchPresentationHistory,
  fetchPresentationPreferences,
  fetchRobotCapabilities,
  fetchRobotStatus,
  updatePresentationPreferences,
} from './api';
import type {
  Capabilities,
  Presentation,
  PresentationPreferences,
  PresentationPreferencesInput,
  RobotStatus,
} from './types';

export const robotStatusKey = (deviceId: string) => ['robot-status', deviceId] as const;
export const robotCapabilitiesKey = (deviceId: string) =>
  ['robot-capabilities', deviceId] as const;
export const robotPreferencesKey = (deviceId: string) =>
  ['robot-preferences', deviceId] as const;
export const robotHistoryKey = (deviceId: string) => ['robot-history', deviceId] as const;

/**
 * How often to re-read the status while the robot is online.
 *
 * Fifteen seconds: the robot's own poll interval is five, so this is slow
 * enough not to shadow it and quick enough that a card appearing on a shelf
 * shows up on the phone while somebody is watching. Nothing depends on it for
 * correctness -- every read reconciles server-side.
 */
const LIVE_POLL_MS = 15000;

/** The account's robot, or null. Null for every account today. */
export function useRobotDevice() {
  const devices = useDevices();
  const device = devices.data?.[0] ?? null;
  return {
    device,
    deviceId: device?.id ?? null,
    isLoading: devices.isLoading,
    isError: devices.isError,
    error: devices.error,
    refetch: devices.refetch,
  };
}

function useEnabled(deviceId: string | null): boolean {
  const authStatus = useAppStore((state) => state.authStatus);
  return authStatus === 'authenticated' && deviceId !== null;
}

export function useRobotStatus(deviceId: string | null) {
  const enabled = useEnabled(deviceId);
  return useQuery<RobotStatus>({
    queryKey: robotStatusKey(deviceId ?? 'none'),
    queryFn: () => fetchRobotStatus(deviceId as string),
    enabled,
    refetchInterval: (query) =>
      query.state.data?.connectionStatus === 'online' ? LIVE_POLL_MS : false,
  });
}

export function useRobotCapabilities(deviceId: string | null) {
  const enabled = useEnabled(deviceId);
  return useQuery<Capabilities>({
    queryKey: robotCapabilitiesKey(deviceId ?? 'none'),
    queryFn: () => fetchRobotCapabilities(deviceId as string),
    enabled,
  });
}

export function usePresentationPreferences(deviceId: string | null) {
  const enabled = useEnabled(deviceId);
  return useQuery<PresentationPreferences>({
    queryKey: robotPreferencesKey(deviceId ?? 'none'),
    queryFn: () => fetchPresentationPreferences(deviceId as string),
    enabled,
  });
}

export function usePresentationHistory(deviceId: string | null) {
  const enabled = useEnabled(deviceId);
  return useQuery<Presentation[]>({
    queryKey: robotHistoryKey(deviceId ?? 'none'),
    queryFn: () => fetchPresentationHistory(deviceId as string),
    enabled,
  });
}

/**
 * Changes one or more settings (section 46).
 *
 * The response replaces the cache rather than invalidating it, so a switch
 * does not flicker back to its old position while a refetch runs. The server's
 * answer is authoritative because it carries `effectiveReducedMotion`, which
 * the client cannot compute.
 */
export function useUpdatePresentationPreferences(deviceId: string | null) {
  const client = useQueryClient();
  const invalidate = useCallback(() => {
    if (deviceId === null) return;
    void client.invalidateQueries({ queryKey: robotStatusKey(deviceId) });
  }, [client, deviceId]);

  return useMutation<PresentationPreferences, Error, PresentationPreferencesInput>({
    mutationFn: (input) => updatePresentationPreferences(deviceId as string, input),
    onSuccess: (preferences) => {
      if (deviceId !== null) {
        client.setQueryData(robotPreferencesKey(deviceId), preferences);
      }
      invalidate();
    },
  });
}

/** Five steps, for a control on a device nobody can see yet (sections 44, 45). */
export const LEVELS = [0, 25, 50, 75, 100] as const;

/** The nearest step to a stored value, so a slider's 70 shows as 75. */
export function nearestLevel(value: number): number {
  return LEVELS.reduce((best, step) =>
    Math.abs(step - value) < Math.abs(best - value) ? step : best
  );
}
