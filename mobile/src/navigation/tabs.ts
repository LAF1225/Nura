/**
 * The five primary sections (PRD 0, section 8).
 *
 * This order is locked: Today, Health, Care, Nura, More. Defining the tabs in
 * one place keeps the navigator declaration short and gives later PRDs a
 * single spot to adjust titles or icons.
 */
import type { Ionicons } from '@expo/vector-icons';

export interface TabDefinition {
  /** Route name inside `app/(tabs)/`. `index` is the default tab. */
  name: 'index' | 'health' | 'care' | 'nura' | 'more';
  title: string;
  icon: keyof typeof Ionicons.glyphMap;
  /** Filled variant, shown when the tab is focused. */
  iconActive: keyof typeof Ionicons.glyphMap;
}

export const TABS: readonly TabDefinition[] = [
  { name: 'index', title: 'Today', icon: 'today-outline', iconActive: 'today' },
  { name: 'health', title: 'Health', icon: 'pulse-outline', iconActive: 'pulse' },
  { name: 'care', title: 'Care', icon: 'people-outline', iconActive: 'people' },
  { name: 'nura', title: 'Nura', icon: 'sparkles-outline', iconActive: 'sparkles' },
  {
    name: 'more',
    title: 'More',
    icon: 'ellipsis-horizontal-circle-outline',
    iconActive: 'ellipsis-horizontal-circle',
  },
] as const;
