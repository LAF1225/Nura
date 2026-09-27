/**
 * The Today medication card (PRD 5, sections 28 and 53).
 *
 * Shows the one dose somebody is most likely to act on, with Taken, Snooze
 * and Skip right there -- the point of the card is that a routine dose can be
 * recorded without going anywhere. Everything else is a count and a way in.
 *
 * It draws nothing at all when the profile has no schedules. An empty
 * medication card would promise a feature that has not been set up, which is
 * exactly what PRD 3 section 18 rules out; the Care tab is where somebody goes
 * to create their first schedule.
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { Button } from '../../../components/Button';
import { Card } from '../../../components/Card';
import { spacing } from '../../../theme/tokens';
import { localDateString } from '../../../utils/date';
import { doseTitle, lowSupplySentence } from '../doses';
import { useDoseAction } from '../hooks';
import type { TodayMedications } from '../types';
import { DoseCard } from './DoseCard';

interface MedicationsTodayCardProps {
  medications: TodayMedications | null;
}

/**
 * "2 more later today", or null when there is nothing left to say.
 *
 * The dose on the card is only subtracted when it is actually one of today's.
 * `next_due` may be yesterday's overdue dose, still waiting to be recorded --
 * and that one is not part of today's remaining count.
 */
function remainingLine(medications: TodayMedications, today: string): string | null {
  const nextIsToday =
    medications.nextDue !== null &&
    localDateString(new Date(medications.nextDue.scheduledFor)) === today;

  const remaining = medications.remainingTodayCount - (nextIsToday ? 1 : 0);
  if (remaining <= 0) return null;
  return remaining === 1 ? '1 more later today' : `${remaining} more later today`;
}

export function MedicationsTodayCard({ medications }: MedicationsTodayCardProps) {
  const router = useRouter();
  const action = useDoseAction();

  if (medications === null || !medications.hasSchedules) return null;

  const next = medications.nextDue;
  const later = remainingLine(medications, localDateString());
  const low = medications.lowSupply[0];

  const run = (doseId: string, input: Parameters<typeof action.mutate>[0]['input']) =>
    action.mutate({ doseId, input });

  return (
    <View style={{ gap: spacing.sm }}>
      {next === null ? (
        <Card style={{ gap: spacing.xxs }}>
          <AppText variant="heading">Medications</AppText>
          <AppText variant="body" tone="secondary">
            {medications.dueTodayCount === 0
              ? 'Nothing is scheduled for today.'
              : 'Everything scheduled for today has been recorded.'}
          </AppText>
          <Button
            label="Medications"
            variant="secondary"
            onPress={() => router.push('/medications')}
            accessibilityHint="Opens your medication schedules and history"
          />
        </Card>
      ) : (
        <DoseCard
          title={doseTitle(next)}
          dueAt={next.scheduledFor}
          window={next.window}
          canSnooze={next.canSnooze}
          busy={action.isPending}
          footnote={later}
          onTaken={() => run(next.doseId, { action: 'taken' })}
          onSnooze={(minutes) => run(next.doseId, { action: 'snooze', minutes })}
          onSkip={() =>
            router.push({
              pathname: '/medications/skip',
              params: { doseId: next.doseId },
            })
          }
        />
      )}

      {low ? (
        <Card style={{ gap: spacing.xxs }}>
          <AppText variant="bodyStrong">Refill reminder</AppText>
          {/* Cautious wording: the count came from the user, not from Nura
              (PRD 5, section 34). */}
          <AppText variant="body" tone="secondary">
            {lowSupplySentence(low.medicationName, low.remainingDoses)}
          </AppText>
          <Button
            label="Update supply"
            variant="secondary"
            onPress={() => router.push('/medications/supply')}
          />
        </Card>
      ) : null}
    </View>
  );
}
