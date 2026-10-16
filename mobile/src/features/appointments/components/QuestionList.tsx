/**
 * The questions for the clinician (PRD 7, sections 23, 24, 39 and 62).
 *
 * The user's own list, in their own words and their own order. Nothing here
 * rewrites, merges, sorts by importance or suggests a better phrasing: this is
 * going to be read out in a consulting room by the person who wrote it.
 *
 * Suggestions are offered *underneath* the list rather than mixed into it, and
 * accepting one adds an ordinary question -- from then on indistinguishable from a
 * typed one, because at that point it is theirs (PRD 7, section 24).
 */
import { Ionicons } from '@expo/vector-icons';
import { Pressable, View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { Button } from '../../../components/Button';
import { useTheme } from '../../../theme';
import { iconSize, minTouchTarget, radius, spacing } from '../../../theme/tokens';
import { PENDING_LABEL } from '../copy';
import type { AppointmentQuestion, PendingQuestion, QuestionSuggestion } from '../types';

interface QuestionListProps {
  questions: AppointmentQuestion[];
  /** Questions saved on this phone and not yet on the server (s53). */
  pending?: PendingQuestion[];
  onDelete?: (questionId: string) => void;
  onToggleAnswered?: (question: AppointmentQuestion) => void;
  emptyMessage?: string;
}

export function QuestionList({
  questions,
  pending = [],
  onDelete,
  onToggleAnswered,
  emptyMessage = 'No questions yet.',
}: QuestionListProps) {
  const theme = useTheme();

  if (questions.length === 0 && pending.length === 0) {
    return (
      <AppText variant="body" tone="secondary">
        {emptyMessage}
      </AppText>
    );
  }

  return (
    <View style={{ gap: spacing.xs }}>
      {questions.map((question) => (
        <View
          key={question.id}
          style={{
            flexDirection: 'row',
            alignItems: 'flex-start',
            gap: spacing.sm,
            padding: spacing.md,
            borderRadius: radius.lg,
            borderWidth: 1,
            borderColor: theme.colors.border,
            backgroundColor: theme.colors.surface,
          }}
        >
          {onToggleAnswered ? (
            <Pressable
              onPress={() => onToggleAnswered(question)}
              accessibilityRole="checkbox"
              accessibilityLabel={`Answered: ${question.text}`}
              accessibilityState={{ checked: question.isAnswered }}
              accessibilityHint="Marks this question as answered"
              style={{
                minWidth: iconSize.md,
                minHeight: iconSize.md,
                justifyContent: 'center',
              }}
            >
              <Ionicons
                name={question.isAnswered ? 'checkmark-circle' : 'ellipse-outline'}
                size={iconSize.md}
                color={
                  question.isAnswered ? theme.colors.accent : theme.colors.textSecondary
                }
              />
            </Pressable>
          ) : null}

          <View style={{ flex: 1, gap: spacing.xxs }}>
            <AppText variant="body">{question.text}</AppText>
            {question.answerNote ? (
              <AppText variant="caption" tone="secondary">
                {`Their answer: ${question.answerNote}`}
              </AppText>
            ) : null}
          </View>

          {onDelete ? (
            <Pressable
              onPress={() => onDelete(question.id)}
              accessibilityRole="button"
              accessibilityLabel={`Remove question: ${question.text}`}
              accessibilityHint="Removes this question from the list"
              style={{
                minWidth: minTouchTarget / 2,
                minHeight: minTouchTarget / 2,
                alignItems: 'flex-end',
                justifyContent: 'center',
              }}
            >
              <Ionicons
                name="close"
                size={iconSize.md}
                color={theme.colors.textSecondary}
              />
            </Pressable>
          ) : null}
        </View>
      ))}

      {pending.map((question) => (
        <View
          key={question.clientQuestionId}
          style={{
            gap: spacing.xxs,
            padding: spacing.md,
            borderRadius: radius.lg,
            borderWidth: 1,
            borderStyle: 'dashed',
            borderColor: theme.colors.border,
          }}
        >
          <AppText variant="body">{question.text}</AppText>
          <AppText variant="caption" tone="secondary">
            {PENDING_LABEL}
          </AppText>
        </View>
      ))}
    </View>
  );
}

interface SuggestionListProps {
  suggestions: QuestionSuggestion[];
  onAccept: (suggestion: QuestionSuggestion) => void;
}

/**
 * The deterministic prompts (PRD 7, section 24).
 *
 * Each one is an offer with a button. Nothing is added until it is pressed, and
 * there is no "add all" -- the opting in is the point.
 */
export function SuggestionList({ suggestions, onAccept }: SuggestionListProps) {
  if (suggestions.length === 0) return null;

  return (
    <View style={{ gap: spacing.xs }}>
      <AppText variant="caption" tone="secondary">
        Nura can add one of these for you
      </AppText>
      {suggestions.map((suggestion) => (
        <View key={suggestion.key} style={{ gap: spacing.xxs }}>
          <AppText variant="body" tone="secondary">
            {suggestion.prompt}
          </AppText>
          <Button
            label="Add this question"
            variant="secondary"
            onPress={() => onAccept(suggestion)}
            accessibilityLabel={`Add question: ${suggestion.questionText}`}
            accessibilityHint="Adds this to your list of questions"
          />
        </View>
      ))}
    </View>
  );
}
