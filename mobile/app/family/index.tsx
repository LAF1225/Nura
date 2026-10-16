/**
 * The care conversations (PRD 9, sections 30, 32 and 37).
 *
 * A list of people and the last thing each said. Deliberately plain: section 32
 * rules out chat rooms, social feeds, reactions and communities, so there is no
 * avatar, no typing indicator and no presence dot -- the last of those would be a
 * claim about whether somebody is available that Nura cannot make.
 *
 * An unread count is the other side's unread messages, which is the only thing
 * section 37's "sent and read" supports. Nothing here says "delivered".
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import {
  AppText,
  AsyncState,
  Button,
  Card,
  ListRow,
  Screen,
  StatusChip,
} from '../../src/components';
import {
  CALLING_UNAVAILABLE,
  MESSAGES_EMPTY,
  MESSAGES_INTRO,
  unreadSentence,
} from '../../src/features/caregivers/copy';
import {
  useCaregiverHome,
  useCareMode,
  useCaregivers,
  useCreateThread,
  useThreads,
} from '../../src/features/caregivers/hooks';
import { spacing } from '../../src/theme/tokens';

export default function FamilyMessagesScreen() {
  const router = useRouter();
  const mode = useCareMode();
  const threads = useThreads();
  const createThread = useCreateThread();
  // Only the primary user can start a thread with somebody who has no thread
  // yet, so the caregiver list is only read in self mode.
  const caregivers = useCaregivers();
  const home = useCaregiverHome();

  const rows = threads.data?.threads ?? [];
  const started = new Set(rows.map((thread) => thread.relationshipId));
  const startable = mode.isCaregiverMode
    ? []
    : (caregivers.data?.caregivers ?? []).filter(
        (caregiver) =>
          caregiver.status === 'active' &&
          !started.has(caregiver.id) &&
          caregiver.permissions.some(
            (permission) => permission.key === 'communication' && permission.allowed
          )
      );

  const callingAvailable = home.data?.callingAvailable === true;

  return (
    <Screen
      onRefresh={() => void threads.refetch()}
      refreshing={threads.isRefetching && !threads.isLoading}
    >
      <View style={{ gap: spacing.md }}>
        <AppText variant="body" tone="secondary">
          {MESSAGES_INTRO}
        </AppText>

        <AsyncState
          status={threads.isError ? 'error' : 'success'}
          error={threads.error}
          isEmpty={rows.length === 0 && startable.length === 0}
          emptyMessage={MESSAGES_EMPTY}
          loadingLabel="Loading messages"
          onRetry={() => void threads.refetch()}
        >
          <View style={{ gap: spacing.md }}>
            {rows.map((thread) => (
              <Card key={thread.id} style={{ gap: spacing.xs }}>
                <View
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: spacing.sm,
                  }}
                >
                  <AppText variant="bodyStrong">{thread.withName}</AppText>
                  {thread.unread > 0 ? (
                    <StatusChip label={unreadSentence(thread.unread)} tone="warning" />
                  ) : null}
                </View>
                {thread.lastMessage ? (
                  <AppText variant="body" tone="secondary" numberOfLines={2}>
                    {thread.lastMessage.text ?? ''}
                  </AppText>
                ) : null}
                <ListRow
                  label="Open"
                  onPress={() => router.push(`/family/${thread.id}`)}
                  showChevron
                  accessibilityHint={`Opens your messages with ${thread.withName}`}
                />
              </Card>
            ))}

            {startable.map((caregiver) => (
              <Card key={caregiver.id} style={{ gap: spacing.xs }}>
                <AppText variant="bodyStrong">{caregiver.invitedName}</AppText>
                <Button
                  label="Start a conversation"
                  variant="secondary"
                  onPress={() =>
                    createThread.mutate(caregiver.id, {
                      onSuccess: (thread) => router.push(`/family/${thread.id}`),
                    })
                  }
                  disabled={createThread.isPending}
                />
              </Card>
            ))}
          </View>
        </AsyncState>

        {/* Said once, here, rather than as a Call button that cannot work
            (section 38). */}
        {!callingAvailable ? (
          <AppText variant="caption" tone="secondary">
            {CALLING_UNAVAILABLE}
          </AppText>
        ) : null}
      </View>
    </Screen>
  );
}
