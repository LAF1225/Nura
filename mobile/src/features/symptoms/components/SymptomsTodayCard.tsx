/**
 * The Today symptoms card (PRD 6, sections 39, 40 and 52).
 *
 * Shows the symptom most recently written about, with the one action that matters
 * from Today: adding an update. Everything else is a count and a way in.
 *
 * **It draws nothing at all for somebody who has never logged a symptom.** Most
 * people, most of the time, have nothing to report, and a card saying so would be
 * a permanent reminder of a feature they are not using -- which is what PRD 3
 * section 18 rules out. Once they have used it, the card is there and shows the
 * empty state PRD 6 section 39 specifies, because from then on it is a way back
 * in rather than an advertisement.
 *
 * Nothing on it is styled as an alert. A symptom the user recorded as worsening is
 * stated in words, and PRD 6 section 40 forbids labelling it urgent without a
 * reviewed safety rule -- which is switched off (section 44).
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { Button } from '../../../components/Button';
import { Card } from '../../../components/Card';
import { spacing } from '../../../theme/tokens';
import {
  CHANGE_MARKER,
  changeLabel,
  EMPTY_TODAY_CARD,
  episodeTitle,
  formatDay,
  summarySentence,
} from '../copy';
import type { TodaySymptoms } from '../types';

interface SymptomsTodayCardProps {
  symptoms: TodaySymptoms | null;
}

export function SymptomsTodayCard({ symptoms }: SymptomsTodayCardProps) {
  const router = useRouter();

  // Never used the feature: nothing to draw.
  if (symptoms === null || !symptoms.hasEpisodes) return null;

  const recent = symptoms.mostRecent;

  if (recent === null) {
    return (
      <Card style={{ gap: spacing.xxs }}>
        <AppText variant="heading">Symptoms</AppText>
        <AppText variant="body" tone="secondary">
          {EMPTY_TODAY_CARD}
        </AppText>
        <Button
          label="Log a symptom"
          variant="secondary"
          onPress={() => router.push('/symptoms')}
          accessibilityHint="Opens symptoms, where you can log a new one"
        />
      </Card>
    );
  }

  const change = changeLabel(recent.changeState);

  return (
    <Card style={{ gap: spacing.sm }}>
      <View style={{ gap: spacing.xxs }}>
        <AppText variant="heading">Symptoms</AppText>
        <AppText variant="bodyStrong">
          {episodeTitle(recent.name, recent.severity)}
        </AppText>
        <AppText variant="body" tone="secondary">
          {`Last updated ${formatDay(recent.updatedAt)}`}
        </AppText>
        {change ? (
          <AppText variant="body" tone="secondary">
            {`${CHANGE_MARKER[recent.changeState ?? 'unsure']} ${change}`}
          </AppText>
        ) : null}
        {symptoms.activeCount > 1 ? (
          <AppText variant="caption" tone="secondary">
            {summarySentence(symptoms.activeCount, symptoms.worseningCount)}
          </AppText>
        ) : null}
      </View>

      <Button
        label="Add an update"
        onPress={() =>
          router.push({
            pathname: '/symptoms/[id]/update',
            params: { id: recent.episodeId },
          })
        }
        accessibilityHint={`Records how your ${recent.name.toLowerCase()} is doing now`}
      />
    </Card>
  );
}
