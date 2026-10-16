/**
 * A caregiver proposes a reminder change (PRD 9, sections 20, 21, 73 and 85).
 *
 * Section 20's worked example, as a screen: the evening reminder from 7:00 PM to
 * 8:00 PM, with the current value shown so the caregiver knows what they are
 * changing.
 *
 * **It cannot propose a dose change.** Not because a check refuses one -- because
 * the only controls here are a time and a pause switch, the only action types the
 * app knows are the five section 85 allows, and the backend has no action type
 * for a dose at all.
 *
 * **A draft is kept and never applied** (section 73). What is stored is a
 * proposed time and a target id; the only thing that can turn one into a change is
 * the primary user pressing Approve, on the server. The draft also carries the
 * client id, so a send that timed out does not become two care requests
 * (section 74).
 */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { AppText, Button, Card, ListRow, Screen, ToggleRow } from '../../src/components';
import { CareErrorNote } from '../../src/features/caregivers/components/CaregiverCards';
import {
  PROPOSE_FAILED,
  PROPOSE_INTRO,
  PROPOSE_NO_SCHEDULE,
  PROPOSE_SEND,
  PROPOSE_SENT,
  SUGGESTION_CURRENT,
} from '../../src/features/caregivers/copy';
import { useCreateSuggestion } from '../../src/features/caregivers/hooks';
import {
  useCareFormStore,
  useSuggestionDraftStore,
} from '../../src/features/caregivers/stores';
import { spacing } from '../../src/theme/tokens';

/**
 * The times offered, on the hour and half hour.
 *
 * A list rather than a time picker: section 77 wants 48dp targets and screen
 * reader support, and a wheel picker is neither. A reminder nobody can set to
 * 7:17 PM is not a limitation anybody has noticed.
 */
const TIMES = [
  '06:00',
  '07:00',
  '08:00',
  '09:00',
  '12:00',
  '13:00',
  '17:00',
  '18:00',
  '19:00',
  '20:00',
  '21:00',
  '22:00',
];

function label(value: string): string {
  const hour = Number(value.slice(0, 2));
  const minute = value.slice(3, 5);
  const display = hour % 12 === 0 ? 12 : hour % 12;
  return `${display}:${minute} ${hour < 12 ? 'AM' : 'PM'}`;
}

export default function SuggestChangeScreen() {
  const { scheduleId, name, current } = useLocalSearchParams<{
    scheduleId?: string;
    name?: string;
    current?: string;
  }>();
  const router = useRouter();
  const create = useCreateSuggestion();
  const clearDraft = useSuggestionDraftStore((state) => state.clearDraft);

  // In the store rather than in component state: under React 19 a local
  // `useState` update from a fired event does not re-render, and these decide
  // which controls are on screen.
  const time = useCareFormStore((state) => state.suggestTime);
  const pause = useCareFormStore((state) => state.suggestPause);
  const setTime = useCareFormStore((state) => state.setSuggestTime);
  const setPause = useCareFormStore((state) => state.setSuggestPause);
  const resetSuggestion = useCareFormStore((state) => state.resetSuggestion);
  const [sent, setSent] = useState(false);
  const [failed, setFailed] = useState(false);

  if (!scheduleId) {
    return (
      <Screen>
        <Card>
          <AppText variant="body">{PROPOSE_NO_SCHEDULE}</AppText>
        </Card>
      </Screen>
    );
  }

  // Captured after the guard above: a function declaration is hoisted, so the
  // narrowing on `scheduleId` does not reach inside one.
  const target = scheduleId;

  function send() {
    // Read at press time, so a press arriving before the store update has
    // re-rendered still sends what was chosen.
    const state = useCareFormStore.getState();
    const pausing = state.suggestPause;
    const chosen = state.suggestTime;
    if (!pausing && chosen === null) return;
    setFailed(false);
    const clientSuggestionId = `sug-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const input = pausing
      ? {
          actionType: 'pause_medication_reminder' as const,
          targetResourceId: target,
          payload: {},
          clientSuggestionId,
        }
      : {
          actionType: 'change_medication_reminder_time' as const,
          targetResourceId: target,
          payload: { times: [{ time_of_day: chosen }] },
          clientSuggestionId,
        };
    create.mutate(input, {
      onSuccess: () => {
        clearDraft(target);
        resetSuggestion();
        setSent(true);
      },
      onError: () => setFailed(true),
    });
  }

  const canSend = (pause || time !== null) && !create.isPending;

  return (
    <Screen>
      <View style={{ gap: spacing.md }}>
        <AppText variant="title" accessibilityRole="header">
          {name ?? 'This reminder'}
        </AppText>
        <AppText variant="body" tone="secondary">
          {PROPOSE_INTRO}
        </AppText>

        {current ? (
          <Card style={{ gap: spacing.xxs }}>
            <AppText variant="caption" tone="secondary">
              {SUGGESTION_CURRENT}
            </AppText>
            <AppText variant="body">{current}</AppText>
          </Card>
        ) : null}

        <ToggleRow
          label="Suggest pausing these reminders instead"
          value={pause}
          onChange={(next) => {
            setPause(next);
            setSent(false);
          }}
        />

        {!pause ? (
          <View style={{ gap: spacing.xxs }}>
            <AppText variant="bodyStrong">Suggest a new time</AppText>
            {TIMES.map((option) => (
              <ListRow
                key={option}
                label={label(option)}
                role="radio"
                selected={time === option}
                onPress={() => {
                  setTime(option);
                  setSent(false);
                }}
              />
            ))}
          </View>
        ) : null}

        {failed ? <CareErrorNote message={PROPOSE_FAILED} /> : null}

        {sent ? (
          <Card style={{ gap: spacing.sm }}>
            <AppText variant="body">{PROPOSE_SENT}</AppText>
            <Button label="Done" onPress={() => router.back()} />
          </Card>
        ) : (
          <Button label={PROPOSE_SEND} onPress={send} disabled={!canSend} />
        )}
      </View>
    </Screen>
  );
}
