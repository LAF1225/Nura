/**
 * One observation in an episode's history (PRD 6, section 36).
 *
 * The shape PRD 6 section 36 asks for -- date, severity, how it changed -- with
 * whatever else was recorded underneath. Tapping it opens the entry, where it can
 * be corrected (section 30).
 *
 * The severity is shown as the user's own number and never turned into a word,
 * and the change state carries its arrow as well as its label so neither depends
 * on colour (PRD 6, sections 22 and 66).
 */
import { Pressable, View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { StatusChip } from '../../../components/StatusChip';
import { useTheme } from '../../../theme';
import { minTouchTarget, spacing } from '../../../theme/tokens';
import {
  CHANGE_MARKER,
  changeLabel,
  entryLine,
  joined,
  PENDING_LABEL,
  PENDING_PHOTO_LABEL,
} from '../copy';
import type { SymptomEntry } from '../types';

interface SymptomTimelineRowProps {
  entry: SymptomEntry;
  onPress?: () => void;
  /** Drawn without a separator when it is the last row in a group. */
  last?: boolean;
}

/** The second line: whatever else this observation said. */
function details(entry: SymptomEntry): string | null {
  const list = (values: string[]): string | null =>
    values.length > 0 ? values.join(', ') : null;

  return joined([
    entry.site,
    entry.character,
    list(entry.associatedSymptoms),
    entry.negatedItems.length > 0 ? `no ${entry.negatedItems.join(', ')}` : null,
    entry.freeTextNote,
  ]);
}

export function SymptomTimelineRow({
  entry,
  onPress,
  last = false,
}: SymptomTimelineRowProps) {
  const theme = useTheme();
  const change = changeLabel(entry.changeState);
  const second = details(entry);
  const photos = entry.photos.length;
  const pendingPhotos = entry.photos.filter(
    (photo) => photo.syncStatus === 'pending'
  ).length;

  const body = (
    <View
      style={{
        gap: spacing.xxs,
        paddingVertical: spacing.sm,
        minHeight: minTouchTarget,
        borderBottomWidth: last ? 0 : 1,
        borderBottomColor: theme.colors.border,
      }}
    >
      <AppText variant="bodyStrong">{entryLine(entry)}</AppText>

      {change ? (
        <AppText variant="caption" tone="secondary">
          {`${CHANGE_MARKER[entry.changeState ?? 'unsure']} ${change}`}
        </AppText>
      ) : null}

      {second ? (
        <AppText variant="caption" tone="secondary" numberOfLines={2}>
          {second}
        </AppText>
      ) : null}

      {photos > 0 ? (
        <AppText variant="caption" tone="secondary">
          {photos === 1 ? '1 photo' : `${photos} photos`}
          {pendingPhotos > 0 ? ` · ${PENDING_PHOTO_LABEL}` : ''}
        </AppText>
      ) : null}

      {entry.syncStatus === 'pending' ? (
        <StatusChip label={PENDING_LABEL} tone="info" icon="cloud-offline-outline" />
      ) : null}
    </View>
  );

  if (onPress === undefined) return body;

  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityHint="Opens this entry so you can change it"
    >
      {body}
    </Pressable>
  );
}
