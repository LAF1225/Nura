/**
 * Custom instructions (PRD 8, sections 25, 26 and 63).
 *
 * A single free-text field, the examples the PRD lists, and one thing worth
 * reading: **a refused instruction is shown as refused.**
 *
 * Section 26 allows rejecting *or* safely ignoring an instruction that tries
 * to disable safety, reveal how Nura is set up, or reach somebody else's
 * data. The backend rejects, and this screen shows the reason, because
 * somebody who types "act as my doctor" and is quietly ignored will believe
 * it worked -- and will read the next answer as a doctor's.
 */
import { View } from 'react-native';

import { AppText, Button, Card, Screen, TextField } from '../../src/components';
import {
  INSTRUCTIONS_INTRO,
  INSTRUCTIONS_LABEL,
  INSTRUCTIONS_LIMIT_NOTE,
  INSTRUCTIONS_PLACEHOLDER,
  INSTRUCTION_EXAMPLES,
  SAVE,
  SAVED,
  SAVE_FAILED,
  UNSAFE_INSTRUCTION,
} from '../../src/features/nura/copy';
import { useEditorStore } from '../../src/features/nura/editorStore';
import {
  useAssistantPreferences,
  useUpdatePreferences,
} from '../../src/features/nura/hooks';
import { ApiError } from '../../src/services/api/errors';
import { spacing } from '../../src/theme/tokens';

/** Matches the backend's own limit, so a refusal is never a surprise. */
const MAX_LENGTH = 2000;

export default function InstructionsScreen() {
  const preferences = useAssistantPreferences();
  const update = useUpdatePreferences();

  const typed = useEditorStore((state) => state.instructions);
  const error = useEditorStore((state) => state.instructionsError);
  const saved = useEditorStore((state) => state.instructionsSaved);
  const setInstructions = useEditorStore((state) => state.setInstructions);
  const setError = useEditorStore((state) => state.setInstructionsError);
  const markSaved = useEditorStore((state) => state.markInstructionsSaved);

  // The server's value shows through until the field is touched, so a
  // refetch landing mid-sentence cannot overwrite what is being typed.
  const value = typed ?? preferences.data?.customInstructions ?? '';

  return (
    <Screen>
      <View style={{ gap: spacing.md }}>
        <AppText variant="body" tone="secondary">
          {INSTRUCTIONS_INTRO}
        </AppText>

        <TextField
          label={INSTRUCTIONS_LABEL}
          placeholder={INSTRUCTIONS_PLACEHOLDER}
          value={value}
          onChangeText={setInstructions}
          multiline
          maxLength={MAX_LENGTH}
          error={error}
        />

        <Button
          label={saved ? SAVED : SAVE}
          disabled={update.isPending}
          onPress={() => {
            // Read at press time, for the same reason the memory screen does.
            const state = useEditorStore.getState();
            const current =
              state.instructions ?? preferences.data?.customInstructions ?? '';
            update.mutate(
              { customInstructions: current.trim() },
              {
                onSuccess: markSaved,
                onError: (failure) => {
                  // The one refusal worth its own sentence. Anything else is
                  // a transport problem and reads as one.
                  const refused =
                    failure instanceof ApiError && failure.code === 'unsafe_instruction';
                  setError(refused ? UNSAFE_INSTRUCTION : SAVE_FAILED);
                },
              }
            );
          }}
          accessibilityHint="Saves how Nura should talk with you"
        />

        <Card style={{ gap: spacing.xxs }}>
          <AppText variant="bodyStrong">Examples</AppText>
          {INSTRUCTION_EXAMPLES.map((example) => (
            <AppText key={example} variant="body" tone="secondary">
              {`• ${example}`}
            </AppText>
          ))}
        </Card>

        <AppText variant="caption" tone="secondary">
          {INSTRUCTIONS_LIMIT_NOTE}
        </AppText>
      </View>
    </Screen>
  );
}
