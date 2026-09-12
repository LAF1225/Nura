/**
 * Appearance (PRD 0, section 27).
 *
 * Choosing an option writes to the app store, which the ThemeProvider reads,
 * so the whole app re-themes on the spot. The choice is persisted by the
 * store's AsyncStorage layer and survives a restart.
 */
import { AppText, ListGroup, ListRow, Screen } from '../src/components';
import { useAppStore } from '../src/store/appStore';
import type { ThemePreference } from '../src/theme';
import { spacing } from '../src/theme/tokens';

const OPTIONS: { value: ThemePreference; label: string; description: string }[] = [
  { value: 'system', label: 'System', description: 'Match my device appearance' },
  { value: 'light', label: 'Light', description: 'Always light' },
  { value: 'dark', label: 'Dark', description: 'Always dark' },
];

export default function AppearanceScreen() {
  const preference = useAppStore((state) => state.themePreference);
  const setThemePreference = useAppStore((state) => state.setThemePreference);

  return (
    <Screen>
      <AppText variant="caption" tone="secondary" style={{ marginBottom: spacing.xs }}>
        THEME
      </AppText>

      <ListGroup>
        {OPTIONS.map((option) => (
          <ListRow
            key={option.value}
            label={option.label}
            description={option.description}
            role="radio"
            selected={preference === option.value}
            onPress={() => setThemePreference(option.value)}
          />
        ))}
      </ListGroup>

      <AppText variant="caption" tone="secondary" style={{ marginTop: spacing.md }}>
        System follows your device&apos;s Light or Dark setting and updates automatically.
      </AppText>
    </Screen>
  );
}
