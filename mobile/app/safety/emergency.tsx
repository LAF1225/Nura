/**
 * Emergency mode: what Nura actually did (PRD 10, §26, 42, 43, 44, 45, 68).
 *
 * **This screen reports; it does not reassure.** Every line in the escalation
 * list is the server's (section 42), and the ones that matter most are the
 * ones saying a channel is not set up. A screen that showed only the
 * successful halves would be the "Ayesha has been contacted" section 42
 * forbids, assembled from omissions instead of words.
 *
 * **Non-essential UI is gone** (section 43). No navigation, no suggestions,
 * nothing about medications or appointments. Two controls: say you are okay,
 * or cancel the request.
 *
 * **Cancelling asks first and says what it does not undo** (section 45).
 * Already-created alerts cannot be recalled, and the confirm step says so
 * rather than implying a clean stop.
 *
 * **The dialler is offered, and labelled honestly** (section 68). Tapping it
 * opens the phone's own dialler; Nura does not place the call, and the
 * sentence under it says exactly that.
 */
import { useRouter } from 'expo-router';
import { Linking, View } from 'react-native';

import { AppText, AsyncState, Button, Card, Screen } from '../../src/components';
import { useEmergencyContacts } from '../../src/features/caregivers/hooks';
import {
  EscalationStatusList,
  SafetyErrorNote,
} from '../../src/features/safety/components/SafetyCards';
import {
  alertCountSentence,
  CANCEL_BODY,
  CANCEL_CONFIRM,
  CANCEL_KEEP,
  CANCEL_TITLE,
  DIALER_NOTE,
  DIALER_TITLE,
  dialerLabel,
  EMERGENCY_ACKNOWLEDGED,
  EMERGENCY_IM_OKAY,
  EMERGENCY_SUBTITLE,
  EMERGENCY_TITLE,
} from '../../src/features/safety/copy';
import {
  useCancelSafetyEvent,
  useRespondToSafetyEvent,
  useSafetyStatus,
} from '../../src/features/safety/hooks';
import { useSafetyFormStore } from '../../src/features/safety/stores';
import { spacing } from '../../src/theme/tokens';

export default function EmergencyModeScreen() {
  const router = useRouter();
  const status = useSafetyStatus();
  const respond = useRespondToSafetyEvent();
  const cancel = useCancelSafetyEvent();
  const contacts = useEmergencyContacts();
  const confirming = useSafetyFormStore((state) => state.confirming);
  const confirm = useSafetyFormStore((state) => state.confirm);

  const data = status.data ?? null;
  const event = data?.activeEvent ?? null;
  const callable = (contacts.data?.contacts ?? []).filter(
    (contact) => contact.isActive && contact.phone
  );

  function pressCancel() {
    if (event === null) return;
    if (useSafetyFormStore.getState().confirming !== 'cancel') {
      confirm('cancel');
      return;
    }
    confirm('none');
    cancel.mutate(event.id, { onSuccess: () => router.back() });
  }

  function pressOkay() {
    if (event === null) return;
    respond.mutate(
      { eventId: event.id, response: 'im_okay' },
      { onSuccess: () => router.back() }
    );
  }

  return (
    <Screen
      onRefresh={() => void status.refetch()}
      refreshing={status.isRefetching && !status.isLoading}
    >
      <AsyncState
        status={status.isError ? 'error' : data ? 'success' : 'loading'}
        error={status.error}
        isEmpty={event === null}
        emptyMessage={EMERGENCY_ACKNOWLEDGED}
        loadingLabel="Loading"
        onRetry={() => void status.refetch()}
      >
        {event ? (
          <View style={{ gap: spacing.lg }}>
            <Card style={{ gap: spacing.xs }} accessible accessibilityRole="alert">
              <AppText variant="title" accessibilityRole="header">
                {EMERGENCY_TITLE}
              </AppText>
              <AppText variant="body" tone="secondary">
                {EMERGENCY_SUBTITLE}
              </AppText>
              <AppText variant="bodyStrong">{event.eventLabel}</AppText>
              {event.noResponseLabel ? (
                <AppText variant="body" tone="secondary">
                  {event.noResponseLabel}
                </AppText>
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

            {data?.noProvidersWarning ? (
              <Card accessible accessibilityRole="alert">
                <AppText variant="body">{data.noProvidersWarning}</AppText>
              </Card>
            ) : null}

            {callable.length > 0 ? (
              <Card style={{ gap: spacing.xs }}>
                <AppText variant="heading">{DIALER_TITLE}</AppText>
                <AppText variant="body" tone="secondary">
                  {DIALER_NOTE}
                </AppText>
                {callable.map((contact) => (
                  <Button
                    key={contact.id}
                    label={dialerLabel(contact.name)}
                    variant="secondary"
                    onPress={() => void Linking.openURL(`tel:${contact.phone}`)}
                    accessibilityHint={DIALER_NOTE}
                  />
                ))}
              </Card>
            ) : null}

            <View style={{ gap: spacing.sm }}>
              <Button
                label={EMERGENCY_IM_OKAY}
                onPress={pressOkay}
                disabled={respond.isPending}
              />
              {confirming === 'cancel' ? (
                <Card style={{ gap: spacing.xs }}>
                  <AppText variant="bodyStrong">{CANCEL_TITLE}</AppText>
                  <AppText variant="body" tone="secondary">
                    {CANCEL_BODY}
                  </AppText>
                  <Button
                    label={CANCEL_CONFIRM}
                    variant="secondary"
                    onPress={pressCancel}
                    disabled={cancel.isPending}
                  />
                  <Button
                    label={CANCEL_KEEP}
                    variant="ghost"
                    onPress={() => confirm('none')}
                  />
                </Card>
              ) : (
                <Button
                  label="Cancel this request"
                  variant="ghost"
                  onPress={pressCancel}
                />
              )}
            </View>

            {respond.isError || cancel.isError ? (
              <SafetyErrorNote message="That could not be recorded. Please try again." />
            ) : null}
          </View>
        ) : null}
      </AsyncState>
    </Screen>
  );
}
