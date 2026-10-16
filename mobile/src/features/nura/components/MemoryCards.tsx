/**
 * The memory screen's rows, and the suggestion card (PRD 8, sections 43, 94).
 *
 * `MemoryRow` is section 43's layout: the sentence, and Edit and Remove. The
 * paused state is shown rather than hidden, because a memory switched off is
 * still something the user asked Nura to keep and finding it gone would be
 * worse than seeing it greyed.
 *
 * `MemorySuggestionCard` is section 94's exact shape -- a question, Remember,
 * Not now. It appears only after a reply and never saves anything on its own
 * (section 46).
 */
import { View } from 'react-native';

import { AppText, Button, Card } from '../../../components';
import { spacing } from '../../../theme/tokens';
import {
  EDIT_MEMORY,
  MEMORY_ACTIVE,
  MEMORY_PAUSED,
  MEMORY_SUGGESTION_TITLE,
  NOT_NOW,
  REMEMBER_THIS,
  REMOVE_MEMORY,
  REMOVE_MEMORY_HINT,
} from '../copy';
import type { Memory, MemorySuggestion } from '../types';

interface MemoryRowProps {
  memory: Memory;
  onEdit: () => void;
  onRemove: () => void;
  onToggle: (active: boolean) => void;
}

export function MemoryRow({ memory, onEdit, onRemove, onToggle }: MemoryRowProps) {
  return (
    <Card style={{ gap: spacing.xs }}>
      <AppText variant="body" tone={memory.isActive ? 'primary' : 'secondary'}>
        {memory.content}
      </AppText>

      <AppText variant="caption" tone="secondary">
        {memory.isActive ? MEMORY_ACTIVE : MEMORY_PAUSED}
      </AppText>

      <View style={{ flexDirection: 'row', gap: spacing.xs }}>
        <Button
          label={EDIT_MEMORY}
          variant="secondary"
          onPress={onEdit}
          accessibilityLabel={`${EDIT_MEMORY}: ${memory.content}`}
          style={{ flex: 1 }}
        />
        <Button
          label={memory.isActive ? MEMORY_PAUSED : MEMORY_ACTIVE}
          variant="secondary"
          onPress={() => onToggle(!memory.isActive)}
          accessibilityLabel={
            memory.isActive ? `Pause: ${memory.content}` : `Use again: ${memory.content}`
          }
          accessibilityHint={
            memory.isActive
              ? 'Stops Nura using this, without deleting it'
              : 'Lets Nura use this again'
          }
          style={{ flex: 1 }}
        />
        <Button
          label={REMOVE_MEMORY}
          variant="ghost"
          onPress={onRemove}
          accessibilityLabel={`${REMOVE_MEMORY}: ${memory.content}`}
          accessibilityHint={REMOVE_MEMORY_HINT}
          style={{ flex: 1 }}
        />
      </View>
    </Card>
  );
}

interface MemorySuggestionCardProps {
  suggestion: MemorySuggestion;
  onRemember: () => void;
  onDismiss: () => void;
  busy: boolean;
}

export function MemorySuggestionCard({
  suggestion,
  onRemember,
  onDismiss,
  busy,
}: MemorySuggestionCardProps) {
  return (
    <Card style={{ gap: spacing.sm }}>
      <AppText variant="bodyStrong">{MEMORY_SUGGESTION_TITLE}</AppText>
      <AppText variant="body" tone="secondary">
        {suggestion.content}
      </AppText>

      <View style={{ flexDirection: 'row', gap: spacing.xs }}>
        <Button
          label={REMEMBER_THIS}
          onPress={onRemember}
          disabled={busy}
          accessibilityHint="Adds this to what Nura remembers"
          style={{ flex: 1 }}
        />
        <Button
          label={NOT_NOW}
          variant="secondary"
          onPress={onDismiss}
          disabled={busy}
          accessibilityHint="Leaves it out"
          style={{ flex: 1 }}
        />
      </View>
    </Card>
  );
}
