/**
 * What the primary user hears about from the people helping them (PRD 9, s48).
 *
 * The other half of section 48. These live on the account, alongside the
 * check-in reminder preference PRD 3 added, because that is where per-account
 * notification preferences already are -- and because the person holding the
 * phone is the one being notified.
 *
 * **None of these gates anything in the app.** Section 48 requires an approval
 * request to stay visible in-app even when push is disabled, so the care-request
 * list and the Today card ignore all four. The sentence at the top says so,
 * because somebody turning everything off should know they will still be asked.
 *
 * Nothing is delivered yet: there is no push for a family message or a care
 * request. These are the answers the feature will find already given, which is
 * how PRD 3 handled the daily check-in reminder.
 */
import { View } from 'react-native';

import { AppText, AsyncState, Card, Screen, ToggleRow } from '../../src/components';
import { CARE_NOTIFICATION_FIELDS } from '../../src/features/caregivers/api';
import {
  CARE_NOTIFICATION_LABELS,
  CARE_NOTIFICATIONS_NOT_DELIVERED,
  CARE_NOTIFICATIONS_INTRO,
} from '../../src/features/caregivers/copy';
import { useAccount, useUpdateSettings } from '../../src/hooks/useOnboarding';
import { spacing } from '../../src/theme/tokens';

export default function CareNotificationsScreen() {
  const account = useAccount();
  const update = useUpdateSettings();
  const settings = account.data?.settings;

  return (
    <Screen>
      <AsyncState
        status={account.isError ? 'error' : 'success'}
        error={account.error}
        isEmpty={settings === undefined}
        emptyMessage="Those settings could not be loaded."
        loadingLabel="Loading"
        onRetry={() => void account.refetch()}
      >
        {settings === undefined ? null : (
          <View style={{ gap: spacing.md }}>
            <AppText variant="body" tone="secondary">
              {CARE_NOTIFICATIONS_INTRO}
            </AppText>

            {CARE_NOTIFICATION_FIELDS.map(({ key, field }) => (
              <ToggleRow
                key={key}
                label={CARE_NOTIFICATION_LABELS[key] ?? key}
                value={settings[field]}
                onChange={(value) => update.mutate({ [field]: value })}
              />
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
