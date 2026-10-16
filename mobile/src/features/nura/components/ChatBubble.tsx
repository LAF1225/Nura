/**
 * One line of a conversation (PRD 8, sections 6 and 83).
 *
 * Read as text, not as a picture of a chat. Accessibility (section 83) asks
 * for accessible chat ordering, so every bubble announces who is speaking
 * before what was said -- a screen reader user moving down a thread hears
 * "Nura said ..." and "You said ...", which is the information the visual
 * left/right split carries for everybody else.
 *
 * A `notice` is drawn differently on purpose. It is the product speaking, not
 * the model: "emergency escalation is not set up yet" (section 39), or what
 * happened after a Confirm. Giving it the same bubble as a generated reply
 * would blur a line worth keeping.
 */
import { View } from 'react-native';

import { AppText, Card } from '../../../components';
import { useTheme } from '../../../theme';
import { radius, spacing } from '../../../theme/tokens';
import { TRUNCATED_NOTE } from '../copy';
import type { Message } from '../types';

interface ChatBubbleProps {
  message: Message;
}

export function ChatBubble({ message }: ChatBubbleProps) {
  const theme = useTheme();
  const isUser = message.role === 'user';

  if (message.messageType === 'notice') {
    return (
      <Card
        accessible
        accessibilityLabel={`Nura: ${message.content}`}
        style={{
          backgroundColor: theme.colors.surfaceSecondary,
          borderLeftWidth: 3,
          borderLeftColor: theme.colors.accentStrong,
        }}
      >
        <AppText variant="body">{message.content}</AppText>
      </Card>
    );
  }

  return (
    <View
      accessible
      accessibilityLabel={`${isUser ? 'You' : 'Nura'}: ${message.content}`}
      style={{
        alignSelf: isUser ? 'flex-end' : 'flex-start',
        maxWidth: '88%',
        backgroundColor: isUser ? theme.colors.accentSoft : theme.colors.surfaceSecondary,
        borderRadius: radius.lg,
        paddingHorizontal: spacing.sm,
        paddingVertical: spacing.xs,
        gap: spacing.xxs,
      }}
    >
      <AppText variant="body">{message.content}</AppText>

      {message.meta.truncated ? (
        <AppText variant="caption" tone="secondary">
          {TRUNCATED_NOTE}
        </AppText>
      ) : null}
    </View>
  );
}
