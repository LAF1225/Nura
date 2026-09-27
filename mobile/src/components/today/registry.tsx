/**
 * The Today card registry (PRD 3, sections 17 and 59).
 *
 * Today is a list of cards looked up by key, not one screen with everything
 * written into it. Adding a card in a later PRD means three edits -- the
 * server registry, the `DashboardCardKey` union, and one entry here -- and no
 * change to the screen itself.
 *
 * A key with no entry here simply is not drawn, which is what lets the backend
 * announce a card before an app version knows how to render it.
 */
import type { ReactNode } from 'react';
import { View } from 'react-native';

import { visibleCards } from '../../services/dashboard/cards';
import { spacing } from '../../theme/tokens';
import type {
  DailyCheckIn,
  DashboardCard,
  DashboardCardKey,
  TodayDevice,
  TodayMedications,
  TodaySymptoms,
  WellbeingLevel,
} from '../../types/today';
import { HealthProfileCard } from '../../features/health/components/HealthProfileCard';
import { MedicationsTodayCard } from '../../features/medications/components/MedicationsTodayCard';
import { SymptomsTodayCard } from '../../features/symptoms/components/SymptomsTodayCard';
import { DailyCheckInCard } from './DailyCheckInCard';
import { NuraStatusCard } from './NuraStatusCard';
import { QuickActionsCard } from './QuickActionsCard';

/** Everything a card renderer is allowed to know about the day. */
export interface DashboardCardContext {
  device: TodayDevice | null;
  /** The medication block of the Today summary. Null with no profile. */
  medications: TodayMedications | null;
  /** The symptom block. Null with no profile. */
  symptoms: TodaySymptoms | null;
  /** True when the screen is showing saved information rather than live data. */
  statusUnavailable: boolean;
  checkIn: DailyCheckIn | null;
  recentCompletedCount: number;
  isSavingCheckIn: boolean;
  checkInError: string | null;
  onSubmitCheckIn: (level: WellbeingLevel, note: string | null) => void;
}

type CardRenderer = (context: DashboardCardContext) => ReactNode;

export const CARD_RENDERERS: Partial<Record<DashboardCardKey, CardRenderer>> = {
  daily_checkin: (context) => (
    <DailyCheckInCard
      checkIn={context.checkIn}
      isSaving={context.isSavingCheckIn}
      errorMessage={context.checkInError}
      recentCompletedCount={context.recentCompletedCount}
      onSubmit={context.onSubmitCheckIn}
    />
  ),
  device_status: (context) => (
    <NuraStatusCard
      device={context.device}
      statusUnavailable={context.statusUnavailable}
    />
  ),
  quick_actions: (context) => <QuickActionsCard device={context.device} />,
  // Reads its own summary rather than being handed one: Today should not pay
  // for a health request when the card is hidden, which it is by default
  // (PRD 4, section 47).
  health_profile: () => <HealthProfileCard />,
  // Handed its data, because the Today request already carries it: the whole
  // point of PRD 5 section 53 is that medications arrive with the day rather
  // than costing a second request (PRD 3, section 16). The card draws nothing
  // at all for a profile with no schedules.
  medications: (context) => <MedicationsTodayCard medications={context.medications} />,
  // Handed its data for the same reason, and it draws nothing at all for
  // anybody who has never logged a symptom -- which is most people, most of
  // the time (PRD 6, section 39).
  symptoms: (context) => <SymptomsTodayCard symptoms={context.symptoms} />,
};

/** Keys this build can draw. Used to filter whatever the server sends. */
export const RENDERABLE_CARD_KEYS: ReadonlySet<DashboardCardKey> = new Set(
  Object.keys(CARD_RENDERERS) as DashboardCardKey[]
);

interface DashboardCardListProps {
  cards: DashboardCard[];
  context: DashboardCardContext;
  /**
   * A fixed section to place directly after one of the cards, or first if that
   * card is hidden. Important Today uses it: PRD 3 section 7 puts it under the
   * check-in, but it is not a card the user can hide -- a reminder someone
   * switched off months ago is a reminder that failed.
   */
  insertAfter?: { key: DashboardCardKey; node: ReactNode };
}

export function DashboardCardList({
  cards,
  context,
  insertAfter,
}: DashboardCardListProps) {
  const shown = visibleCards(cards, RENDERABLE_CARD_KEYS);
  const anchorIsShown =
    insertAfter !== undefined && shown.some((card) => card.key === insertAfter.key);

  return (
    <View style={{ gap: spacing.lg }}>
      {insertAfter && !anchorIsShown ? insertAfter.node : null}

      {shown.map((card) => (
        <View key={card.key} style={{ gap: spacing.lg }}>
          {CARD_RENDERERS[card.key]?.(context)}
          {insertAfter && insertAfter.key === card.key ? insertAfter.node : null}
        </View>
      ))}
    </View>
  );
}
