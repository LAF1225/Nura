/**
 * How a robot's connection is described everywhere in the app
 * (PRD 2, sections 46-47): calm words, an icon as well as a colour, and the
 * status always as reported by the backend.
 */
import type { ConnectionStatus } from '../types/device';
import { timeAgo } from '../utils/time';
import { StatusChip } from './StatusChip';

export function connectionLabel(status: ConnectionStatus): string {
  switch (status) {
    case 'online':
      return 'Online';
    case 'offline':
      return 'Offline';
    default:
      return 'Not connected yet';
  }
}

/** "Nura is currently offline." / "Last connected 12 minutes ago." */
export function connectionSentence(
  displayName: string,
  status: ConnectionStatus,
  lastSeenAt: string | null,
  now: number = Date.now()
): string {
  if (status === 'online') return `${displayName} is online.`;
  if (status === 'offline') {
    const since = lastSeenAt ? ` Last connected ${timeAgo(lastSeenAt, now)}.` : '';
    return `${displayName} is currently offline.${since}`;
  }
  return `${displayName} hasn’t connected yet.`;
}

export function ConnectionChip({ status }: { status: ConnectionStatus }) {
  return (
    <StatusChip
      label={connectionLabel(status)}
      tone={status === 'online' ? 'success' : status === 'offline' ? 'warning' : 'neutral'}
      icon={
        status === 'online' ? 'wifi' : status === 'offline' ? 'cloud-offline-outline' : undefined
      }
    />
  );
}
