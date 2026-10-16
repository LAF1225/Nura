/**
 * Personality (PRD 8, sections 22-24 and 62).
 *
 * A preset writes the five dials and then stops mattering: nudging one
 * afterwards leaves the other four alone, and the screen says "Adjusted"
 * rather than pretending the preset still describes the settings.
 *
 * The note at the bottom is section 24 said out loud. Personality must never
 * weaken safety behaviour, and telling the user that is better than only
 * enforcing it behind the screen -- somebody who turns humour up should know
 * what it does *not* change.
 */
import { View } from 'react-native';

import { AppText, Card, Screen, SelectableCard } from '../../src/components';
import { PreferenceChoice } from '../../src/features/nura/components/PreferenceChoice';
import {
  LEVEL_LABELS,
  PERSONALITY_INTRO,
  PERSONALITY_SAFETY_NOTE,
  PRESET_ADJUSTED,
  PRESET_DESCRIPTIONS,
  PRESET_HEADING,
  PRESET_LABELS,
  TRAIT_LABELS,
} from '../../src/features/nura/copy';
import {
  useAssistantPreferences,
  useUpdatePreferences,
} from '../../src/features/nura/hooks';
import type { PersonalityLevel, PersonalityPreset } from '../../src/features/nura/types';
import { spacing } from '../../src/theme/tokens';

const PRESETS: PersonalityPreset[] = ['gentle', 'friendly', 'focused', 'professional'];
const LEVELS: PersonalityLevel[] = ['low', 'medium', 'high'];

/** The four dials this screen owns. Proactivity has a screen of its own. */
const TRAITS = ['warmth', 'humour', 'talkativeness', 'reminderFirmness'] as const;

export default function PersonalityScreen() {
  const preferences = useAssistantPreferences();
  const update = useUpdatePreferences();
  const current = preferences.data;

  return (
    <Screen>
      <View style={{ gap: spacing.md }}>
        <AppText variant="body" tone="secondary">
          {PERSONALITY_INTRO}
        </AppText>

        <View style={{ gap: spacing.xs }}>
          <AppText variant="bodyStrong">{PRESET_HEADING}</AppText>
          {PRESETS.map((preset) => (
            <SelectableCard
              key={preset}
              title={
                current?.personalityPreset === preset && current?.matchesPreset === false
                  ? `${PRESET_LABELS[preset]} (${PRESET_ADJUSTED})`
                  : (PRESET_LABELS[preset] ?? preset)
              }
              description={PRESET_DESCRIPTIONS[preset] ?? ''}
              selected={current?.personalityPreset === preset}
              onPress={() => update.mutate({ personalityPreset: preset })}
            />
          ))}
        </View>

        {current !== undefined ? (
          <View style={{ gap: spacing.md }}>
            {TRAITS.map((trait) => (
              <PreferenceChoice
                key={trait}
                label={TRAIT_LABELS[trait] ?? trait}
                options={LEVELS}
                labels={LEVEL_LABELS}
                value={current[trait]}
                onChange={(level) => update.mutate({ [trait]: level })}
                hint="Changes how Nura sounds"
              />
            ))}
          </View>
        ) : null}

        <Card>
          <AppText variant="caption" tone="secondary">
            {PERSONALITY_SAFETY_NOTE}
          </AppText>
        </Card>
      </View>
    </Screen>
  );
}
