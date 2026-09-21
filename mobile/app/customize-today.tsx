/**
 * Customize Today (PRD 3, sections 19 and 37).
 *
 * Show, hide and reorder the cards on Today. Reordering is move-up/move-down
 * rather than drag-and-drop: a drag target is hard to hit with shaky hands and
 * impossible to reach with a screen reader, and PRD 3 section 19 allows this
 * instead (section 42 requires it -- no critical interaction may depend on a
 * gesture).
 *
 * Only cards this build can actually draw are offered. A card whose feature
 * does not exist yet is never listed, so nobody can switch on an empty
 * medication card (PRD 3, sections 18 and 59).
 */
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Pressable, View } from 'react-native';

import {
  AppText,
  Button,
  Card,
  Screen,
  SkeletonCard,
  ToggleRow,
} from '../src/components';
import { RENDERABLE_CARD_KEYS } from '../src/components/today';
import {
  useDashboardPreferences,
  useSaveDashboardPreferences,
} from '../src/hooks/useToday';
import { apiErrorMessage } from '../src/services/api';
import {
  customisableCards,
  layoutPayload,
  moveCard,
  toggleCard,
} from '../src/services/dashboard/cards';
import { useTheme } from '../src/theme';
import { iconSize, minTouchTarget, radius, spacing } from '../src/theme/tokens';
import type { DashboardCard, DashboardCardKey } from '../src/types/today';

interface MoveButtonProps {
  direction: 'up' | 'down';
  cardTitle: string;
  disabled: boolean;
  onPress: () => void;
}

function MoveButton({ direction, cardTitle, disabled, onPress }: MoveButtonProps) {
  const theme = useTheme();

  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={`Move ${cardTitle} ${direction}`}
      accessibilityState={{ disabled }}
      style={({ pressed }) => ({
        width: minTouchTarget,
        height: minTouchTarget,
        alignItems: 'center',
        justifyContent: 'center',
        borderRadius: radius.md,
        backgroundColor: pressed ? theme.colors.surfaceSecondary : 'transparent',
        opacity: disabled ? 0.35 : 1,
      })}
    >
      <Ionicons
        name={direction === 'up' ? 'chevron-up' : 'chevron-down'}
        size={iconSize.md}
        color={theme.colors.textSecondary}
      />
    </Pressable>
  );
}

export default function CustomizeTodayScreen() {
  const theme = useTheme();
  const router = useRouter();
  const preferences = useDashboardPreferences();
  const save = useSaveDashboardPreferences();

  // Edits are held as an overlay on the server's answer rather than copied
  // into state when it arrives: nothing to keep in sync, no effect, and the
  // screen renders correctly on the very first frame it has data.
  const [edits, setEdits] = useState<DashboardCard[] | null>(null);
  const cards =
    edits ??
    (preferences.data
      ? customisableCards(preferences.data.cards, RENDERABLE_CARD_KEYS)
      : []);

  const onSave = async () => {
    await save.mutateAsync(layoutPayload(cards));
    router.back();
  };

  const move = (key: DashboardCardKey, offset: -1 | 1) =>
    setEdits(moveCard(cards, key, offset));

  return (
    <Screen>
      <AppText variant="title" style={{ marginBottom: spacing.xs }}>
        Customize Today
      </AppText>
      <AppText variant="body" tone="secondary" style={{ marginBottom: spacing.lg }}>
        Choose what appears on your Today screen, and in what order.
      </AppText>

      {preferences.isLoading ? (
        <Card>
          <SkeletonCard lines={3} label="Loading your Today cards" />
        </Card>
      ) : preferences.isError ? (
        <Card style={{ gap: spacing.sm }}>
          <AppText variant="body" tone="secondary">
            {apiErrorMessage(preferences.error)}
          </AppText>
          <Button
            label="Try again"
            variant="secondary"
            onPress={() => preferences.refetch()}
          />
        </Card>
      ) : (
        <View style={{ gap: spacing.lg }}>
          <Card padded={false}>
            {cards.map((card, index) => (
              <View
                key={card.key}
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  paddingRight: spacing.xs,
                  // A hairline between rows, from the theme -- never a colour
                  // written into the screen (PRD 3, section 41).
                  borderTopWidth: index === 0 ? 0 : 1,
                  borderTopColor: theme.colors.border,
                }}
              >
                <View style={{ flex: 1 }}>
                  <ToggleRow
                    label={card.title}
                    value={card.visible}
                    onChange={() => setEdits(toggleCard(cards, card.key))}
                  />
                </View>
                <MoveButton
                  direction="up"
                  cardTitle={card.title}
                  disabled={index === 0}
                  onPress={() => move(card.key, -1)}
                />
                <MoveButton
                  direction="down"
                  cardTitle={card.title}
                  disabled={index === cards.length - 1}
                  onPress={() => move(card.key, 1)}
                />
              </View>
            ))}
          </Card>

          {save.isError ? (
            <AppText variant="body" tone="secondary">
              {apiErrorMessage(save.error)}
            </AppText>
          ) : null}

          <Button
            label={save.isPending ? 'Saving…' : 'Save'}
            disabled={save.isPending || cards.length === 0}
            onPress={() => void onSave()}
          />
        </View>
      )}
    </Screen>
  );
}
