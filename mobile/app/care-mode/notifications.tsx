/**
 * What a caregiver wants to hear about, for one person (PRD 9, sections 48, 94).
 *
 * Per supported person, not per account: somebody helping two parents may want
 * everything about one and only messages about the other.
 *
 * `safety_alerts` can be switched on and is stored faithfully, and the line under
 * it says plainly that nothing will be sent. Section 48 says not to activate
 * safety alerts until PRD 10 exists and section 94 not to fabricate one, so a
 * toggle that quietly promised alerts would be the thing both forbid.
 *
 * None of this gates anything in the app. There is no push notification for a
 * family message yet, and these are the preferences the feature will find already
 * answered when there is -- which is how PRD 3 handled the check-in reminder.
 */
import { View } from 'react-native';

import { AppText, AsyncState, Card, Screen, ToggleRow } from '../../src/components';
import { CAREGIVER_NOTIFICATION_KEYS } from '../../src/features/caregivers/api';
import {
  CARE_NOTIFICATIONS_NOT_DELIVERED,
  CAREGIVER_NOTIFICATION_LABELS,
  SAFETY_ALERTS_NOTE,
} from '../../src/features/caregivers/copy';
import {
  useCareMode,
  useSupportedProfiles,
  useUpdateCaregiverNotifications,
} from '../../src/features/caregivers/hooks';
import { spacing } from '../../src/theme/tokens';

export default function CaregiverNotificationsScreen() {
  const mode = useCareMode();
  const supported = useSupportedProfiles();
  const update = useUpdateCaregiverNotifications();
  const relationship = mode.relationship;

  return (
    <Screen>
      <AsyncState
        status={supported.isError ? 'error' : 'success'}
        error={supported.error}
        isEmpty={relationship === null}
        emptyMessage="Choose someone you support first."
        loadingLabel="Loading"
        onRetry={() => void supported.refetch()}
      >
        {relationship === null ? null : (
          <View style={{ gap: spacing.md }}>
            <AppText variant="body" tone="secondary">
              {`What Nura tells you about ${relationship.profileName}.`}
            </AppText>

            {CAREGIVER_NOTIFICATION_KEYS.map((key) => (
              <View key={key} style={{ gap: spacing.xxs }}>
                <ToggleRow
                  label={CAREGIVER_NOTIFICATION_LABELS[key] ?? key}
                  value={relationship.notifications[key]}
                  onChange={(value) => update.mutate({ [key]: value })}
                />
                {key === 'safety_alerts' ? (
                  <AppText
                    variant="caption"
                    tone="secondary"
                    style={{ paddingHorizontal: spacing.md }}
                  >
                    {SAFETY_ALERTS_NOTE}
                  </AppText>
                ) : null}
              </View>
            ))}

            <Card>
              <AppText variant="caption" tone="secondary">
                {CARE_NOTIFICATIONS_NOT_DELIVERED}
              </AppText>
            </Card>
          </View>
        )}
      </AsyncState>
    </Screen>
  );
}
