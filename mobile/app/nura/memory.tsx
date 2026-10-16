/**
 * What Nura remembers (PRD 8, sections 40-47).
 *
 * The intro is the part that earns its place. Section 40 draws a line between
 * memory and health data, and a user looking at this screen is entitled to
 * know which side their diagnoses are on -- so the screen says it: this is a
 * list of how you like to be spoken to, and your records are kept separately.
 *
 * Three actions per memory, from section 43 plus one. Edit and Remove are the
 * PRD's; pausing is ours, because turning a memory off must stop it reaching
 * the model (section 47) and being able to turn it back on without retyping
 * it is worth a button.
 *
 * A refusal is shown rather than swallowed. Section 26 allows rejecting or
 * safely ignoring an instruction that tries to move the medical boundary;
 * somebody who writes "Nura should diagnose me" and hears nothing will
 * believe it worked.
 */
import { View } from 'react-native';

import {
  AppText,
  AsyncState,
  Button,
  Card,
  Screen,
  SkeletonCard,
  TextField,
} from '../../src/components';
import { MemoryRow } from '../../src/features/nura/components/MemoryCards';
import {
  ADD_MEMORY,
  CANCEL,
  MEMORY_EMPTY,
  MEMORY_FULL,
  MEMORY_INTRO,
  MEMORY_LABEL,
  MEMORY_PLACEHOLDER,
  SAVE,
  SAVE_FAILED,
  UNSAFE_INSTRUCTION,
} from '../../src/features/nura/copy';
import { useEditorStore } from '../../src/features/nura/editorStore';
import {
  useAddMemory,
  useMemories,
  useRemoveMemory,
  useUpdateMemory,
} from '../../src/features/nura/hooks';
import { ApiError } from '../../src/services/api/errors';
import { spacing } from '../../src/theme/tokens';

/** Matches the backend's own limit, so a refusal is never a surprise. */
const MAX_LENGTH = 300;

export default function MemoryScreen() {
  const list = useMemories();
  const add = useAddMemory();
  const update = useUpdateMemory();
  const remove = useRemoveMemory();

  const draft = useEditorStore((state) => state.memoryDraft);
  const editingId = useEditorStore((state) => state.memoryEditingId);
  const error = useEditorStore((state) => state.memoryError);
  const setDraft = useEditorStore((state) => state.setMemoryDraft);
  const startEditing = useEditorStore((state) => state.startEditingMemory);
  const stopEditing = useEditorStore((state) => state.stopEditingMemory);
  const setError = useEditorStore((state) => state.setMemoryError);

  const memories = list.data?.memories ?? [];

  const failed = (failure: unknown) => {
    if (failure instanceof ApiError && failure.code === 'unsafe_instruction') {
      setError(UNSAFE_INSTRUCTION);
      return;
    }
    if (failure instanceof ApiError && failure.code === 'too_many_memories') {
      setError(MEMORY_FULL);
      return;
    }
    setError(SAVE_FAILED);
  };

  const submit = () => {
    // Read at press time rather than from the render closure: a press
    // arriving before the store update has re-rendered would otherwise save
    // the text as it was a keystroke ago.
    const state = useEditorStore.getState();
    const content = state.memoryDraft.trim();
    if (content.length === 0) return;

    if (state.memoryEditingId !== null) {
      update.mutate(
        { id: state.memoryEditingId, content },
        { onSuccess: stopEditing, onError: failed }
      );
      return;
    }
    add.mutate(
      { content, category: 'preferences', source: 'user' },
      { onSuccess: stopEditing, onError: failed }
    );
  };

  return (
    <Screen
      onRefresh={() => void list.refetch()}
      refreshing={list.isRefetching && !list.isLoading}
    >
      <View style={{ gap: spacing.md }}>
        <AppText variant="body" tone="secondary">
          {MEMORY_INTRO}
        </AppText>

        <Card style={{ gap: spacing.sm }}>
          <TextField
            label={MEMORY_LABEL}
            placeholder={MEMORY_PLACEHOLDER}
            value={draft}
            onChangeText={setDraft}
            maxLength={MAX_LENGTH}
            error={error}
          />
          <View style={{ flexDirection: 'row', gap: spacing.xs }}>
            <Button
              label={editingId === null ? ADD_MEMORY : SAVE}
              onPress={submit}
              disabled={draft.trim().length === 0 || add.isPending || update.isPending}
              style={{ flex: 1 }}
            />
            {editingId !== null ? (
              <Button
                label={CANCEL}
                variant="secondary"
                onPress={stopEditing}
                style={{ flex: 1 }}
              />
            ) : null}
          </View>
        </Card>

        {list.isLoading ? (
          <Card>
            <SkeletonCard lines={3} />
          </Card>
        ) : (
          <AsyncState
            status={list.isError ? 'error' : 'success'}
            error={list.error}
            isEmpty={memories.length === 0}
            emptyMessage={MEMORY_EMPTY}
            onRetry={() => void list.refetch()}
          >
            <View style={{ gap: spacing.xs }}>
              {memories.map((memory) => (
                <MemoryRow
                  key={memory.id}
                  memory={memory}
                  onEdit={() => startEditing(memory.id, memory.content)}
                  onRemove={() => remove.mutate(memory.id)}
                  onToggle={(isActive) => update.mutate({ id: memory.id, isActive })}
                />
              ))}
            </View>
          </AsyncState>
        )}
      </View>
    </Screen>
  );
}
