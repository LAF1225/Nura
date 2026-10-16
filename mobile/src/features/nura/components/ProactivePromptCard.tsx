/**
 * One thing Nura is offering to help with (PRD 8, sections 35 and 36).
 *
 * Everything in it came from data the app already holds -- an appointment
 * tomorrow with nothing prepared, a check-in not done, a medication running
 * low. No model wrote the sentence and none of it is a conclusion about
 * health (section 35).
 *
 * "Not now" is not a close button: it posts a dismissal, so the same prompt
 * about the same thing does not come back (section 36). Saying so in the
 * hint matters, because a card that reappears after being waved away is the
 * behaviour section 36 exists to prevent.
 */
import { View } from 'react-native';

import { AppText, Button, Card } from '../../../components';
import { spacing } from '../../../theme/tokens';
import { DISMISS_PROMPT } from '../copy';
import type { ProactivePrompt } from '../types';

interface ProactivePromptCardProps {
  prompt: ProactivePrompt;
  onAct: () => void;
  onDismiss: () => void;
}

export function ProactivePromptCard({
  prompt,
  onAct,
  onDismiss,
}: ProactivePromptCardProps) {
  return (
    <Card style={{ gap: spacing.sm }}>
      <AppText variant="body">{prompt.text}</AppText>

      <View style={{ flexDirection: 'row', gap: spacing.xs }}>
        {prompt.route !== null && prompt.actionLabel !== null ? (
          <Button
            label={prompt.actionLabel}
            onPress={onAct}
            accessibilityLabel={`${prompt.actionLabel}: ${prompt.text}`}
            style={{ flex: 1 }}
          />
        ) : null}
        <Button
          label={DISMISS_PROMPT}
          variant="secondary"
          onPress={onDismiss}
          accessibilityLabel={`${DISMISS_PROMPT}: ${prompt.text}`}
          accessibilityHint="Stops Nura mentioning this one again"
          style={{ flex: 1 }}
        />
      </View>
    </Card>
  );
}
