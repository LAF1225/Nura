/**
 * Choosing how long to be watched over (PRD 10, sections 5, 6, 7, 8 and 59).
 *
 * **Four durations and no fifth.** Section 5 locks the presets and says not
 * to invent a hidden monitoring period; the app offers exactly those, and the
 * server works out the instant from the mode it is sent (section 61).
 *
 * **"Until bedtime" needs a bedtime** (section 6). Nura does not infer one
 * from behaviour, so choosing it without one is refused by the server with
 * `bedtime_not_set` -- and this screen says so and offers the setting rather
 * than letting somebody press Start into an error.
 *
 * **The second prompt's timing is stated, not implied** (section 8). Twenty
 * seconds, whatever the first wait was, written on the toggle.
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { AppText, Button, Card, ListRow, Screen, ToggleRow } from '../../src/components';
import { SafetyErrorNote } from '../../src/features/safety/components/SafetyCards';
import { useAccount, useUpdateSettings } from '../../src/hooks/useOnboarding';
import {
  BEDTIME_HINT,
  BEDTIME_MISSING,
  BEDTIME_TITLE,
  DURATION_LABELS,
  DURATION_ORDER,
  DURATION_TITLE,
  SECOND_PROMPT_HINT,
  SECOND_PROMPT_TITLE,
  START_MONITORING,
  timeoutLabel,
  TIMEOUT_HINT,
  TIMEOUT_OPTIONS,
  TIMEOUT_TITLE,
} from '../../src/features/safety/copy';
import { useStartMonitoring } from '../../src/features/safety/hooks';
import { useSafetyFormStore } from '../../src/features/safety/stores';
import { spacing } from '../../src/theme/tokens';
import type { DurationMode, ResponseTimeout } from '../../src/features/safety/types';

export default function StartMonitoringScreen() {
  const router = useRouter();
  const start = useStartMonitoring();
  const account = useAccount();
  const durationMode = useSafetyFormStore((state) => state.durationMode);
  const responseTimeout = useSafetyFormStore((state) => state.responseTimeout);
  const secondPrompt = useSafetyFormStore((state) => state.secondPrompt);
  const setDurationMode = useSafetyFormStore((state) => state.setDurationMode);
  const setResponseTimeout = useSafetyFormStore((state) => state.setResponseTimeout);
  const setSecondPrompt = useSafetyFormStore((state) => state.setSecondPrompt);

  const bedtime = account.data?.settings?.safetyBedtime ?? null;
  const needsBedtime = durationMode === 'until_bedtime' && bedtime === null;

  function press() {
    const state = useSafetyFormStore.getState();
    if (state.durationMode === 'until_bedtime' && bedtime === null) return;
    start.mutate(
      {
        durationMode: state.durationMode as Exclude<DurationMode, 'custom'>,
        responseTimeoutSeconds: state.responseTimeout,
        secondPromptEnabled: state.secondPrompt,
      },
      { onSuccess: () => router.back() }
    );
  }

  return (
    <Screen>
      <View style={{ gap: spacing.lg }}>
        <Card style={{ gap: spacing.xs }}>
          <AppText variant="heading">{DURATION_TITLE}</AppText>
          {DURATION_ORDER.map((mode) => (
            <ListRow
              key={mode}
              label={DURATION_LABELS[mode]}
              role="radio"
              selected={durationMode === mode}
              onPress={() => setDurationMode(mode)}
            />
          ))}
          {needsBedtime ? (
            <View style={{ gap: spacing.xxs }}>
              <SafetyErrorNote message={BEDTIME_MISSING} />
              <AppText variant="caption" tone="secondary">
                {BEDTIME_HINT}
              </AppText>
              <BedtimeField />
            </View>
          ) : null}
          {bedtime && durationMode === 'until_bedtime' ? (
            <AppText variant="caption" tone="secondary">
              {`${BEDTIME_TITLE}: ${bedtime}`}
            </AppText>
          ) : null}
        </Card>

        <Card style={{ gap: spacing.xs }}>
          <AppText variant="heading">{TIMEOUT_TITLE}</AppText>
          <AppText variant="body" tone="secondary">
            {TIMEOUT_HINT}
          </AppText>
          {TIMEOUT_OPTIONS.map((seconds) => (
            <ListRow
              key={seconds}
              label={timeoutLabel(seconds)}
              role="radio"
              selected={responseTimeout === seconds}
              onPress={() => setResponseTimeout(seconds as ResponseTimeout)}
            />
          ))}
        </Card>

        <Card style={{ gap: spacing.xs }}>
          <ToggleRow
            label={SECOND_PROMPT_TITLE}
            description={SECOND_PROMPT_HINT}
            value={secondPrompt}
            onChange={setSecondPrompt}
          />
        </Card>

        {start.isError ? (
          <SafetyErrorNote message="Monitoring could not be started. Please try again." />
        ) : null}

        <Button
          label={START_MONITORING}
          onPress={press}
          disabled={start.isPending || needsBedtime}
        />
      </View>
    </Screen>
  );
}

/**
 * The bedtime setting, offered where it is needed (section 6).
 *
 * Section 6 says to prompt for a time when none is configured, rather than
 * inferring one. Putting the field here means the prompt and the fix are the
 * same screen -- a person who chose "Until bedtime" is told what is missing
 * and can supply it without going looking.
 */
function BedtimeField() {
  const update = useUpdateSettings();
  const options = ['21:00', '22:00', '22:30', '23:00'];
  return (
    <View style={{ gap: spacing.xxs }}>
      {options.map((value) => (
        <ListRow
          key={value}
          label={value}
          role="radio"
          selected={false}
          onPress={() => update.mutate({ safetyBedtime: value })}
          accessibilityHint="Sets your bedtime"
        />
      ))}
    </View>
  );
}
