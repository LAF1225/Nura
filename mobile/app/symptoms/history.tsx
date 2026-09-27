/**
 * Every symptom, active or ended (PRD 6, sections 36 and 49).
 *
 * The filters are the ones PRD 6 section 49 asks for and no more: active, ended,
 * and everything. "Recent" is the default ordering rather than a filter, and
 * searching by name is left to the overview's own list -- a search box reaching
 * into somebody's symptom descriptions is a feature that needs its own thought.
 *
 * Each row is a way into the episode's own history. Nothing about a symptom's
 * detail is shown here, for the same reason the overview keeps it out
 * (PRD 6, section 7).
 */
import { useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import {
  AppText,
  Button,
  Card,
  ListGroup,
  ListRow,
  Screen,
  SkeletonCard,
} from '../../src/components';
import {
  changeLabel,
  EMPTY_HISTORY,
  episodeSubtitle,
  episodeTitle,
  isActiveStatus,
  joined,
  STATUS_LABEL,
} from '../../src/features/symptoms/copy';
import { useSymptomEpisodes } from '../../src/features/symptoms/hooks';
import type { EpisodeStatus } from '../../src/features/symptoms/types';
import { apiErrorMessage } from '../../src/services/api';
import { minTouchTarget, radius, spacing } from '../../src/theme/tokens';
import { useTheme } from '../../src/theme';
import { localDateString } from '../../src/utils/date';

type Scope = 'all' | 'active' | 'resolved';

const SCOPES: { value: Scope; label: string }[] = [
  { value: 'all', label: 'Everything' },
  { value: 'active', label: 'Active' },
  { value: 'resolved', label: 'Ended' },
];

export default function SymptomHistoryScreen() {
  const router = useRouter();
  const theme = useTheme();
  // The chosen filter is the one piece of local state here. It changes what is
  // fetched, so a re-render follows from the query rather than from this value.
  const [scope, setScope] = useState<Scope>('all');

  const episodes = useSymptomEpisodes(
    scope === 'all'
      ? {}
      : scope === 'active'
        ? { active: true }
        : { status: 'resolved' as EpisodeStatus }
  );

  const today = localDateString();
  const rows = episodes.data ?? [];

  return (
    <Screen
      onRefresh={() => void episodes.refetch()}
      refreshing={episodes.isRefetching && !episodes.isLoading}
    >
      <View
        style={{ flexDirection: 'row', gap: spacing.xs }}
        accessibilityRole="radiogroup"
        accessibilityLabel="Which symptoms to show"
      >
        {SCOPES.map((option) => {
          const selected = scope === option.value;
          return (
            <Button
              key={option.value}
              label={option.label}
              variant={selected ? 'primary' : 'secondary'}
              onPress={() => setScope(option.value)}
              style={{
                flex: 1,
                minHeight: minTouchTarget,
                borderRadius: radius.pill,
                borderColor: theme.colors.border,
              }}
            />
          );
        })}
      </View>

      <View style={{ height: spacing.lg }} />

      {episodes.isLoading ? (
        <Card>
          <SkeletonCard lines={4} label="Loading your symptom history" />
        </Card>
      ) : episodes.isError ? (
        <Card style={{ gap: spacing.sm }}>
          <AppText variant="heading">Nura can’t load your history</AppText>
          <AppText variant="body" tone="secondary">
            {apiErrorMessage(episodes.error)}
          </AppText>
          <Button
            label="Try again"
            variant="secondary"
            onPress={() => episodes.refetch()}
          />
        </Card>
      ) : rows.length === 0 ? (
        <Card>
          <AppText variant="body" tone="secondary">
            {EMPTY_HISTORY}
          </AppText>
        </Card>
      ) : (
        <ListGroup>
          {rows.map((episode) => (
            <ListRow
              key={episode.id}
              label={episodeTitle(episode.name, episode.latestEntry?.severity)}
              description={
                episodeSubtitle(episode, today) ?? 'Nothing logged about it yet'
              }
              value={
                joined([
                  isActiveStatus(episode.status) ? null : STATUS_LABEL[episode.status],
                  changeLabel(episode.latestEntry?.changeState),
                ]) ?? undefined
              }
              showChevron
              onPress={() =>
                router.push({ pathname: '/symptoms/[id]', params: { id: episode.id } })
              }
              accessibilityHint={`Opens everything you have logged about your ${episode.name.toLowerCase()}`}
            />
          ))}
        </ListGroup>
      )}
    </Screen>
  );
}
