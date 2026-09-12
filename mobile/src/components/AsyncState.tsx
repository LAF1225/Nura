/**
 * Renders the five states every asynchronous screen needs: idle, loading,
 * success, empty and error (PRD 0, section 20).
 *
 * Error text always comes from `apiErrorMessage`, so a raw JavaScript
 * exception is never put in front of a user.
 */
import type { ReactNode } from 'react';
import { ActivityIndicator, View } from 'react-native';

import { apiErrorMessage } from '../services/api';
import { useTheme } from '../theme';
import { spacing } from '../theme/tokens';
import { AppText } from './AppText';
import { Button } from './Button';

export type AsyncStatus = 'idle' | 'loading' | 'success' | 'error';

interface AsyncStateProps {
  status: AsyncStatus;
  /** Any thrown value; it is mapped to friendly wording, never shown raw. */
  error?: unknown;
  /** True when the request succeeded but there is nothing to show. */
  isEmpty?: boolean;
  emptyMessage?: string;
  loadingLabel?: string;
  onRetry?: () => void;
  /** Rendered on success. */
  children: ReactNode;
}

export function AsyncState({
  status,
  error,
  isEmpty = false,
  emptyMessage = 'Nothing here yet.',
  loadingLabel = 'Loading',
  onRetry,
  children,
}: AsyncStateProps) {
  const theme = useTheme();

  if (status === 'idle') {
    return null;
  }

  if (status === 'loading') {
    return (
      <View
        accessibilityRole="progressbar"
        accessibilityLabel={loadingLabel}
        style={{ paddingVertical: spacing.lg, gap: spacing.xs, alignItems: 'center' }}
      >
        <ActivityIndicator color={theme.colors.accent} />
        <AppText variant="caption" tone="secondary">
          {loadingLabel}
        </AppText>
      </View>
    );
  }

  if (status === 'error') {
    return (
      <View style={{ paddingVertical: spacing.md, gap: spacing.sm }}>
        <AppText variant="body" tone="secondary">
          {apiErrorMessage(error)}
        </AppText>
        {onRetry ? (
          <Button label="Try again" variant="secondary" onPress={onRetry} />
        ) : null}
      </View>
    );
  }

  if (isEmpty) {
    return (
      <View style={{ paddingVertical: spacing.md }}>
        <AppText variant="body" tone="secondary">
          {emptyMessage}
        </AppText>
      </View>
    );
  }

  return <>{children}</>;
}
