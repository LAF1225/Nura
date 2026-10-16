/**
 * Voice and language (PRD 8, sections 27-31 and 64).
 *
 * Every control here is stored and none of it does anything yet, and the
 * screen says so at the top. Section 27 asks for the preferences to exist
 * ahead of the voice; the honest way to ship that is a sentence explaining
 * why nothing speaks, not a settings page that looks broken.
 *
 * Language shows English and says more are coming, which is what section 31
 * asks for: state it clearly rather than faking translation support.
 *
 * Verbosity lives here rather than on Personality because it is the one
 * setting that changes what a *reply* is like rather than how it sounds --
 * and it carries section 30's promise that a shorter reply never drops a
 * safety point.
 */
import { View } from 'react-native';

import { AppText, Card, ListGroup, ListRow, Screen } from '../../src/components';
import { PreferenceChoice } from '../../src/features/nura/components/PreferenceChoice';
import {
  LANGUAGE_LABEL,
  LANGUAGE_NOTE,
  SPEED_LABEL,
  SPEED_LABELS,
  VERBOSITY_LABEL,
  VERBOSITY_LABELS,
  VERBOSITY_NOTE,
  VOICE_LABEL,
  VOICE_LABELS,
  VOICE_NOT_YET,
} from '../../src/features/nura/copy';
import {
  useAssistantPreferences,
  useUpdatePreferences,
} from '../../src/features/nura/hooks';
import type {
  AssistantVoice,
  SpeakingSpeed,
  Verbosity,
} from '../../src/features/nura/types';
import { spacing } from '../../src/theme/tokens';

const VOICES: AssistantVoice[] = ['calm', 'clear', 'warm', 'bright'];
const SPEEDS: SpeakingSpeed[] = ['slow', 'normal', 'fast'];
const VERBOSITIES: Verbosity[] = ['concise', 'balanced', 'detailed'];

export default function VoiceScreen() {
  const preferences = useAssistantPreferences();
  const update = useUpdatePreferences();
  const current = preferences.data;

  return (
    <Screen>
      <View style={{ gap: spacing.md }}>
        <PreferenceChoice
          label={VERBOSITY_LABEL}
          description={VERBOSITY_NOTE}
          options={VERBOSITIES}
          labels={VERBOSITY_LABELS}
          value={current?.verbosity ?? 'balanced'}
          onChange={(verbosity) => update.mutate({ verbosity })}
          hint="Changes how long Nura's replies are"
        />

        <Card>
          <AppText variant="caption" tone="secondary">
            {VOICE_NOT_YET}
          </AppText>
        </Card>

        <PreferenceChoice
          label={VOICE_LABEL}
          options={VOICES}
          labels={VOICE_LABELS}
          value={current?.voiceId ?? 'calm'}
          onChange={(voiceId) => update.mutate({ voiceId })}
          hint="Saved for when Nura can speak"
        />

        <PreferenceChoice
          label={SPEED_LABEL}
          options={SPEEDS}
          labels={SPEED_LABELS}
          value={current?.speakingSpeed ?? 'normal'}
          onChange={(speakingSpeed) => update.mutate({ speakingSpeed })}
          hint="Saved for when Nura can speak"
        />

        <View style={{ gap: spacing.xs }}>
          <AppText variant="bodyStrong">{LANGUAGE_LABEL}</AppText>
          <ListGroup>
            <ListRow label="English" value="Selected" />
          </ListGroup>
          <AppText variant="caption" tone="secondary">
            {LANGUAGE_NOTE}
          </AppText>
        </View>
      </View>
    </Screen>
  );
}
