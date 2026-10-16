/**
 * Where a message is typed (PRD 8, sections 6, 56, 57 and 83).
 *
 * The text lives in `composerStore`, not in component state. Two reasons, and
 * both matter: section 57 asks for an unsent message to survive the app
 * backgrounding, and a store update re-renders under React 19 where a local
 * `useState` update from a fired event does not -- which is what makes this
 * testable.
 *
 * Send is disabled while a reply is in flight and while the field is empty,
 * and it says why through `accessibilityState` rather than only by going
 * grey. Offline it is disabled too, with the banner above saying what is
 * saved and what is not (section 56).
 */
import { View } from 'react-native';

import { AppText, Button, TextField } from '../../../components';
import { spacing } from '../../../theme/tokens';
import { COMPOSER_LABEL, COMPOSER_PLACEHOLDER, DRAFT_SAVED, SEND } from '../copy';
import { useComposerStore, useDraft } from '../composerStore';

/** Matches the backend's own limit, so a refusal is never a surprise. */
export const MAX_MESSAGE_LENGTH = 4000;

interface ConversationComposerProps {
  conversationId: string;
  onSend: (text: string) => void;
  /** True while a reply is being waited for. */
  busy: boolean;
  /** True when there is no connection, or no provider configured. */
  disabled: boolean;
}

export function ConversationComposer({
  conversationId,
  onSend,
  busy,
  disabled,
}: ConversationComposerProps) {
  const draft = useDraft(conversationId);
  const setDraft = useComposerStore((state) => state.setDraft);

  const trimmed = draft.trim();
  const canSend = trimmed.length > 0 && !busy && !disabled;

  return (
    <View style={{ gap: spacing.xs }}>
      <TextField
        label={COMPOSER_LABEL}
        placeholder={COMPOSER_PLACEHOLDER}
        value={draft}
        onChangeText={(text) => setDraft(conversationId, text)}
        multiline
        maxLength={MAX_MESSAGE_LENGTH}
        editable={!busy}
      />

      {/* Only shown when there is something to lose. Saying "saved on this
          phone" over an empty field would be a claim about nothing. */}
      {disabled && trimmed.length > 0 ? (
        <AppText variant="caption" tone="secondary">
          {DRAFT_SAVED}
        </AppText>
      ) : null}

      <Button
        label={SEND}
        onPress={() => {
          if (!canSend) return;
          // Read at press time rather than from the render closure: a press
          // arriving before a store update has re-rendered would otherwise
          // send the text as it was a keystroke ago.
          const current = useComposerStore.getState().drafts[conversationId] ?? '';
          const message = current.trim();
          if (message.length === 0) return;
          onSend(message);
        }}
        disabled={!canSend}
        accessibilityHint="Sends your message to Nura"
      />
    </View>
  );
}
