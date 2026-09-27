/**
 * One symptom, as the overview and the Today card show it (PRD 6, ss7 and 39).
 *
 * Deliberately three lines: what it is, when it was last written about and how it
 * is going, and a way in. PRD 6 section 7 asks the overview not to be overloaded
 * with detail, and the detail screen is one tap away.
 *
 * Change state appears as a word, never as a colour on its own
 * (PRD 6, section 66).
 */
import { View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { Button } from '../../../components/Button';
import { Card } from '../../../components/Card';
import { StatusChip } from '../../../components/StatusChip';
import { spacing } from '../../../theme/tokens';
import {
  CHANGE_MARKER,
  changeLabel,
  episodeSubtitle,
  episodeTitle,
  PENDING_LABEL,
  STATUS_LABEL,
} from '../copy';
import type { SymptomEpisode } from '../types';

interface SymptomCardProps {
  episode: SymptomEpisode;
  /** The user's local day, so "today" is their today. */
  today: string;
  /** Adds an Update button. Left off where the whole card is already tappable. */
  onUpdate?: () => void;
  onPress?: () => void;
  /** True when there is an update for this symptom still on the phone. */
  pending?: boolean;
}

export function SymptomCard({
  episode,
  today,
  onUpdate,
  onPress,
  pending = false,
}: SymptomCardProps) {
  const entry = episode.latestEntry;
  const change = changeLabel(entry?.changeState);

  return (
    <Card style={{ gap: spacing.sm }}>
      <View style={{ gap: spacing.xxs }}>
        <AppText variant="heading">{episodeTitle(episode.name, entry?.severity)}</AppText>

        <AppText variant="body" tone="secondary">
          {episodeSubtitle(episode, today)}
        </AppText>

        {change ? (
          <AppText variant="body" tone="secondary">
            {/* The arrow is a second, non-colour cue beside the word, so the
                direction survives for somebody who cannot tell the colours
                apart (PRD 6, section 66). */}
            {`${CHANGE_MARKER[entry?.changeState ?? 'unsure']} ${change}`}
          </AppText>
        ) : null}

        {episode.status !== 'active' ? (
          <AppText variant="caption" tone="secondary">
            {STATUS_LABEL[episode.status]}
          </AppText>
        ) : null}
      </View>

      {pending ? (
        <StatusChip label={PENDING_LABEL} tone="info" icon="cloud-offline-outline" />
      ) : null}

      {onUpdate ? (
        <Button
          label="Add an update"
          variant="secondary"
          onPress={onUpdate}
          accessibilityHint={`Adds how your ${episode.name.toLowerCase()} is doing now`}
        />
      ) : null}

      {onPress ? (
        <Button
          label="See history"
          variant="ghost"
          onPress={onPress}
          accessibilityHint={`Opens everything you have logged about your ${episode.name.toLowerCase()}`}
        />
      ) : null}
    </Card>
  );
}
