/**
 * Privacy & Security (PRD 13, sections 4 to 10).
 *
 * **One screen that reads the system, rather than a second place to configure
 * it.** Every control here is a link to the screen that already owns the
 * setting, and every claim is a sentence the server sent. Section 4 asks for
 * exactly that -- "reuse existing destination screens wherever they already
 * exist", "do not duplicate caregiver, memory, robot, or safety settings" --
 * and it is also the only way the screen can be trustworthy: a hub that kept
 * its own copy of what a caregiver can see would eventually disagree with the
 * permissions that actually apply.
 *
 * So the capability rows are PRD 10's, PRD 11's and PRD 12's own maps, chosen
 * from a state rather than written here (sections 9, 10 and 38); the counts
 * are read, not cached; and the two sentences somebody most needs are the ones
 * nobody would think to ask for -- that Privacy Mode is not a hardware switch
 * (section 5), and that Nura has never been tested on a physical phone or
 * robot (section 36).
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import {
  AppText,
  AsyncState,
  Card,
  DegradedModeBanner,
  ListGroup,
  ListRow,
  Screen,
  StatusChip,
  type StatusTone,
} from '../../src/components';
import { useIsOffline } from '../../src/hooks/useNetworkStatus';
import {
  HUB_INTRO,
  NO_ROBOT_LINKED,
  ROW_CAMERA_MIC,
  ROW_CAREGIVERS,
  ROW_CONVERSATIONS,
  ROW_DELETE,
  ROW_EXPORT,
  ROW_MEMORY,
  ROW_PRIVACY_MODE,
  ROW_ROBOT,
  ROW_SAFETY,
  SECTION_SECURITY,
  SECTION_WHAT_NURA_CAN_REACH,
  SECTION_WHAT_NURA_STORES,
  SECTION_WHO_CAN_SEE,
  SECTION_YOUR_DATA,
  caregiverSummary,
  conversationSummary,
  memorySummary,
} from '../../src/features/privacy/copy';
import { usePrivacySummary } from '../../src/features/privacy/hooks';
import type { CapabilityLine } from '../../src/features/privacy/types';
import { spacing } from '../../src/theme/tokens';

/**
 * How a capability state reads as a chip.
 *
 * `available` is the only positive tone. Everything else is neutral rather
 * than alarming: a microphone that is not connected is not a fault, and
 * colouring it as one would be the "unnecessary alarmist disclaimer" PRD 14
 * section 40 asks to be reviewed out.
 */
function toneFor(state: string): StatusTone {
  return state === 'available' ? 'success' : 'neutral';
}

function CapabilityRows({ lines }: { lines: CapabilityLine[] }) {
  return (
    <View style={{ gap: spacing.sm }}>
      {lines.map((line) => (
        <View
          key={line.key}
          accessible
          accessibilityLabel={`${line.label}. ${line.stateLabel}`}
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: spacing.sm,
          }}
        >
          <AppText variant="body" style={{ flex: 1 }}>
            {line.label}
          </AppText>
          <StatusChip label={line.stateLabel} tone={toneFor(line.state)} />
        </View>
      ))}
    </View>
  );
}

export default function PrivacyScreen() {
  const router = useRouter();
  const summary = usePrivacySummary();
  const isOffline = useIsOffline();
  const data = summary.data;

  return (
    <Screen
      onRefresh={() => void summary.refetch()}
      refreshing={summary.isRefetching && !summary.isLoading}
    >
      {isOffline ? <DegradedModeBanner kind="offline" /> : null}

      <AsyncState
        status={summary.isError ? 'error' : data ? 'success' : 'loading'}
        error={summary.error}
        onRetry={() => void summary.refetch()}
      >
        {data ? (
          <View style={{ gap: spacing.lg }}>
            <AppText variant="body" tone="secondary">
              {HUB_INTRO}
            </AppText>

            {/* --- what Nura stores (sections 5, 6 and 7) ----------------- */}
            <View style={{ gap: spacing.sm }}>
              <AppText variant="heading">{SECTION_WHAT_NURA_STORES}</AppText>
              <ListGroup>
                <ListRow
                  label={ROW_PRIVACY_MODE}
                  description={data.privacyModeNote}
                  value={data.privacyMode ? 'On' : 'Off'}
                  leadingIcon="eye-off-outline"
                  showChevron
                  onPress={() => router.push('/nura/proactivity')}
                  accessibilityHint="Opens Nura's modes, where Privacy Mode is set"
                />
                <ListRow
                  label={ROW_MEMORY}
                  description={memorySummary(data.activeMemoryCount, data.memoryCount)}
                  leadingIcon="bookmark-outline"
                  showChevron
                  onPress={() => router.push('/nura/memory')}
                  accessibilityHint="Opens what Nura remembers"
                />
                <ListRow
                  label={ROW_CONVERSATIONS}
                  description={conversationSummary(data.conversationCount)}
                  leadingIcon="chatbubbles-outline"
                  showChevron
                  onPress={() => router.push('/nura/history')}
                  accessibilityHint="Opens your conversations with Nura"
                />
              </ListGroup>
              {/* Section 5's last line. Privacy Mode changes how Nura
                  behaves; it is not a switch on any hardware. */}
              <AppText variant="caption" tone="secondary">
                {data.privacyModeLimit}
              </AppText>
            </View>

            {/* --- camera and microphone (section 6) ---------------------- */}
            <View style={{ gap: spacing.sm }}>
              <AppText variant="heading">{ROW_CAMERA_MIC}</AppText>
              <Card style={{ gap: spacing.sm }}>
                <AppText variant="body">{data.microphoneNote}</AppText>
                <AppText variant="body">{data.cameraNote}</AppText>
                <AppText variant="caption" tone="secondary">
                  {data.photoPermissionNote}
                </AppText>
                {data.robotLinked ? (
                  <CapabilityRows lines={data.robotInputCapabilities} />
                ) : null}
              </Card>
            </View>

            {/* --- who can see it (section 8) ----------------------------- */}
            <View style={{ gap: spacing.sm }}>
              <AppText variant="heading">{SECTION_WHO_CAN_SEE}</AppText>
              <ListGroup>
                <ListRow
                  label={ROW_CAREGIVERS}
                  description={caregiverSummary(data.caregivers.length)}
                  leadingIcon="people-outline"
                  showChevron
                  onPress={() => router.push('/caregivers')}
                  accessibilityHint="Opens caregivers and their permissions"
                />
              </ListGroup>
              {data.caregivers.length > 0 ? (
                <Card style={{ gap: spacing.sm }}>
                  {data.caregivers.map((caregiver) => (
                    <View key={caregiver.relationshipId} style={{ gap: spacing.xxs }}>
                      <AppText variant="bodyStrong">{caregiver.name}</AppText>
                      <AppText variant="caption" tone="secondary">
                        {caregiver.granted.length === 0
                          ? 'No categories shared'
                          : caregiver.granted.join(', ')}
                      </AppText>
                    </View>
                  ))}
                </Card>
              ) : null}
            </View>

            {/* --- safety (section 9) ------------------------------------- */}
            <View style={{ gap: spacing.sm }}>
              <AppText variant="heading">{ROW_SAFETY}</AppText>
              <ListGroup>
                <ListRow
                  label={ROW_SAFETY}
                  value={data.safetyMonitoringActive ? 'On' : 'Off'}
                  leadingIcon="shield-outline"
                  showChevron
                  onPress={() => router.push('/safety')}
                  accessibilityHint="Opens Safety Monitoring"
                />
              </ListGroup>
              {/* PRD 10's own map. Nothing here is written optimistically:
                  push, SMS and calling read not_configured because no
                  provider exists, not because a screen says so. */}
              <Card>
                <CapabilityRows lines={data.safetyCapabilities} />
              </Card>
            </View>

            {/* --- the robot (section 10) --------------------------------- */}
            <View style={{ gap: spacing.sm }}>
              <AppText variant="heading">{ROW_ROBOT}</AppText>
              {data.robotLinked ? (
                <>
                  <ListGroup>
                    <ListRow
                      label="Nura Device settings"
                      leadingIcon="hardware-chip-outline"
                      showChevron
                      onPress={() => router.push('/robot')}
                      accessibilityHint="Opens settings for Nura's own screen"
                    />
                  </ListGroup>
                  <Card style={{ gap: spacing.md }}>
                    <CapabilityRows lines={data.robotCapabilities} />
                    <View style={{ gap: spacing.sm }}>
                      {data.robotPreviews.map(([label, value]) => (
                        <View
                          key={label}
                          accessible
                          accessibilityLabel={`${label}. ${value}`}
                          style={{
                            flexDirection: 'row',
                            justifyContent: 'space-between',
                            gap: spacing.sm,
                          }}
                        >
                          <AppText variant="body" style={{ flex: 1 }}>
                            {label}
                          </AppText>
                          <AppText variant="bodyStrong">{value}</AppText>
                        </View>
                      ))}
                    </View>
                  </Card>
                </>
              ) : (
                <Card>
                  <AppText variant="body" tone="secondary">
                    {NO_ROBOT_LINKED}
                  </AppText>
                </Card>
              )}
            </View>

            {/* --- what Nura can reach (section 37) ----------------------- */}
            <View style={{ gap: spacing.sm }}>
              <AppText variant="heading">{SECTION_WHAT_NURA_CAN_REACH}</AppText>
              <Card style={{ gap: spacing.sm }}>
                {data.externalCapabilities.map((capability) => (
                  <AppText
                    key={capability.key}
                    variant="body"
                    tone="secondary"
                    accessibilityLabel={capability.stateLabel}
                  >
                    {capability.stateLabel}
                  </AppText>
                ))}
              </Card>
            </View>

            {/* --- export and deletion (sections 17 and 21) --------------- */}
            <View style={{ gap: spacing.sm }}>
              <AppText variant="heading">{SECTION_YOUR_DATA}</AppText>
              <ListGroup>
                <ListRow
                  label={ROW_EXPORT}
                  description={data.exportNote}
                  leadingIcon="download-outline"
                  showChevron
                  onPress={() => router.push('/privacy/export')}
                  accessibilityHint="Opens exporting your data"
                />
                <ListRow
                  label={ROW_DELETE}
                  leadingIcon="trash-outline"
                  showChevron
                  onPress={() => router.push('/privacy/delete')}
                  accessibilityHint="Opens deleting this profile's data"
                />
              </ListGroup>
            </View>

            {/* --- security status (section 4) ---------------------------- */}
            <View style={{ gap: spacing.sm }}>
              <AppText variant="heading">{SECTION_SECURITY}</AppText>
              <Card style={{ gap: spacing.sm }}>
                {data.securityStatements.map((statement) => (
                  <AppText key={statement} variant="body" tone="secondary">
                    {statement}
                  </AppText>
                ))}
              </Card>
              {/* Section 36: the developer status belongs in the docs, and
                  this is the one sentence a user needs from it. */}
              <AppText variant="caption" tone="secondary">
                {data.buildHonestyNote}
              </AppText>
            </View>
          </View>
        ) : null}
      </AsyncState>
    </Screen>
  );
}
