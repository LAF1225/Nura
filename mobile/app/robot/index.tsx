/**
 * Nura Device: status, display, audio and companion (PRD 11, section 46).
 *
 * The screen section 46 sketches, with section 47's rule applied throughout:
 * **a control only exists where the capability does.** The Audio section is
 * not a set of disabled switches -- it is a sentence saying this Nura has not
 * reported a speaker, because a greyed-out volume slider still implies there
 * is a speaker to be loud.
 *
 * The exception is deliberate and is section 49: the three read-aloud
 * preferences are *kept* and shown even without a speaker, because somebody
 * may reasonably decide now that their messages should never be read out in a
 * room. Their wording says "when Nura has a working speaker", so the setting
 * does not imply the speaker works.
 *
 * **Reduced motion has three positions**, not two (sections 30 and 105).
 * Following the account's accessibility setting is the default and is its own
 * choice, so turning it off here does not mean "off" -- it means "decide
 * separately from my accessibility setting".
 *
 * Nothing on this screen can make the robot do anything. There is no "show
 * this now" control, because the queue is built from what is true rather than
 * from what somebody pressed (sections 51-54), and no acknowledgement can be
 * sent from a phone (sections 14 and 19).
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import {
  AppText,
  AsyncState,
  Button,
  Card,
  ListGroup,
  ListRow,
  Screen,
  ToggleRow,
} from '../../src/components';
import {
  MEDICATION_PRIVACY_LEVELS,
  SLEEP_SCREEN_MODES,
} from '../../src/features/robot/api';
import {
  RobotErrorNote,
  RobotSectionHeading,
  RobotStatusCard,
  UnavailableNote,
} from '../../src/features/robot/components/RobotCards';
import * as copy from '../../src/features/robot/copy';
import {
  LEVELS,
  nearestLevel,
  useRobotCapabilities,
  useRobotDevice,
  useRobotStatus,
  usePresentationPreferences,
  useUpdatePresentationPreferences,
} from '../../src/features/robot/hooks';
import type {
  MedicationPrivacyLevel,
  SleepScreenMode,
} from '../../src/features/robot/types';
import { spacing } from '../../src/theme/tokens';

export default function RobotScreen() {
  const router = useRouter();
  const { deviceId, device, isLoading, isError } = useRobotDevice();
  const status = useRobotStatus(deviceId);
  const capabilities = useRobotCapabilities(deviceId);
  const preferences = usePresentationPreferences(deviceId);
  const update = useUpdatePresentationPreferences(deviceId);

  if (deviceId === null) {
    return (
      <Screen>
        <AppText variant="title" accessibilityRole="header">
          {copy.ROBOT_TITLE}
        </AppText>
        <AsyncState
          status={isError ? 'error' : isLoading ? 'loading' : 'success'}
          loadingLabel="Looking for your Nura"
        >
          <Card style={{ gap: spacing.sm, marginTop: spacing.md }}>
            <AppText variant="bodyStrong">{copy.NO_DEVICE_TITLE}</AppText>
            <AppText variant="body" tone="secondary">
              {copy.NO_DEVICE_BODY}
            </AppText>
            <Button
              label={copy.SET_UP_DEVICE}
              onPress={() => router.push('/connect-device')}
            />
          </Card>
        </AsyncState>
      </Screen>
    );
  }

  const settings = preferences.data;
  const capability = capabilities.data;

  return (
    <Screen>
      <AppText variant="title" accessibilityRole="header">
        {copy.ROBOT_TITLE}
      </AppText>
      <AppText variant="body" tone="secondary" style={{ marginBottom: spacing.md }}>
        {copy.ROBOT_SUBTITLE}
      </AppText>

      <AsyncState
        status={
          status.isError || preferences.isError
            ? 'error'
            : settings === undefined
              ? 'loading'
              : 'success'
        }
        error={status.error ?? preferences.error}
        loadingLabel="Reading Nura’s settings"
        onRetry={() => {
          void status.refetch();
          void preferences.refetch();
          void capabilities.refetch();
        }}
      >
        {settings === undefined ? null : (
          <View style={{ gap: spacing.lg }}>
            {status.data ? <RobotStatusCard status={status.data} /> : null}
            {status.data && !status.data.setupComplete ? (
              <UnavailableNote message={copy.SETUP_INCOMPLETE} />
            ) : null}
            {capability ? (
              <AppText variant="caption" tone="secondary">
                {capability.hardwareNote}
              </AppText>
            ) : null}

            {update.isError ? <RobotErrorNote message={copy.SAVE_FAILED} /> : null}

            {/* --- display (sections 45, 30, 22, 31) --- */}
            <View style={{ gap: spacing.sm }}>
              <RobotSectionHeading title={copy.DISPLAY_TITLE} />
              {capability && !capability.displayAvailable ? (
                <UnavailableNote message={copy.CAPABILITIES_HINT} />
              ) : null}

              <ListGroup>
                {LEVELS.map((step) => (
                  <ListRow
                    key={`brightness-${step}`}
                    label={copy.BRIGHTNESS_LABELS[step] ?? `${step}%`}
                    role="radio"
                    selected={nearestLevel(settings.brightness) === step}
                    onPress={() => update.mutate({ brightness: step })}
                    accessibilityHint={copy.BRIGHTNESS_HINT}
                  />
                ))}
              </ListGroup>

              <ListGroup>
                <ListRow
                  label={copy.REDUCED_MOTION_FOLLOW}
                  description={
                    settings.reducedMotion === null
                      ? copy.REDUCED_MOTION_FOLLOWING
                      : undefined
                  }
                  role="radio"
                  selected={settings.reducedMotion === null}
                  onPress={() => update.mutate({ reducedMotion: null })}
                  accessibilityHint={copy.REDUCED_MOTION_HINT}
                />
                <ListRow
                  label="Reduced motion on"
                  role="radio"
                  selected={settings.reducedMotion === true}
                  onPress={() => update.mutate({ reducedMotion: true })}
                  accessibilityHint={copy.REDUCED_MOTION_HINT}
                />
                <ListRow
                  label="Reduced motion off"
                  role="radio"
                  selected={settings.reducedMotion === false}
                  onPress={() => update.mutate({ reducedMotion: false })}
                  accessibilityHint={copy.REDUCED_MOTION_HINT}
                />
              </ListGroup>

              <ListGroup>
                <ToggleRow
                  label={copy.FACE_ANIMATION_TITLE}
                  description={copy.FACE_ANIMATION_HINT}
                  value={settings.faceAnimationEnabled}
                  onChange={(value) => update.mutate({ faceAnimationEnabled: value })}
                />
                <ToggleRow
                  label={copy.MESSAGE_DISPLAY_TITLE}
                  description={copy.MESSAGE_DISPLAY_HINT}
                  value={settings.familyMessageDisplayEnabled}
                  onChange={(value) =>
                    update.mutate({ familyMessageDisplayEnabled: value })
                  }
                />
              </ListGroup>

              <RobotSectionHeading
                title={copy.PRIVACY_PREVIEW_TITLE}
                hint={copy.PRIVACY_PREVIEW_HINT}
              />
              <ListGroup>
                {MEDICATION_PRIVACY_LEVELS.map((option: MedicationPrivacyLevel) => (
                  <ListRow
                    key={option}
                    label={PRIVACY_LABELS[option]}
                    description={PRIVACY_DESCRIPTIONS[option]}
                    role="radio"
                    selected={settings.medicationPrivacyLevel === option}
                    onPress={() => update.mutate({ medicationPrivacyLevel: option })}
                  />
                ))}
              </ListGroup>

              <RobotSectionHeading
                title={copy.SLEEP_SCREEN_TITLE}
                hint={copy.SLEEP_SCREEN_HINT}
              />
              <ListGroup>
                {SLEEP_SCREEN_MODES.map((option: SleepScreenMode) => (
                  <ListRow
                    key={option}
                    label={SLEEP_LABELS[option]}
                    role="radio"
                    selected={settings.sleepScreenMode === option}
                    onPress={() => update.mutate({ sleepScreenMode: option })}
                  />
                ))}
              </ListGroup>
            </View>

            {/* --- audio (sections 43, 44, 47, 49) --- */}
            <View style={{ gap: spacing.sm }}>
              <RobotSectionHeading title={copy.AUDIO_TITLE} />
              {capability && !capability.audioAvailable ? (
                // Section 47: a sentence rather than disabled controls. A
                // greyed-out volume slider still implies a speaker.
                <UnavailableNote
                  message={
                    capability.capabilities.find((row) => row.key === 'speaker')
                      ?.stateLabel === 'Not fitted'
                      ? 'Not available on this device'
                      : 'This Nura has not reported a speaker'
                  }
                />
              ) : (
                <ListGroup>
                  {LEVELS.map((step) => (
                    <ListRow
                      key={`volume-${step}`}
                      label={copy.VOLUME_LABELS[step] ?? `${step}%`}
                      role="radio"
                      selected={nearestLevel(settings.volume) === step}
                      onPress={() => update.mutate({ volume: step })}
                      accessibilityHint={copy.VOLUME_HINT}
                    />
                  ))}
                </ListGroup>
              )}

              {/* Kept whatever the hardware says, which is section 49. */}
              <ListGroup>
                <ToggleRow
                  label={copy.READ_MEDICATIONS_TITLE}
                  description={copy.READ_MEDICATIONS_HINT}
                  value={settings.readMedicationsAloud}
                  onChange={(value) => update.mutate({ readMedicationsAloud: value })}
                />
                <ToggleRow
                  label={copy.READ_MESSAGES_TITLE}
                  description={copy.READ_MESSAGES_HINT}
                  value={settings.readMessagesAloud}
                  onChange={(value) => update.mutate({ readMessagesAloud: value })}
                />
                <ToggleRow
                  label={copy.READ_ASSISTANT_TITLE}
                  description={copy.READ_ASSISTANT_HINT}
                  value={settings.readAssistantAloud}
                  onChange={(value) => update.mutate({ readAssistantAloud: value })}
                />
              </ListGroup>
            </View>

            {/* --- the rest --- */}
            <ListGroup>
              <ListRow
                label={copy.CAPABILITIES_TITLE}
                description={copy.CAPABILITIES_HINT}
                leadingIcon="hardware-chip-outline"
                showChevron
                onPress={() => router.push('/robot/capabilities')}
              />
              <ListRow
                label={copy.HISTORY_TITLE}
                description={copy.HISTORY_HINT}
                leadingIcon="time-outline"
                showChevron
                onPress={() => router.push('/robot/history')}
              />
              <ListRow
                label={copy.PREVIEW_OPEN}
                description={copy.PREVIEW_HINT}
                leadingIcon="eye-outline"
                showChevron
                onPress={() => router.push('/robot/preview')}
              />
            </ListGroup>

            {device ? (
              <AppText variant="caption" tone="secondary">
                {device.displayName} · {device.hardwareId}
              </AppText>
            ) : null}
          </View>
        )}
      </AsyncState>
    </Screen>
  );
}

/**
 * The three privacy levels, in the app's words.
 *
 * Duplicated from the server's own labels on purpose: this is a *setting*
 * being offered rather than a state being reported, and section 22's own
 * wording is what the PRD puts in front of the user. The server's labels are
 * what the history and the capability list read.
 */
const PRIVACY_LABELS: Record<MedicationPrivacyLevel, string> = {
  full: 'Full details',
  name_only: 'Medication name only',
  private: 'Private reminder',
};

const PRIVACY_DESCRIPTIONS: Record<MedicationPrivacyLevel, string> = {
  full: 'Name, dose and time on the screen.',
  name_only: 'The name and the time, without the dose.',
  private: 'Only that a medication is due. Open the app for the details.',
};

const SLEEP_LABELS: Record<SleepScreenMode, string> = {
  dim: 'Dim the screen',
  sleeping_face: 'Sleeping face',
  blank: 'Blank screen',
};
