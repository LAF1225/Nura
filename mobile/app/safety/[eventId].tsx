/**
 * One safety event, in full (PRD 10, sections 47, 48 and 51).
 *
 * Section 51's layout: what it was, when it started, whether there was a
 * response, what the escalation did, and where it ended up. Every one of
 * those sentences comes from the server.
 *
 * **The false-alarm question is here rather than in a popup** (section 47).
 * It is asked after the event has finished, both answers are recorded --
 * "No / not sure" is a real answer, so "they said it was real" and "nobody
 * asked" stay different facts -- and the note says plainly that nothing
 * trains on it (section 48).
 */
import { useLocalSearchParams } from 'expo-router';
import { View } from 'react-native';

import { AppText, AsyncState, Button, Card, ListRow, Screen } from '../../src/components';
import {
  EscalationStatusList,
  SafetyErrorNote,
} from '../../src/features/safety/components/SafetyCards';
import { FALSE_POSITIVE_REASONS } from '../../src/features/safety/api';
import {
  alertCountSentence,
  FALSE_ALARM_NO,
  FALSE_ALARM_NOTE,
  FALSE_ALARM_REASON_TITLE,
  FALSE_ALARM_REASONS,
  FALSE_ALARM_TITLE,
  FALSE_ALARM_YES,
} from '../../src/features/safety/copy';
import { useMarkFalseAlarm, useSafetyEvent } from '../../src/features/safety/hooks';
import { useSafetyFormStore } from '../../src/features/safety/stores';
import { spacing } from '../../src/theme/tokens';

export default function SafetyEventScreen() {
  const params = useLocalSearchParams<{ eventId?: string }>();
  const eventId = typeof params.eventId === 'string' ? params.eventId : null;
  const query = useSafetyEvent(eventId);
  const mark = useMarkFalseAlarm();
  const reason = useSafetyFormStore((state) => state.falseAlarmReason);
  const setReason = useSafetyFormStore((state) => state.setFalseAlarmReason);

  const event = query.data ?? null;
  const finished = event?.status === 'resolved' || event?.status === 'cancelled';

  function answer(falsePositive: boolean) {
    if (event === null) return;
    mark.mutate({
      eventId: event.id,
      falsePositive,
      reason: falsePositive ? useSafetyFormStore.getState().falseAlarmReason : null,
    });
  }

  return (
    <Screen
      onRefresh={() => void query.refetch()}
      refreshing={query.isRefetching && !query.isLoading}
    >
      <AsyncState
        status={query.isError ? 'error' : event ? 'success' : 'loading'}
        error={query.error}
        loadingLabel="Loading safety event"
        onRetry={() => void query.refetch()}
      >
        {event ? (
          <View style={{ gap: spacing.md }}>
            <Card style={{ gap: spacing.xs }}>
              <AppText variant="heading">{event.eventLabel}</AppText>
              <AppText variant="body" tone="secondary">
                {event.description}
              </AppText>
              {event.noResponseLabel ? (
                <AppText variant="body" tone="secondary">
                  {event.noResponseLabel}
                </AppText>
              ) : null}
              {event.resolutionLabel ? (
                <AppText variant="body">{event.resolutionLabel}</AppText>
              ) : null}
            </Card>

            <Card style={{ gap: spacing.sm }}>
              <EscalationStatusList attempts={event.attempts} />
              <AppText variant="caption" tone="secondary">
                {alertCountSentence(event.alertCount)}
              </AppText>
              {event.escalationOutcomeLabel ? (
                <AppText variant="body" tone="secondary">
                  {event.escalationOutcomeLabel}
                </AppText>
              ) : null}
            </Card>

            {finished ? (
              <Card style={{ gap: spacing.xs }}>
                <AppText variant="heading">{FALSE_ALARM_TITLE}</AppText>
                {event.falsePositive === null ? (
                  <View style={{ gap: spacing.xs }}>
                    <AppText variant="body" tone="secondary">
                      {FALSE_ALARM_REASON_TITLE}
                    </AppText>
                    {FALSE_POSITIVE_REASONS.map((value) => (
                      <ListRow
                        key={value}
                        label={FALSE_ALARM_REASONS[value]}
                        role="radio"
                        selected={reason === value}
                        onPress={() => setReason(value)}
                      />
                    ))}
                    <Button
                      label={FALSE_ALARM_YES}
                      onPress={() => answer(true)}
                      disabled={mark.isPending}
                    />
                    <Button
                      label={FALSE_ALARM_NO}
                      variant="secondary"
                      onPress={() => answer(false)}
                      disabled={mark.isPending}
                    />
                  </View>
                ) : (
                  <AppText variant="body">
                    {event.falsePositive
                      ? `Marked as a false alarm${
                          event.falsePositiveReason
                            ? `: ${FALSE_ALARM_REASONS[event.falsePositiveReason]}`
                            : ''
                        }.`
                      : 'Recorded as not a false alarm.'}
                  </AppText>
                )}
                <AppText variant="caption" tone="secondary">
                  {FALSE_ALARM_NOTE}
                </AppText>
                {mark.isError ? (
                  <SafetyErrorNote message="That could not be saved. Please try again." />
                ) : null}
              </Card>
            ) : null}
          </View>
        ) : null}
      </AsyncState>
    </Screen>
  );
}
