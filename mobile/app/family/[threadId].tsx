/**
 * One care conversation (PRD 9, sections 31, 34-37, 71 and 72).
 *
 * Three things are worth reading rather than skimming.
 *
 * **The draft is kept and nothing is queued** (sections 71 and 72). What somebody
 * typed goes to AsyncStorage and comes back, and the banner says that it has not
 * been sent. There is no background retry: a message that went out an hour later
 * without the sender knowing is worse than one they resend themselves, and
 * section 72 only asks for `pending` until the backend confirms -- not for a queue.
 *
 * **A retry answers rather than repeats** (section 74). The send hook keeps one
 * client id across attempts, so a request that timed out after the server stored
 * it comes back as the message already there.
 *
 * **The check-ins offered depend on which side you are** (sections 35 and 36).
 * The person says how they are; the caregiver asks. The note under them says they
 * are messages and not alerts, because section 35 forbids inferring urgency from
 * one and somebody pressing "I need help with something" should know what it does.
 */
import { useLocalSearchParams } from 'expo-router';
import { View } from 'react-native';

import {
  AppText,
  AsyncState,
  Button,
  Card,
  Screen,
  TextField,
} from '../../src/components';
import {
  CHECK_INS_FROM_CAREGIVER,
  CHECK_INS_FROM_USER,
} from '../../src/features/caregivers/api';
import {
  CareErrorNote,
  FamilyMessageBubble,
} from '../../src/features/caregivers/components/CaregiverCards';
import {
  CHECK_IN_LABELS,
  CHECK_IN_NOTE,
  CHECK_IN_TITLE,
  DRAFT_KEPT,
  MESSAGE_FAILED,
  MESSAGE_PLACEHOLDER,
  MESSAGE_READ,
  MESSAGE_SEND,
  MESSAGE_SENDING,
  MESSAGE_SENT,
  THREAD_EMPTY,
} from '../../src/features/caregivers/copy';
import {
  useCareMode,
  useSendMessage,
  useThread,
} from '../../src/features/caregivers/hooks';
import {
  useMessageDraft,
  useMessageDraftStore,
} from '../../src/features/caregivers/stores';
import { spacing } from '../../src/theme/tokens';

export default function FamilyThreadScreen() {
  const { threadId } = useLocalSearchParams<{ threadId: string }>();
  const id = threadId ?? '';
  const mode = useCareMode();
  const thread = useThread(id);
  const send = useSendMessage();
  const draft = useMessageDraft(id);
  const setDraft = useMessageDraftStore((state) => state.setDraft);

  const mySide = mode.isCaregiverMode ? 'caregiver' : 'primary_user';
  const checkIns = mode.isCaregiverMode ? CHECK_INS_FROM_CAREGIVER : CHECK_INS_FROM_USER;
  const messages = thread.data?.messages ?? [];

  function sendTyped() {
    // Read at press time rather than from the render that queued this handler.
    const text = (useMessageDraftStore.getState().drafts[id] ?? '').trim();
    if (text.length === 0) return;
    send.mutate({ threadId: id, text });
  }

  return (
    <Screen
      onRefresh={() => void thread.refetch()}
      refreshing={thread.isRefetching && !thread.isLoading}
    >
      <View style={{ gap: spacing.md }}>
        <AsyncState
          status={thread.isError ? 'error' : 'success'}
          error={thread.error}
          isEmpty={messages.length === 0}
          emptyMessage={THREAD_EMPTY}
          loadingLabel="Loading messages"
          onRetry={() => void thread.refetch()}
        >
          <View style={{ gap: spacing.sm }}>
            {messages.map((message) => {
              const mine = message.side === mySide;
              return (
                <FamilyMessageBubble
                  key={message.id}
                  message={message}
                  mine={mine}
                  statusLabel={
                    mine ? (message.readAt ? MESSAGE_READ : MESSAGE_SENT) : undefined
                  }
                />
              );
            })}
          </View>
        </AsyncState>

        <View style={{ gap: spacing.xs }}>
          <TextField
            label={MESSAGE_PLACEHOLDER}
            value={draft}
            onChangeText={(text) => setDraft(id, text)}
            multiline
          />
          {draft.trim().length > 0 ? (
            <AppText variant="caption" tone="secondary">
              {DRAFT_KEPT}
            </AppText>
          ) : null}
          <Button
            label={send.isPending ? MESSAGE_SENDING : MESSAGE_SEND}
            onPress={sendTyped}
            disabled={draft.trim().length === 0 || send.isPending}
          />
          {send.isError ? <CareErrorNote message={MESSAGE_FAILED} /> : null}
        </View>

        <Card style={{ gap: spacing.xs }}>
          <AppText variant="bodyStrong">{CHECK_IN_TITLE}</AppText>
          {checkIns.map((code) => (
            <Button
              key={code}
              label={CHECK_IN_LABELS[code]}
              variant="secondary"
              onPress={() => send.mutate({ threadId: id, checkInCode: code })}
              disabled={send.isPending}
            />
          ))}
          <AppText variant="caption" tone="secondary">
            {CHECK_IN_NOTE}
          </AppText>
        </Card>
      </View>
    </Screen>
  );
}
