/**
 * Cautious, non-diagnostic guidance (PRD 6, sections 42, 44, 45 and 77).
 *
 * The only component in the symptom feature that says anything back, and it says
 * exactly one of the reviewed sentences from `safetyMessages.ts` or from the
 * server's `safety.notice`. It never composes a sentence from the user's own
 * words, because a "notice" built from somebody's symptoms is a summary of their
 * symptoms sitting on a screen.
 *
 * **It never blocks anything** (PRD 6, section 77). It is a card above the Save
 * button, not a modal in front of it: somebody describing a worsening symptom
 * must still be able to finish describing it.
 *
 * `urgent` is false in every shipped build -- the red-flag rules are switched off
 * until a clinician has reviewed them (section 44) -- so in practice this renders
 * the quiet variant. The urgent variant exists so that turning the rules on is a
 * setting change rather than a code change, and it is still non-diagnostic: it
 * points at urgent care and names no cause.
 */
import { View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { Card } from '../../../components/Card';
import { useTheme } from '../../../theme';
import { spacing } from '../../../theme/tokens';

interface SafetyNoticeProps {
  /** One reviewed sentence, or null to draw nothing. */
  notice: string | null;
  /** True only when a reviewed rule fired on a deployment that enabled them. */
  urgent?: boolean;
}

export function SafetyNotice({ notice, urgent = false }: SafetyNoticeProps) {
  const theme = useTheme();
  if (notice === null) return null;

  return (
    <Card
      style={{
        gap: spacing.xxs,
        // A left edge rather than a filled warning colour. The quiet variant has
        // to read as information, because most of the time that is all it is.
        borderLeftWidth: 3,
        borderLeftColor: urgent ? theme.colors.danger : theme.colors.info,
      }}
    >
      <View accessibilityRole="alert" style={{ gap: spacing.xxs }}>
        <AppText variant="bodyStrong">
          {urgent ? 'Please get help now' : 'Something to keep an eye on'}
        </AppText>
        <AppText variant="body" tone="secondary">
          {notice}
        </AppText>
      </View>
    </Card>
  );
}
