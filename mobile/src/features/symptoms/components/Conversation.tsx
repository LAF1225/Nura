/**
 * The guided conversation's bubbles and answers (PRD 6, ss26, 66 and 67).
 *
 * Two components, both presentational: the whole conversation lives in the
 * store, so these render what they are given and report taps upward. That is
 * what lets the engine be tested without a renderer and the screen be tested
 * without the engine.
 *
 * Accessibility is the reason for several of the choices here (PRD 6, ss66, 67):
 *
 *   - Each bubble is one accessibility element with the speaker named, so a
 *     screen reader reads "Nura said…" then "You said…" in order rather than
 *     announcing a wall of unattributed text.
 *   - Every question offers tap choices *and* a text box. Somebody who finds
 *     typing hard can get through the whole flow by tapping (section 67).
 *   - Choices are buttons of at least 48dp, wrapping rather than scrolling
 *     sideways, so they still work at the largest text size.
 */
import { Pressable, View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { useTheme } from '../../../theme';
import { minTouchTarget, radius, spacing } from '../../../theme/tokens';
import type { ConversationChoice, ConversationTurn } from '../types';

interface ConversationBubbleProps {
  turn: ConversationTurn;
}

export function ConversationBubble({ turn }: ConversationBubbleProps) {
  const theme = useTheme();
  const fromNura = turn.speaker === 'nura';

  return (
    <View
      accessible
      accessibilityLabel={`${fromNura ? 'Nura said' : 'You said'}: ${turn.text}`}
      style={{
        alignSelf: fromNura ? 'flex-start' : 'flex-end',
        maxWidth: '88%',
        paddingVertical: spacing.sm,
        paddingHorizontal: spacing.md,
        borderRadius: radius.lg,
        backgroundColor: fromNura ? theme.colors.surface : theme.colors.surfaceSecondary,
        borderWidth: 1,
        borderColor: theme.colors.border,
      }}
    >
      <AppText variant="body">{turn.text}</AppText>
    </View>
  );
}

interface ConversationChoicesProps {
  choices: ConversationChoice[];
  onChoose: (choice: ConversationChoice) => void;
  disabled?: boolean;
}

export function ConversationChoices({
  choices,
  onChoose,
  disabled = false,
}: ConversationChoicesProps) {
  const theme = useTheme();
  if (choices.length === 0) return null;

  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs }}>
      {choices.map((choice) => (
        <Pressable
          key={choice.label}
          onPress={() => onChoose(choice)}
          disabled={disabled}
          accessibilityRole="button"
          accessibilityLabel={choice.label}
          style={{
            minHeight: minTouchTarget,
            justifyContent: 'center',
            paddingHorizontal: spacing.md,
            borderRadius: radius.pill,
            borderWidth: 1,
            borderColor: theme.colors.border,
            backgroundColor: theme.colors.surface,
            opacity: disabled ? 0.5 : 1,
          }}
        >
          <AppText variant="body">{choice.label}</AppText>
        </Pressable>
      ))}
    </View>
  );
}
