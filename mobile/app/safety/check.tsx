/**
 * "Are you okay?" (PRD 10, sections 23, 24, 25, 26 and 118).
 *
 * **Two answers, and a dismissal.** Section 23's wording, with the optional
 * false-alarm dismissal it allows. Each is a full-width control with its own
 * label; nothing here is an icon or a colour, because this is the screen
 * somebody answers in forty-five seconds and possibly badly.
 *
 * **The countdown is text** (section 118). It is computed from the server's
 * `responseDeadlineAt` rather than from a timer this screen started, so it
 * says the same thing after a reload and it never decides on its own
 * authority that time is up -- the backend does that, and the worker does it
 * for somebody who is not looking at all (sections 28 and 80).
 *
 * **"I need help" does not ask again.** Section 26: skip the countdown,
 * escalate, show what actually happened. "I'm okay" does not ask again
 * either -- the person is the authority on that, and this is their own
 * screen, not a model's guess (which *is* confirmed; see the assistant's
 * tools).
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { AppText, AsyncState, Button, Card, Screen } from '../../src/components';
import {
  CountdownLine,
  SafetyErrorNote,
} from '../../src/features/safety/components/SafetyCards';
import {
  CHECK_FALSE_ALARM,
  CHECK_HELP,
  CHECK_OKAY,
  CHECK_TITLE,
} from '../../src/features/safety/copy';
import {
  secondsUntil,
  useRespondToSafetyEvent,
  useSafetyStatus,
} from '../../src/features/safety/hooks';
import { spacing } from '../../src/theme/tokens';
import type { UserResponse } from '../../src/features/safety/types';

export default function SafetyCheckScreen() {
  const router = useRouter();
  const status = useSafetyStatus();
  const respond = useRespondToSafetyEvent();

  const data = status.data ?? null;
  const event = data?.activeEvent ?? null;
  const waiting = event?.status === 'checking_user' || event?.status === 'second_prompt';
  const deadline =
    event?.status === 'second_prompt'
      ? event.secondPromptDeadlineAt
      : (event?.responseDeadlineAt ?? null);
  const left = waiting ? secondsUntil(deadline, new Date()) : null;

  function answer(response: UserResponse) {
    if (event === null) return;
    respond.mutate(
      { eventId: event.id, response },
      {
        onSuccess: (updated) => {
          // "I need help" leaves the event live and escalating, so the next
          // screen is the emergency one. Anything else has finished it.
          if (updated.status === 'escalating' || updated.status === 'escalated') {
            router.replace('/safety/emergency');
          } else {
            router.back();
          }
        },
      }
    );
  }

  return (
    <Screen>
      <AsyncState
        status={status.isError ? 'error' : data ? 'success' : 'loading'}
        error={status.error}
        isEmpty={event === null}
        emptyMessage="There is nothing to answer."
        loadingLabel="Loading"
        onRetry={() => void status.refetch()}
      >
        {event ? (
          <View style={{ gap: spacing.lg }}>
            <Card style={{ gap: spacing.sm }} accessible accessibilityRole="alert">
              <AppText variant="title" accessibilityRole="header">
                {CHECK_TITLE}
              </AppText>
              <AppText variant="body" tone="secondary">
                {data?.checkPrompt}
              </AppText>
              <AppText variant="caption" tone="secondary">
                {event.eventLabel}
              </AppText>
              <CountdownLine seconds={left} />
            </Card>

            <View style={{ gap: spacing.sm }}>
              <Button
                label={CHECK_OKAY}
                onPress={() => answer('im_okay')}
                disabled={respond.isPending}
              />
              <Button
                label={CHECK_HELP}
                variant="secondary"
                onPress={() => answer('need_help')}
                disabled={respond.isPending}
                accessibilityHint="Starts escalation straight away"
              />
              <Button
                label={CHECK_FALSE_ALARM}
                variant="ghost"
                onPress={() => answer('false_alarm')}
                disabled={respond.isPending}
              />
            </View>

            {respond.isError ? (
              <SafetyErrorNote message="That could not be recorded. Please try again." />
            ) : null}
          </View>
        ) : null}
      </AsyncState>
    </Screen>
  );
}
