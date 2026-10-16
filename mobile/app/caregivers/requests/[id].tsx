/**
 * One care request, approved or declined (PRD 9, sections 24, 25, 77, 86 and 87).
 *
 * The diff is explicit and labelled -- "Now" and "Suggested" as separate lines
 * rather than two values side by side -- because section 77 asks for approval
 * dialogs that clearly state what will change, and a screen reader cannot convey
 * a visual comparison.
 *
 * **Approve is never automatic** (section 87). There is no auto-apply, no
 * countdown and no default action; the only thing that changes a record is a
 * press. If the target has gone since the suggestion was made, Approve is not
 * offered at all -- the server would refuse it, and offering a button that
 * cannot work is worse than saying why.
 *
 * **The decline note is private** (sections 25 and 88). The hint under the field
 * says so, and the caregiver's own view of this suggestion has no field for it.
 */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import {
  AppText,
  AsyncState,
  Button,
  Card,
  Screen,
  TextField,
} from '../../../src/components';
import {
  CareErrorNote,
  SuggestionCard,
} from '../../../src/features/caregivers/components/CaregiverCards';
import {
  APPROVE_BUTTON,
  APPROVE_FAILED,
  DECLINE_FAILED,
  DECLINE_NOTE_HINT,
  DECLINE_NOTE_LABEL,
  DECLINE_SUGGESTION_BUTTON,
  SUGGESTION_TARGET_MISSING,
} from '../../../src/features/caregivers/copy';
import {
  useApproveSuggestion,
  useDeclineSuggestion,
  useSuggestions,
} from '../../../src/features/caregivers/hooks';
import { useCareFormStore } from '../../../src/features/caregivers/stores';
import { spacing } from '../../../src/theme/tokens';

export default function CareRequestScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const suggestionId = id ?? '';
  const router = useRouter();
  const suggestions = useSuggestions();
  const approve = useApproveSuggestion();
  const decline = useDeclineSuggestion();
  const note = useCareFormStore((state) => state.declineNote);
  const setNote = useCareFormStore((state) => state.setDeclineNote);
  const [failed, setFailed] = useState<string | null>(null);

  const suggestion = (suggestions.data?.suggestions ?? []).find(
    (row) => row.id === suggestionId
  );
  const answered = suggestion !== undefined && suggestion.status !== 'pending';
  const missing = suggestion?.diff.targetMissing === true;

  return (
    <Screen
      onRefresh={() => void suggestions.refetch()}
      refreshing={suggestions.isRefetching && !suggestions.isLoading}
    >
      <AsyncState
        status={suggestions.isError ? 'error' : 'success'}
        error={suggestions.error}
        isEmpty={suggestion === undefined}
        emptyMessage="That care request is no longer here."
        loadingLabel="Loading care request"
        onRetry={() => void suggestions.refetch()}
      >
        {suggestion === undefined ? null : (
          <View style={{ gap: spacing.lg }}>
            <SuggestionCard suggestion={suggestion} />

            {missing ? (
              <Card>
                <AppText variant="body">{SUGGESTION_TARGET_MISSING}</AppText>
              </Card>
            ) : null}

            {answered ? (
              suggestion.declineNote ? (
                <Card style={{ gap: spacing.xxs }}>
                  <AppText variant="bodyStrong">Your note</AppText>
                  <AppText variant="body" tone="secondary">
                    {suggestion.declineNote}
                  </AppText>
                </Card>
              ) : null
            ) : (
              <View style={{ gap: spacing.md }}>
                {!missing ? (
                  <Button
                    label={APPROVE_BUTTON}
                    onPress={() => {
                      setFailed(null);
                      approve.mutate(suggestionId, {
                        onSuccess: () => router.back(),
                        onError: () => setFailed(APPROVE_FAILED),
                      });
                    }}
                    disabled={approve.isPending}
                    accessibilityHint={`Changes ${suggestion.diff.subject} to ${suggestion.diff.proposed}`}
                  />
                ) : null}

                <TextField
                  label={DECLINE_NOTE_LABEL}
                  hint={DECLINE_NOTE_HINT}
                  value={note}
                  onChangeText={setNote}
                  multiline
                />
                <Button
                  label={DECLINE_SUGGESTION_BUTTON}
                  variant="secondary"
                  onPress={() => {
                    // Read at press time, for the usual React 19 reason.
                    const typed = useCareFormStore.getState().declineNote.trim();
                    setFailed(null);
                    decline.mutate(
                      { suggestionId, note: typed.length > 0 ? typed : null },
                      {
                        onSuccess: () => {
                          setNote('');
                          router.back();
                        },
                        onError: () => setFailed(DECLINE_FAILED),
                      }
                    );
                  }}
                  disabled={decline.isPending}
                />
              </View>
            )}

            {failed !== null ? <CareErrorNote message={failed} /> : null}
          </View>
        )}
      </AsyncState>
    </Screen>
  );
}
