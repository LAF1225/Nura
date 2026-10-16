/**
 * "Something is not working, and here is what that means" (PRD 13, s34, s35).
 *
 * PRD 3 shipped `OfflineBanner`, which says one sentence: you are offline, some
 * information may be out of date. It is used on ten screens and it is right on
 * all of them. What it cannot say is the other two things PRD 13 section 34
 * asks for -- the server being unreachable while the phone is online, and a
 * robot being offline while the app is fine -- because those are different
 * facts with different consequences.
 *
 * So this takes a `kind` rather than new copy per screen, and `OfflineBanner`
 * is now a thin call into it. Three decisions:
 *
 * **Every sentence says what still works.** Section 35 forbids showing a
 * pending action as saved; the flip side is not frightening somebody about a
 * robot when their medication list is fine. "Robot offline. App features are
 * still available." is section 34's own example, and the shape is deliberate:
 * the fact, then the reassurance.
 *
 * **Nothing here is a safety sentence.** Section 34 allows a high-risk feature
 * to override with more specific wording, and PRD 10 already does: its own
 * `OFFLINE_BODY` says Nura cannot record or send an emergency request and to
 * call somebody directly. That is a stronger claim than any banner should make
 * generically, and it stays where it is -- `safety` here points at it rather
 * than restating it.
 *
 * **It announces politely.** `accessibilityLiveRegion="polite"` so a screen
 * reader mentions it without pulling focus from whatever somebody was doing,
 * which is what PRD 3 chose and what section 29 of PRD 14 will check by hand.
 */
import { Ionicons } from '@expo/vector-icons';
import { View } from 'react-native';

import { useTheme } from '../theme';
import { iconSize, radius, spacing } from '../theme/tokens';
import { AppText } from './AppText';

/** What is wrong. One per kind of degradation, not one per screen. */
export type DegradedKind =
  /** The phone has no connection. */
  | 'offline'
  /** The phone is online and Nura's server did not answer. */
  | 'unavailable'
  /** Something is queued on this phone and has not reached the server. */
  | 'pending'
  /** A robot is linked and has not been heard from. */
  | 'robotOffline';

interface Message {
  icon: keyof typeof Ionicons.glyphMap;
  text: string;
}

/**
 * The sentences, in one place.
 *
 * Section 35's vocabulary: "will sync later" rather than "saved", "may not
 * work" rather than "is broken". Each one states a fact and then what is still
 * true, because a banner that only states the fact leaves somebody to guess
 * the consequence -- and they usually guess worse than it is.
 */
export const DEGRADED_MESSAGES: Readonly<Record<DegradedKind, Message>> = {
  offline: {
    icon: 'cloud-offline-outline',
    text: 'You’re offline. Some information may be out of date, and changes will sync later.',
  },
  unavailable: {
    icon: 'alert-circle-outline',
    text: 'Nura’s server is unavailable. You can keep using the app, and changes will sync when it comes back.',
  },
  pending: {
    icon: 'time-outline',
    text: 'Some changes are waiting to sync. They’re saved on this phone.',
  },
  robotOffline: {
    icon: 'hardware-chip-outline',
    text: 'Nura Device is offline. App features are still available.',
  },
};

interface Props {
  kind: DegradedKind;
  /**
   * More specific wording, for a feature where the generic sentence would be
   * an understatement. Section 34 allows this; PRD 10's safety screens are
   * why it exists.
   */
  message?: string;
}

export function DegradedModeBanner({ kind, message }: Props) {
  const theme = useTheme();
  const fallback = DEGRADED_MESSAGES[kind];

  return (
    <View
      accessible
      accessibilityLiveRegion="polite"
      accessibilityRole="alert"
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.sm,
        padding: spacing.sm,
        marginBottom: spacing.md,
        borderRadius: radius.md,
        backgroundColor: theme.colors.surfaceSecondary,
        borderWidth: 1,
        borderColor: theme.colors.border,
      }}
    >
      <Ionicons
        name={fallback.icon}
        size={iconSize.md}
        color={theme.colors.textSecondary}
      />
      <AppText variant="caption" tone="secondary" style={{ flex: 1 }}>
        {message ?? fallback.text}
      </AppText>
    </View>
  );
}
