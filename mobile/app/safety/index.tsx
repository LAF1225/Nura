/**
 * Safety: what is on, what is not, and how to ask for help.
 *
 * PRD 10, sections 4, 12, 13, 43, 59, 60, 62, 64, 66, 67, 70, 72, 73 and 74.
 *
 * **The SOS control is two taps, not a hold.** Section 13 allows either, and
 * press-and-hold is the one a screen reader cannot describe and a shaking
 * hand cannot complete (section 118). The second step says what it will do
 * and -- just as importantly -- what it will not: section 42's rule applies
 * before an emergency as much as during one, because somebody deciding
 * whether to press this needs to know nobody will be called.
 *
 * **Emergency mode minimises this screen rather than navigating away from
 * it** (section 43). When something is live it is the only thing here, with
 * one way into the detail. Pushing a route from an effect would mean a screen
 * that moves under somebody while they are reading it, which is the opposite
 * of what section 43 is asking for.
 *
 * **The warnings are the server's, and they are not decoration.** "There is
 * nobody to reach" (section 73) and "Nura cannot reach anybody" (section 74)
 * are computed from the chain and the providers, so they appear because they
 * are true rather than because a screen remembered them.
 *
 * **Offline is detected and said plainly** (section 67). A failed status read
 * means Nura cannot record an emergency request at all, and the screen says
 * so rather than offering a button that will fail.
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { AppText, AsyncState, Button, Card, Screen } from '../../src/components';
import {
  SafetyErrorNote,
  SafetyStatusCard,
  SafetyWarning,
} from '../../src/features/safety/components/SafetyCards';
import {
  CAPABILITIES_TITLE,
  CONTACTS_HINT,
  CONTACTS_LINK,
  EMERGENCY_TITLE,
  HISTORY_TITLE,
  MONITORING_OFF_HINT,
  OFFLINE_BODY,
  OFFLINE_TITLE,
  SAFETY_SUBTITLE,
  SOS_BUTTON,
  SOS_CONFIRM,
  SOS_CONFIRM_BODY,
  SOS_CONFIRM_TITLE,
  SOS_KEEP,
  SOS_TITLE,
  START_MONITORING,
  STOP_MONITORING,
  STOP_WITH_EVENT_BODY,
  STOP_WITH_EVENT_CONFIRM,
  STOP_WITH_EVENT_TITLE,
} from '../../src/features/safety/copy';
import {
  useRaiseSos,
  useSafetyStatus,
  useStopMonitoring,
} from '../../src/features/safety/hooks';
import { useSafetyFormStore } from '../../src/features/safety/stores';
import { spacing } from '../../src/theme/tokens';

export default function SafetyScreen() {
  const router = useRouter();
  const status = useSafetyStatus();
  const sos = useRaiseSos();
  const stop = useStopMonitoring();
  const confirming = useSafetyFormStore((state) => state.confirming);
  const confirm = useSafetyFormStore((state) => state.confirm);

  const data = status.data ?? null;
  const live = data?.activeEvent ?? null;
  const emergency = data?.emergencyMode === true;

  function pressSos() {
    // Read at press time rather than from the render that drew the button:
    // a press arriving before a store update has re-rendered would otherwise
    // see the previous step.
    if (useSafetyFormStore.getState().confirming !== 'sos') {
      confirm('sos');
      return;
    }
    confirm('none');
    sos.mutate(undefined, { onSuccess: () => router.push('/safety/emergency') });
  }

  function pressStop() {
    const hasEvent = live !== null;
    if (hasEvent && useSafetyFormStore.getState().confirming !== 'stop_with_event') {
      confirm('stop_with_event');
      return;
    }
    confirm('none');
    stop.mutate({ confirmActiveEvent: hasEvent });
  }

  return (
    <Screen
      onRefresh={() => void status.refetch()}
      refreshing={status.isRefetching && !status.isLoading}
    >
      <View style={{ gap: spacing.md }}>
        {status.isError ? (
          <Card style={{ gap: spacing.xs }} accessible accessibilityRole="alert">
            <AppText variant="bodyStrong">{OFFLINE_TITLE}</AppText>
            <AppText variant="body">{OFFLINE_BODY}</AppText>
            <Button
              label="Try again"
              variant="secondary"
              onPress={() => void status.refetch()}
            />
          </Card>
        ) : null}

        <AsyncState
          status={status.isError ? 'error' : data ? 'success' : 'loading'}
          error={status.error}
          loadingLabel="Loading safety"
          onRetry={() => void status.refetch()}
        >
          {data ? (
            <View style={{ gap: spacing.md }}>
              {live ? (
                <Card style={{ gap: spacing.sm }} accessible accessibilityRole="alert">
                  <AppText variant="heading">
                    {emergency ? EMERGENCY_TITLE : live.eventLabel}
                  </AppText>
                  <AppText variant="body" tone="secondary">
                    {emergency ? live.eventLabel : data.checkPrompt}
                  </AppText>
                  <Button
                    label={emergency ? 'Open emergency request' : 'Answer now'}
                    onPress={() =>
                      router.push(emergency ? '/safety/emergency' : '/safety/check')
                    }
                  />
                </Card>
              ) : null}

              {emergency ? null : (
                <AppText variant="body" tone="secondary">
                  {SAFETY_SUBTITLE}
                </AppText>
              )}

              <SafetyStatusCard status={data}>
                {data.monitoring ? (
                  confirming === 'stop_with_event' ? (
                    <View style={{ gap: spacing.xs }}>
                      <AppText variant="bodyStrong">{STOP_WITH_EVENT_TITLE}</AppText>
                      <AppText variant="body" tone="secondary">
                        {STOP_WITH_EVENT_BODY}
                      </AppText>
                      <Button
                        label={STOP_WITH_EVENT_CONFIRM}
                        variant="secondary"
                        onPress={pressStop}
                      />
                      <Button
                        label="Keep monitoring on"
                        variant="ghost"
                        onPress={() => confirm('none')}
                      />
                    </View>
                  ) : (
                    <Button
                      label={STOP_MONITORING}
                      variant="secondary"
                      onPress={pressStop}
                      disabled={stop.isPending}
                    />
                  )
                ) : (
                  <View style={{ gap: spacing.xs }}>
                    <AppText variant="body" tone="secondary">
                      {MONITORING_OFF_HINT}
                    </AppText>
                    <Button
                      label={START_MONITORING}
                      onPress={() => router.push('/safety/start')}
                      accessibilityHint="Choose how long, and how long Nura waits for an answer"
                    />
                  </View>
                )}
              </SafetyStatusCard>

              {data.detectionNotice ? (
                <SafetyWarning message={data.detectionNotice} />
              ) : null}
              {data.noContactsWarning ? (
                <SafetyWarning message={data.noContactsWarning} />
              ) : null}
              {data.noProvidersWarning ? (
                <SafetyWarning message={data.noProvidersWarning} />
              ) : null}

              {emergency ? null : (
                <Card style={{ gap: spacing.sm }}>
                  <AppText variant="heading">{SOS_TITLE}</AppText>
                  {confirming === 'sos' ? (
                    <View style={{ gap: spacing.xs }}>
                      <AppText variant="bodyStrong">{SOS_CONFIRM_TITLE}</AppText>
                      <AppText variant="body" tone="secondary">
                        {SOS_CONFIRM_BODY}
                      </AppText>
                      <Button
                        label={SOS_CONFIRM}
                        onPress={pressSos}
                        disabled={sos.isPending}
                      />
                      <Button
                        label={SOS_KEEP}
                        variant="ghost"
                        onPress={() => confirm('none')}
                      />
                    </View>
                  ) : (
                    <Button
                      label={SOS_BUTTON}
                      onPress={pressSos}
                      accessibilityHint="Asks again before anything is sent"
                    />
                  )}
                  {sos.isError ? (
                    <SafetyErrorNote message="That could not be sent. Please try again." />
                  ) : null}
                </Card>
              )}

              {emergency ? null : (
                <Card style={{ gap: spacing.sm }}>
                  <AppText variant="heading">{CONTACTS_LINK}</AppText>
                  <AppText variant="body" tone="secondary">
                    {CONTACTS_HINT}
                  </AppText>
                  <Button
                    label={`${data.emergencyContactCount} in the list`}
                    variant="secondary"
                    onPress={() => router.push('/emergency-contacts')}
                  />
                </Card>
              )}

              {emergency ? null : (
                <View style={{ gap: spacing.xs }}>
                  <Button
                    label={HISTORY_TITLE}
                    variant="secondary"
                    onPress={() => router.push('/safety/history')}
                  />
                  <Button
                    label={CAPABILITIES_TITLE}
                    variant="ghost"
                    onPress={() => router.push('/safety/capabilities')}
                    accessibilityHint="What this build can and cannot do"
                  />
                </View>
              )}
            </View>
          ) : null}
        </AsyncState>
      </View>
    </Screen>
  );
}
