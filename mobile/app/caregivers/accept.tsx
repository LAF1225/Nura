/**
 * Accepting or declining an invitation (PRD 9, sections 14, 15 and 81).
 *
 * The screen section 15 describes, almost literally: what you will be able to
 * access, what you will not, and two buttons. Both lists come from the server as
 * labels, so there is no wording here that could describe a category differently
 * from the screen the primary user set it on.
 *
 * **Nothing is created for the caregiver.** Section 14 says a caregiver should
 * not need their own health profile unless they want to use Nura personally, and
 * nothing on this path makes one -- accepting takes the token and the signed-in
 * account, and that is all.
 *
 * The token arrives as a query parameter, which is how a deep link would hand it
 * over. Nura does not send the link (section 12), so in practice it is pasted;
 * either way it never reaches this screen from storage, and it is not kept after
 * the decision.
 */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { AppText, AsyncState, Button, Card, Screen } from '../../src/components';
import {
  CareErrorNote,
  AccessSummary,
} from '../../src/features/caregivers/components/CaregiverCards';
import {
  ACCEPT_BUTTON,
  ACCEPT_FAILED,
  ACCEPT_NO_PROFILE_NEEDED,
  ACCEPT_WILL_ACCESS,
  ACCEPT_WILL_NOT_ACCESS,
  acceptIntro,
  DECLINE_BUTTON,
  INVITATION_NOT_FOUND,
  inviteExpirySentence,
} from '../../src/features/caregivers/copy';
import {
  useAcceptInvitation,
  useDeclineInvitation,
  useInvitation,
  useSwitchCareContext,
} from '../../src/features/caregivers/hooks';
import { spacing } from '../../src/theme/tokens';

export default function AcceptInvitationScreen() {
  const { token } = useLocalSearchParams<{ token?: string }>();
  const router = useRouter();
  const invitation = useInvitation(token ?? null);
  const accept = useAcceptInvitation();
  const decline = useDeclineInvitation();
  const switchContext = useSwitchCareContext();
  const [failed, setFailed] = useState(false);

  const preview = invitation.data;

  return (
    <Screen>
      <AsyncState
        status={invitation.isError ? 'error' : 'success'}
        error={invitation.error}
        isEmpty={false}
        loadingLabel="Loading invitation"
        onRetry={() => void invitation.refetch()}
      >
        {invitation.isError || preview === undefined ? (
          <CareErrorNote message={INVITATION_NOT_FOUND} />
        ) : (
          <View style={{ gap: spacing.lg }}>
            <View style={{ gap: spacing.xs }}>
              <AppText variant="title" accessibilityRole="header">
                {acceptIntro(preview.profileName, preview.invitedName)}
              </AppText>
              <AppText variant="body" tone="secondary">
                {preview.roleLabel}
              </AppText>
            </View>

            <Card style={{ gap: spacing.md }}>
              <AccessSummary
                title={ACCEPT_WILL_ACCESS}
                items={preview.willAccess}
                tone="primary"
              />
              <AccessSummary
                title={ACCEPT_WILL_NOT_ACCESS}
                items={preview.willNotAccess}
              />
            </Card>

            <AppText variant="caption" tone="secondary">
              {ACCEPT_NO_PROFILE_NEEDED}
            </AppText>
            {preview.expiresAt ? (
              <AppText variant="caption" tone="secondary">
                {inviteExpirySentence(preview.expiresAt.slice(0, 10))}
              </AppText>
            ) : null}

            {failed ? <CareErrorNote message={ACCEPT_FAILED} /> : null}

            <View style={{ gap: spacing.sm }}>
              <Button
                label={ACCEPT_BUTTON}
                onPress={() => {
                  setFailed(false);
                  accept.mutate(token ?? '', {
                    onSuccess: (profile) => {
                      // Straight into their care, which is what somebody who
                      // just accepted was asking for.
                      switchContext({
                        kind: 'caregiver',
                        profileId: profile.profileId,
                        relationshipId: profile.relationshipId,
                      });
                      router.replace('/care-mode');
                    },
                    onError: () => setFailed(true),
                  });
                }}
                disabled={accept.isPending}
              />
              <Button
                label={DECLINE_BUTTON}
                variant="secondary"
                onPress={() =>
                  decline.mutate(token ?? '', {
                    onSuccess: () => router.replace('/(tabs)'),
                    onError: () => setFailed(true),
                  })
                }
                disabled={decline.isPending}
              />
            </View>
          </View>
        )}
      </AsyncState>
    </Screen>
  );
}
