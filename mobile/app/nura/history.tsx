/**
 * Conversation history (PRD 8, sections 8 and 61).
 *
 * Threads, not one endless log. Each row opens, archives or deletes one
 * conversation, and the delete confirmation says exactly what goes and what
 * stays -- section 61 is a promise about medications, symptoms, appointments
 * and memories surviving, and a user should be able to see it kept rather
 * than take it on trust.
 *
 * Archived threads are hidden behind a toggle rather than lost: archiving is
 * for tidying, and deleting is the real thing.
 */
import { useRouter } from 'expo-router';
import { Alert, View } from 'react-native';

import {
  AppText,
  AsyncState,
  Button,
  Card,
  Screen,
  SkeletonCard,
} from '../../src/components';
import {
  ARCHIVED_LABEL,
  ARCHIVE_CONVERSATION,
  CANCEL,
  DELETE_CONVERSATION,
  DELETE_CONVERSATION_HINT,
  HIDE_ARCHIVED,
  HISTORY_EMPTY,
  SHOW_ARCHIVED,
  UNARCHIVE_CONVERSATION,
} from '../../src/features/nura/copy';
import {
  useConversations,
  useDeleteConversation,
  useUpdateConversation,
} from '../../src/features/nura/hooks';
import { useHistoryListStore } from '../../src/features/nura/listStore';
import { spacing } from '../../src/theme/tokens';

function ConversationCard({
  id,
  title,
  archived,
  onOpen,
  onDelete,
}: {
  id: string;
  title: string;
  archived: boolean;
  onOpen: () => void;
  onDelete: () => void;
}) {
  const update = useUpdateConversation(id);

  return (
    <Card style={{ gap: spacing.xs }}>
      <AppText variant="bodyStrong">{title}</AppText>
      {archived ? (
        <AppText variant="caption" tone="secondary">
          {ARCHIVED_LABEL}
        </AppText>
      ) : null}

      <View style={{ flexDirection: 'row', gap: spacing.xs }}>
        <Button
          label="Open"
          variant="secondary"
          onPress={onOpen}
          accessibilityLabel={`Open: ${title}`}
          style={{ flex: 1 }}
        />
        <Button
          label={archived ? UNARCHIVE_CONVERSATION : ARCHIVE_CONVERSATION}
          variant="secondary"
          onPress={() => update.mutate({ archived: !archived })}
          accessibilityLabel={
            archived
              ? `${UNARCHIVE_CONVERSATION}: ${title}`
              : `${ARCHIVE_CONVERSATION}: ${title}`
          }
          style={{ flex: 1 }}
        />
        <Button
          label="Delete"
          variant="ghost"
          onPress={onDelete}
          accessibilityLabel={`${DELETE_CONVERSATION}: ${title}`}
          accessibilityHint={DELETE_CONVERSATION_HINT}
          style={{ flex: 1 }}
        />
      </View>
    </Card>
  );
}

export default function HistoryScreen() {
  const router = useRouter();
  // In a store so a press re-renders, the same reason the appointment scope
  // tabs are (see features/nura/listStore.ts).
  const showArchived = useHistoryListStore((state) => state.showArchived);
  const setShowArchived = useHistoryListStore((state) => state.setShowArchived);
  const list = useConversations(showArchived);
  const remove = useDeleteConversation();

  const conversations = list.data?.conversations ?? [];

  const confirmDelete = (id: string, title: string) => {
    Alert.alert(DELETE_CONVERSATION, `${title}\n\n${DELETE_CONVERSATION_HINT}`, [
      { text: CANCEL, style: 'cancel' },
      {
        text: DELETE_CONVERSATION,
        style: 'destructive',
        onPress: () => remove.mutate(id),
      },
    ]);
  };

  return (
    <Screen
      onRefresh={() => void list.refetch()}
      refreshing={list.isRefetching && !list.isLoading}
    >
      <View style={{ gap: spacing.md }}>
        <Button
          label={showArchived ? HIDE_ARCHIVED : SHOW_ARCHIVED}
          variant="secondary"
          onPress={() => setShowArchived(!showArchived)}
        />

        {list.isLoading ? (
          <Card>
            <SkeletonCard lines={3} />
          </Card>
        ) : (
          <AsyncState
            status={list.isError ? 'error' : 'success'}
            error={list.error}
            isEmpty={conversations.length === 0}
            emptyMessage={HISTORY_EMPTY}
            onRetry={() => void list.refetch()}
          >
            <View style={{ gap: spacing.xs }}>
              {conversations.map((conversation) => (
                <ConversationCard
                  key={conversation.id}
                  id={conversation.id}
                  title={conversation.title}
                  archived={conversation.archivedAt !== null}
                  onOpen={() =>
                    router.push({
                      pathname: '/nura/[id]',
                      params: { id: conversation.id },
                    })
                  }
                  onDelete={() => confirmDelete(conversation.id, conversation.title)}
                />
              ))}
            </View>
          </AsyncState>
        )}
      </View>
    </Screen>
  );
}
