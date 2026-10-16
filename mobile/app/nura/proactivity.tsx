/**
 * When Nura speaks first, and which mode it is in (PRD 8, ss34-36, 65-68).
 *
 * Two settings, on one screen, because they answer the same question from
 * different directions: how often Nura may raise something, and what kind of
 * moment the user is in.
 *
 * The note at the bottom is section 67 said out loud. Sleep mode quietens
 * *Nura*; it does not touch a medication or appointment reminder, which the
 * phone delivers on the settings made in PRD 5 and PRD 7. Somebody who
 * expected Sleep mode to silence a dose reminder and found it did not would
 * be right to be confused, so the screen says which is which.
 */
import { View } from 'react-native';

import { AppText, Card, Screen, SelectableCard } from '../../src/components';
import { PreferenceChoice } from '../../src/features/nura/components/PreferenceChoice';
import {
  MODE_DESCRIPTIONS,
  MODE_HEADING,
  MODE_LABELS,
  MODE_REMINDERS_NOTE,
  PROACTIVITY_INTRO,
  PROACTIVITY_LABELS,
} from '../../src/features/nura/copy';
import {
  useAssistantPreferences,
  useUpdatePreferences,
} from '../../src/features/nura/hooks';
import type { AssistantMode, ProactivityLevel } from '../../src/features/nura/types';
import { spacing } from '../../src/theme/tokens';

const LEVELS: ProactivityLevel[] = ['off', 'low', 'medium', 'high'];
const MODES: AssistantMode[] = ['normal', 'focus', 'sleep', 'privacy'];

export default function ProactivityScreen() {
  const preferences = useAssistantPreferences();
  const update = useUpdatePreferences();
  const current = preferences.data;

  return (
    <Screen>
      <View style={{ gap: spacing.md }}>
        <PreferenceChoice
          label="How often Nura speaks first"
          description={PROACTIVITY_INTRO}
          options={LEVELS}
          labels={PROACTIVITY_LABELS}
          value={current?.proactivity ?? 'low'}
          onChange={(proactivity) => update.mutate({ proactivity })}
          hint="Changes how often Nura raises something on the Nura tab"
        />

        <View style={{ gap: spacing.xs }}>
          <AppText variant="bodyStrong">{MODE_HEADING}</AppText>
          {MODES.map((mode) => (
            <SelectableCard
              key={mode}
              title={MODE_LABELS[mode] ?? mode}
              description={MODE_DESCRIPTIONS[mode] ?? ''}
              selected={current?.mode === mode}
              onPress={() => update.mutate({ mode })}
            />
          ))}
        </View>

        <Card>
          <AppText variant="caption" tone="secondary">
            {MODE_REMINDERS_NOTE}
          </AppText>
        </Card>
      </View>
    </Screen>
  );
}
