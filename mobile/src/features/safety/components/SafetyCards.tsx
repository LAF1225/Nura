/**
 * The cards and rows the safety screens are built from.
 *
 * PRD 10, sections 13, 42, 51, 64, 66, 72, 73, 74, 100, 118 and 119.
 *
 * Accessibility is why several of these look plainer than they could
 * (section 118). Every state is announced as well as drawn, nothing is
 * carried by colour alone, the countdown is text rather than an animation,
 * and the SOS control is a two-step confirm rather than a press-and-hold --
 * a hold has no accessible equivalent that a screen reader can describe or a
 * shaking hand can complete, and section 13 allows either.
 *
 * **Nothing in this file writes a sentence about what happened.** The event
 * labels, the escalation lines and the warnings all arrive from the server
 * (section 120). What is written here is what the app is offering to do.
 */
import { View } from 'react-native';

import { AppText, Button, Card, ListRow, StatusChip } from '../../../components';
import { spacing } from '../../../theme/tokens';
import {
  ACKNOWLEDGE,
  ACKNOWLEDGE_NOTE,
  ACKNOWLEDGED,
  countdownSentence,
  ESCALATION_EMPTY,
  ESCALATION_TITLE,
} from '../copy';
import type {
  Capability,
  EscalationAttempt,
  SafetyAlert,
  SafetyEvent,
  SafetyStatus,
} from '../types';

/**
 * One sentence saying something did not work.
 *
 * The same shape PRD 9's `CareErrorNote` takes, and for the same reason: an
 * `alert` role is what tells a screen reader that the press just made did not
 * take.
 */
export function SafetyErrorNote({ message }: { message: string }) {
  return (
    <View accessible accessibilityRole="alert" accessibilityLabel={message}>
      <AppText variant="body" tone="danger">
        {message}
      </AppText>
    </View>
  );
}

/**
 * A standing warning, announced rather than only drawn.
 *
 * Sections 73 and 74 both require a warning the user cannot miss, and section
 * 118 rules out carrying status by colour. So this is a card with an `alert`
 * role and the whole sentence as its label.
 */
export function SafetyWarning({ message }: { message: string }) {
  return (
    <Card
      style={{ gap: spacing.xxs }}
      accessible
      accessibilityRole="alert"
      accessibilityLabel={message}
    >
      <AppText variant="body">{message}</AppText>
    </Card>
  );
}

/**
 * Where monitoring stands (sections 4, 59 and 60).
 *
 * The sentence comes from the server, so "ON until 10:30 PM" is rendered in
 * the person's own zone by the code that knows it -- Hermes has no time-zone
 * database, which is the PRD 7 lesson applied again.
 */
export function SafetyStatusCard({
  status,
  children,
}: {
  status: SafetyStatus;
  children?: React.ReactNode;
}) {
  const on = status.monitoring !== null;
  return (
    <Card style={{ gap: spacing.sm }}>
      <View style={{ gap: spacing.xxs }}>
        <AppText variant="heading">Safety Monitoring</AppText>
        <View style={{ flexDirection: 'row' }}>
          <StatusChip label={on ? 'On' : 'Off'} tone={on ? 'success' : 'neutral'} />
        </View>
        <AppText variant="body" tone="secondary">
          {status.monitoringSentence}
        </AppText>
        {status.monitoring ? (
          <AppText variant="caption" tone="secondary">
            {`Response timeout: ${status.monitoring.responseTimeoutSeconds} seconds`}
          </AppText>
        ) : null}
      </View>
      {children}
    </Card>
  );
}

/**
 * One capability and its state (sections 64 and 106).
 *
 * Both halves are words. A green dot and a grey dot would say the same thing
 * to most people and nothing at all to some, which section 118 rules out.
 */
export function CapabilityStatusRow({ capability }: { capability: Capability }) {
  // One statement of the state, not two. A chip beside the same words would
  // read twice to a screen reader and add nothing to anybody else -- and the
  // words are what section 118 requires, with or without the chip.
  return <ListRow label={capability.label} description={capability.stateLabel} />;
}

/**
 * What the escalation actually did (section 42).
 *
 * Every line is the server's. A client that rebuilt them from `channel` and
 * `status` would be a second place "Ayesha has been contacted" could appear.
 */
export function EscalationStatusList({ attempts }: { attempts: EscalationAttempt[] }) {
  return (
    <View style={{ gap: spacing.xs }}>
      <AppText variant="bodyStrong">{ESCALATION_TITLE}</AppText>
      {attempts.length === 0 ? (
        <AppText variant="body" tone="secondary">
          {ESCALATION_EMPTY}
        </AppText>
      ) : (
        attempts.map((attempt) => (
          <AppText key={attempt.id} variant="body" tone="secondary">
            {attempt.line}
          </AppText>
        ))
      )}
    </View>
  );
}

/**
 * The countdown, in words (section 118).
 *
 * Driven by the server's deadline, so it says the same thing after a reload
 * as before one -- and it never claims time is up on its own authority.
 */
export function CountdownLine({ seconds }: { seconds: number | null }) {
  if (seconds === null) return null;
  const sentence = countdownSentence(seconds);
  return (
    <View accessible accessibilityRole="text" accessibilityLabel={sentence}>
      <AppText variant="body" tone="secondary">
        {sentence}
      </AppText>
    </View>
  );
}

/** One event in the history (section 49). */
export function SafetyEventRow({
  event,
  onPress,
}: {
  event: SafetyEvent;
  onPress: () => void;
}) {
  const ended = event.resolutionLabel ?? event.escalationOutcomeLabel ?? 'In progress';
  return (
    <ListRow
      label={event.eventLabel}
      description={ended}
      onPress={onPress}
      showChevron
      accessibilityHint="Opens what happened and what Nura did"
    />
  );
}

/**
 * One alert, as a caregiver sees it (sections 37, 83, 84 and 85).
 *
 * The sentence is the server's and carries no health data. Acknowledging says
 * what it is and what it is not, because "I'm checking on them" could
 * otherwise read as resolving the event (section 125).
 */
export function CaregiverAlertCard({
  alert,
  onAcknowledge,
  busy,
}: {
  alert: SafetyAlert;
  onAcknowledge: () => void;
  busy?: boolean;
}) {
  return (
    <Card style={{ gap: spacing.sm }}>
      <View style={{ gap: spacing.xxs }}>
        <AppText variant="bodyStrong">{alert.eventLabel}</AppText>
        <AppText variant="body" tone="secondary">
          {alert.sentence}
        </AppText>
      </View>
      {alert.acknowledgedAt ? (
        <AppText variant="caption" tone="secondary">
          {ACKNOWLEDGED}
        </AppText>
      ) : (
        <View style={{ gap: spacing.xxs }}>
          <Button
            label={ACKNOWLEDGE}
            variant="secondary"
            onPress={onAcknowledge}
            disabled={busy}
            accessibilityHint={ACKNOWLEDGE_NOTE}
          />
          <AppText variant="caption" tone="secondary">
            {ACKNOWLEDGE_NOTE}
          </AppText>
        </View>
      )}
    </Card>
  );
}
