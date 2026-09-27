/**
 * The small read-only cards on the medication screens.
 *
 * `AdherenceSummaryCard` (PRD 5, section 27) shows one clearly defined
 * figure and the counts behind it. It never calls the number good or bad,
 * never sets a target, and is deliberately a sentence rather than a dial --
 * a gauge invites a judgement that Nura is in no position to make.
 *
 * `RefillStatusCard` (PRD 5, sections 31-34) shows the count the *user*
 * entered, says so, and offers the two things they might want to do about it.
 * Nothing estimates how long a supply will last.
 *
 * `MedicationHistoryRow` (PRD 5, sections 25 and 26) is one past dose. A late
 * dose says when it was taken; an unrecorded one says it was not marked as
 * taken. Neither is styled as a failure (section 24).
 */
import { View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { Button } from '../../../components/Button';
import { Card } from '../../../components/Card';
import { StatusChip } from '../../../components/StatusChip';
import { spacing } from '../../../theme/tokens';
import {
  adherenceSentence,
  doseStatusLine,
  doseTitle,
  formatDoseTime,
  SUPPLY_CAVEAT,
} from '../doses';
import type { Adherence, MedicationDose, MedicationSupply } from '../types';

interface AdherenceSummaryCardProps {
  adherence: Adherence;
  days: number;
}

export function AdherenceSummaryCard({ adherence, days }: AdherenceSummaryCardProps) {
  return (
    <Card style={{ gap: spacing.xxs }}>
      <AppText variant="bodyStrong">Recorded doses</AppText>
      <AppText variant="body" tone="secondary">
        {adherenceSentence(adherence, days)}
      </AppText>
      {adherence.total > 0 ? (
        // The denominator, spelled out, so the percentage above cannot read
        // as a score with nothing behind it.
        <AppText variant="caption" tone="secondary">
          {adherence.taken} taken · {adherence.skipped} skipped · {adherence.missed} not
          marked
        </AppText>
      ) : null}
    </Card>
  );
}

interface RefillStatusCardProps {
  supply: MedicationSupply;
  onAdjust: () => void;
  onRefilled: () => void;
}

export function RefillStatusCard({
  supply,
  onAdjust,
  onRefilled,
}: RefillStatusCardProps) {
  return (
    <Card style={{ gap: spacing.sm }}>
      <View style={{ gap: spacing.xxs }}>
        <AppText variant="bodyStrong">{supply.medicationName}</AppText>
        <AppText variant="body" tone="secondary">
          {supply.remainingDoses === null
            ? 'No count recorded yet.'
            : supply.remainingDoses === 1
              ? 'About 1 dose left'
              : `About ${supply.remainingDoses} doses left`}
        </AppText>
        {supply.refillThresholdDoses !== null ? (
          <AppText variant="caption" tone="secondary">
            Nura mentions a refill at {supply.refillThresholdDoses} left.
          </AppText>
        ) : null}
        <AppText variant="caption" tone="secondary">
          {SUPPLY_CAVEAT}
        </AppText>
      </View>

      {supply.low ? (
        <StatusChip label="Running low" tone="warning" icon="alert-circle-outline" />
      ) : null}

      <View style={{ flexDirection: 'row', gap: spacing.xs }}>
        <Button
          label="Adjust"
          variant="secondary"
          onPress={onAdjust}
          style={{ flex: 1 }}
          accessibilityHint={`Changes the recorded count for ${supply.medicationName}`}
        />
        <Button
          label="Mark refilled"
          onPress={onRefilled}
          style={{ flex: 1 }}
          accessibilityHint={`Records a new supply of ${supply.medicationName}`}
        />
      </View>
    </Card>
  );
}

interface MedicationHistoryRowProps {
  dose: MedicationDose;
}

export function MedicationHistoryRow({ dose }: MedicationHistoryRowProps) {
  return (
    <View
      // One accessible unit, so a screen reader reads "8:00 AM, Metformin —
      // 500 mg, taken" rather than three unrelated fragments.
      accessible
      accessibilityRole="text"
      accessibilityLabel={`${formatDoseTime(dose.scheduledFor)}, ${doseTitle(
        dose
      )}, ${doseStatusLine(dose)}`}
      style={{
        flexDirection: 'row',
        gap: spacing.sm,
        paddingVertical: spacing.xs,
      }}
    >
      <AppText variant="body" tone="secondary" style={{ width: 76 }}>
        {formatDoseTime(dose.scheduledFor)}
      </AppText>
      <View style={{ flex: 1, gap: spacing.xxs }}>
        <AppText variant="bodyStrong">{doseTitle(dose)}</AppText>
        <AppText variant="caption" tone="secondary">
          {doseStatusLine(dose)}
          {dose.syncStatus === 'pending' ? ' · not synced yet' : ''}
        </AppText>
        {dose.skipReasonText ? (
          <AppText variant="caption" tone="secondary">
            {dose.skipReasonText}
          </AppText>
        ) : null}
      </View>
    </View>
  );
}
