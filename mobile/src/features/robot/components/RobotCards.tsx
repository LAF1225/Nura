/**
 * The cards and rows the Nura Device screens are built from.
 *
 * PRD 11, sections 10, 12, 20, 44, 45, 46, 47, 49, 95, 96, 106 and 130.
 *
 * Three things to notice, all of them accessibility decisions (section 130
 * asks for screen-reader labels and Light/Dark/System, and section 106 for
 * readability over brand colour on anything serious).
 *
 * **Every state is announced as well as drawn.** A capability row reads as
 * "Screen: Not tested yet", not as a coloured dot. A stale report says why.
 *
 * **Nothing is carried by colour alone.** The preview's serious cards use the
 * plain text tone rather than the accent, which is the same decision section
 * 106 asks the firmware to make.
 *
 * **Nothing in this file writes a sentence about hardware.** The capability
 * labels, the state labels and the history lines all arrive from the server
 * (section 75). What is written here is what the app is offering to change.
 */
import { View } from 'react-native';

import { AppText, Card, ListRow, StatusChip } from '../../../components';
import type { StatusTone } from '../../../components';
import { spacing } from '../../../theme/tokens';
import {
  CAPABILITY_NEVER_REPORTED,
  CAPABILITY_STALE,
  MODE_HINTS,
  PREVIEW_HINT,
} from '../copy';
import type { Capability, Presentation, RobotStatus } from '../types';

/** One sentence saying something did not work. */
export function RobotErrorNote({ message }: { message: string }) {
  return (
    <View accessible accessibilityRole="alert" accessibilityLabel={message}>
      <AppText variant="body" tone="danger">
        {message}
      </AppText>
    </View>
  );
}

/**
 * Where the robot stands (sections 46 and 65).
 *
 * The mode and its label both come from the server, because the mode is
 * derived from PRD 10's live safety state and PRD 8's stored mode -- neither
 * of which the app should be re-deciding (section 4).
 */
export function RobotStatusCard({ status }: { status: RobotStatus }) {
  const hint = MODE_HINTS[status.mode];
  const sentence = `${status.displayName}: ${status.modeLabel}.${hint ? ` ${hint}` : ''}`;

  return (
    <Card style={{ gap: spacing.xs }} accessible accessibilityLabel={sentence}>
      <StatusChip
        label={status.modeLabel}
        tone={status.connectionStatus === 'online' ? 'success' : 'neutral'}
      />
      {hint ? (
        <AppText variant="body" tone="secondary">
          {hint}
        </AppText>
      ) : null}
      {status.offlineNote ? (
        <AppText variant="body" tone="secondary">
          {status.offlineNote}
        </AppText>
      ) : null}
      {status.queueDepth > 0 ? (
        <AppText variant="caption" tone="secondary">
          {status.queueDepth === 1
            ? '1 item waiting for Nura'
            : `${status.queueDepth} items waiting for Nura`}
        </AppText>
      ) : null}
    </Card>
  );
}

/**
 * One capability, with both the state and the reason it may differ.
 *
 * A single `ListRow`, not a row plus a chip: PRD 10 learned that the hard way
 * when a capability row rendered its state twice and read it twice to a screen
 * reader. One statement of a state.
 */
export function CapabilityRow({ capability }: { capability: Capability }) {
  const description = capability.stale
    ? CAPABILITY_STALE
    : capability.state === 'not_connected'
      ? CAPABILITY_NEVER_REPORTED
      : undefined;

  return (
    <ListRow
      label={capability.label}
      value={capability.stateLabel}
      description={description}
      accessibilityHint={`${capability.label}: ${capability.stateLabel}`}
    />
  );
}

/** A section heading that is announced as one. */
export function RobotSectionHeading({ title, hint }: { title: string; hint?: string }) {
  return (
    <View style={{ gap: spacing.xxs }}>
      <AppText variant="bodyStrong" accessibilityRole="header">
        {title}
      </AppText>
      {hint ? (
        <AppText variant="caption" tone="secondary">
          {hint}
        </AppText>
      ) : null}
    </View>
  );
}

/**
 * A note explaining that a section's hardware is not there (section 47).
 *
 * Shown instead of controls rather than beside them: section 47 is explicit
 * that live controls must not be presented as if they work.
 */
export function UnavailableNote({ message }: { message: string }) {
  return (
    <Card style={{ gap: spacing.xxs }} accessible accessibilityLabel={message}>
      <AppText variant="body" tone="secondary">
        {message}
      </AppText>
    </Card>
  );
}

const STATUS_TONES: Record<string, StatusTone> = {
  queued: 'neutral',
  sent: 'info',
  acknowledged: 'info',
  displayed: 'success',
  completed: 'success',
  expired: 'neutral',
  failed: 'danger',
  cancelled: 'neutral',
  not_supported: 'warning',
};

/**
 * One row of section 96's history.
 *
 * The sentence is the server's (`line`), so "sent to Nura" and "shown" cannot
 * come apart here -- section 14's distinction survives all the way to the
 * screen. The summary beneath it is the payload the robot was *sent*, already
 * reduced to the privacy level in force when it was built (section 22), so a
 * private reminder reads as "Reminder due" here too.
 */
export function PresentationRow({ presentation }: { presentation: Presentation }) {
  const summary = presentation.summary ?? undefined;
  return (
    <View style={{ gap: spacing.xxs, paddingVertical: spacing.xs }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}>
        <StatusChip
          label={presentation.status.replace(/_/g, ' ')}
          tone={STATUS_TONES[presentation.status] ?? 'neutral'}
        />
      </View>
      <AppText variant="body" accessibilityLabel={presentation.line}>
        {presentation.line}
      </AppText>
      {summary ? (
        <AppText variant="caption" tone="secondary">
          {summary}
        </AppText>
      ) : null}
    </View>
  );
}

/**
 * A drawing of one card layout, as the robot would lay it out (section 95).
 *
 * Labelled "Preview only" by the screen that uses it, and the note travels
 * with it: this does not claim the robot rendered anything. `serious` drops
 * the accent colour, which is the same choice section 106 asks the firmware to
 * make -- readability over brand.
 */
export function PreviewCard({
  layout,
  lines,
  serious = false,
}: {
  layout: string;
  lines: string[];
  serious?: boolean;
}) {
  const sentence = `${layout} layout. ${lines.join('. ')}`;
  return (
    <Card
      style={{ gap: spacing.xxs }}
      accessible
      accessibilityLabel={sentence}
      accessibilityHint={PREVIEW_HINT}
    >
      <AppText variant="caption" tone="secondary">
        {layout}
      </AppText>
      {lines.map((line, index) => (
        <AppText
          key={`${layout}-${index}`}
          variant={index === 0 ? 'bodyStrong' : 'body'}
          tone={serious || index > 0 ? 'primary' : 'accent'}
        >
          {line}
        </AppText>
      ))}
    </Card>
  );
}
