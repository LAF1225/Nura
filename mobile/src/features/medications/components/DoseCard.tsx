/**
 * One dose, with the three things you can do about it (PRD 5, sections 16, 28).
 *
 * Used by the Today card and by the medication screen, so a dose looks and
 * behaves the same wherever it appears.
 *
 * The wording is all from `doses.ts`, which is where the tone is kept: an
 * overdue dose says it was not marked as taken, and says it once, without a
 * red banner or an exclamation mark. A medication reminder is a routine part
 * of somebody's day (PRD 5, sections 24 and 29).
 */
import { useState } from 'react';
import { View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { Card } from '../../../components/Card';
import { StatusChip } from '../../../components/StatusChip';
import { spacing } from '../../../theme/tokens';
import { formatDoseTime, windowLabel } from '../doses';
import type { DoseWindow } from '../types';
import { DoseActionButtons } from './DoseActionButtons';

interface DoseCardProps {
  /** "Metformin — 500 mg". */
  title: string;
  /** ISO instant the dose is waiting for. */
  dueAt: string;
  window: DoseWindow;
  canSnooze: boolean;
  /** Shown instead of the buttons once the dose has been recorded. */
  statusLine?: string | null;
  /** True while the action is saved on this phone and not yet on the server. */
  pending?: boolean;
  busy?: boolean;
  /** Extra line under the title, e.g. a low-supply note. */
  footnote?: string | null;
  onTaken: () => void;
  onSnooze: (minutes: number) => void;
  onSkip: () => void;
}

export function DoseCard({
  title,
  dueAt,
  window,
  canSnooze,
  statusLine,
  pending = false,
  busy = false,
  footnote,
  onTaken,
  onSnooze,
  onSkip,
}: DoseCardProps) {
  const [choosingSnooze, setChoosingSnooze] = useState(false);
  const label = windowLabel(window);
  const recorded = window === 'completed';

  return (
    <Card style={{ gap: spacing.md }}>
      <View style={{ gap: spacing.xxs }}>
        <AppText variant="heading">{title}</AppText>
        <AppText variant="body" tone="secondary">
          {/* The time is always present; the phrase beside it says where the
              dose sits, so neither depends on colour (PRD 5, section 61). */}
          {label === null ? formatDoseTime(dueAt) : `${formatDoseTime(dueAt)} · ${label}`}
        </AppText>
        {footnote ? (
          <AppText variant="caption" tone="secondary">
            {footnote}
          </AppText>
        ) : null}
      </View>

      {recorded ? (
        statusLine ? (
          <AppText variant="body" tone="secondary">
            {statusLine}
          </AppText>
        ) : null
      ) : (
        <DoseActionButtons
          canSnooze={canSnooze}
          choosingSnooze={choosingSnooze}
          busy={busy}
          onTaken={() => {
            setChoosingSnooze(false);
            onTaken();
          }}
          onOpenSnooze={() => setChoosingSnooze(true)}
          onSnooze={(minutes) => {
            setChoosingSnooze(false);
            onSnooze(minutes);
          }}
          onSkip={onSkip}
        />
      )}

      {pending ? (
        <StatusChip
          label="Saved on this phone — will sync when you’re back online"
          tone="info"
          icon="cloud-offline-outline"
        />
      ) : null}
    </Card>
  );
}
