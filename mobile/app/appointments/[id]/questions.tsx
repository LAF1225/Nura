/**
 * Questions for the clinician (PRD 7, sections 22-24, 39 and 53).
 *
 * The user's own list, in their own words. Nothing rewrites a question, and the
 * suggestions sit underneath the list as offers with a button -- accepting one
 * writes an ordinary question, indistinguishable from a typed one, because from
 * then on it is theirs (PRD 7, section 24).
 *
 * A question added with no connection is kept on the phone and shown as such,
 * which is the draft PRD 7 section 53 names explicitly.
 *
 * The text box holds its own draft in local state. That is the one thing in this
 * feature a test cannot drive, for the React 19 reason recorded in the README: a
 * local `useState` update from a fired event does not re-render under Jest. The
 * function the Add button calls is exercised directly instead.
 */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import {
  AppText,
  Button,
  Card,
  Screen,
  SkeletonCard,
  TextField,
} from '../../../src/components';
import { OfflineBanner } from '../../../src/components/today';
import { PreparationProgress } from '../../../src/features/appointments/components/PreparationProgress';
import {
  QuestionList,
  SuggestionList,
} from '../../../src/features/appointments/components/QuestionList';
import { PENDING_HINT, QUESTIONS_INTRO } from '../../../src/features/appointments/copy';
import {
  useAddQuestion,
  useAppointment,
  useDeleteQuestion,
  usePendingQuestions,
  usePreparation,
  useUpdateQuestion,
} from '../../../src/features/appointments/hooks';
import { pendingForAppointment } from '../../../src/features/appointments/pending';
import { useReportSelectionStore } from '../../../src/features/appointments/selectionStore';
import { useIsOffline } from '../../../src/hooks/useNetworkStatus';
import { apiErrorMessage } from '../../../src/services/api';
import { spacing } from '../../../src/theme/tokens';

/** The question length the API accepts. Mirrored so a refusal is not the first
 *  thing the user hears about it. */
const QUESTION_MAX_LENGTH = 500;

export default function DoctorQuestionsScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const isOffline = useIsOffline();
  const [text, setText] = useState('');
  const [error, setError] = useState<string | null>(null);

  const appointmentId = id ?? '';
  const appointment = useAppointment(id);
  const preset = useReportSelectionStore((state) => state.preset);
  const preparation = usePreparation(id, {
    preset: preset === 'custom' ? '30_days' : preset,
  });
  const pending = usePendingQuestions();

  const add = useAddQuestion(appointmentId);
  const update = useUpdateQuestion(appointmentId);
  const remove = useDeleteQuestion(appointmentId);

  const questions = appointment.data?.questions ?? preparation.data?.questions ?? [];
  const queued = pendingForAppointment(pending.data ?? [], appointmentId);
  const suggestions = preparation.data?.suggestions ?? [];

  /** Adds a question. Exported through the button and used by the suggestions. */
  const addQuestion = (value: string) => {
    const trimmed = value.trim();
    if (trimmed.length === 0) return;
    setError(null);
    add.mutate(
      { text: trimmed },
      {
        onSuccess: () => setText(''),
        onError: (cause) => setError(apiErrorMessage(cause)),
      }
    );
  };

  return (
    <Screen
      onRefresh={() => void appointment.refetch()}
      refreshing={appointment.isRefetching && !appointment.isLoading}
    >
      <PreparationProgress current="questions" />

      {isOffline ? (
        <View style={{ gap: spacing.xs, marginTop: spacing.md }}>
          <OfflineBanner />
          <AppText variant="caption" tone="secondary">
            {PENDING_HINT}
          </AppText>
        </View>
      ) : null}

      <View style={{ height: spacing.lg }} />

      <Card style={{ gap: spacing.sm }}>
        <AppText variant="heading" accessibilityRole="header">
          {QUESTIONS_INTRO}
        </AppText>
        <AppText variant="caption" tone="secondary">
          Written exactly as you type them. Nura does not reword your questions.
        </AppText>

        <TextField
          label="Add a question"
          hint="For example, “Could this medication be contributing to my fatigue?”"
          value={text}
          onChangeText={setText}
          multiline
          numberOfLines={2}
          maxLength={QUESTION_MAX_LENGTH}
        />
        <Button
          label={add.isPending ? 'Adding…' : 'Add question'}
          onPress={() => addQuestion(text)}
          disabled={add.isPending}
          accessibilityHint="Adds this question to your list"
        />

        {error ? (
          <AppText variant="body" tone="secondary">
            {error}
          </AppText>
        ) : null}
      </Card>

      <View style={{ height: spacing.lg }} />

      {appointment.isLoading ? (
        <Card>
          <SkeletonCard lines={3} />
        </Card>
      ) : (
        <QuestionList
          questions={questions}
          pending={queued}
          onDelete={(questionId) =>
            remove.mutate(questionId, {
              onError: (cause) => setError(apiErrorMessage(cause)),
            })
          }
          onToggleAnswered={(question) =>
            update.mutate({
              questionId: question.id,
              patch: { is_answered: !question.isAnswered },
            })
          }
          emptyMessage="No questions yet. Add anything you want to remember to ask."
        />
      )}

      <View style={{ height: spacing.lg }} />

      <SuggestionList
        suggestions={suggestions}
        onAccept={(suggestion) => addQuestion(suggestion.questionText)}
      />

      <View style={{ height: spacing.lg }} />

      <Button
        label="Next: what to include"
        onPress={() =>
          router.push({
            pathname: '/appointments/[id]/select',
            params: { id: appointmentId },
          })
        }
        accessibilityHint="Goes to the sections that will appear in the summary"
      />
    </Screen>
  );
}
