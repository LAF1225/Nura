/**
 * One conversation (PRD 8, sections 6, 14, 18, 46, 55 and 56).
 *
 * The screen is the PRD's own layout: the thread, then the composer. What is
 * worth reading is everything that hangs off a *reply*.
 *
 * **A failure is shown, not hidden.** When the model could not be reached the
 * reply is null and a `failure_message` comes back instead, with Try again
 * beside it. Nothing is invented and nothing is queued -- section 56 is
 * explicit on both, and the message the user typed is still in the thread
 * above (section 55).
 *
 * **A write waits for a press.** If Nura offered to add a question, the
 * pending card appears under its reply with Confirm and Cancel, and only
 * Confirm makes the change (section 14).
 *
 * **A memory is offered, never taken.** A durable preference noticed in what
 * the user said produces the section 94 card; pressing Remember is what
 * writes it.
 *
 * **A new symptom is handed to PRD 6.** Section 18 asks Nura to route into
 * the symptom workflow rather than discussing it loosely, so the offer is a
 * button to the real flow rather than a conversation about it.
 */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import {
  AppText,
  AsyncState,
  Button,
  Card,
  Screen,
  SkeletonCard,
} from '../../src/components';
import { OfflineBanner } from '../../src/components/today';
import { AssistantTypingIndicator } from '../../src/features/nura/components/AssistantTypingIndicator';
import {
  PrivacyModeBanner,
  SeriousModeBanner,
} from '../../src/features/nura/components/Banners';
import { ChatBubble } from '../../src/features/nura/components/ChatBubble';
import { ConversationComposer } from '../../src/features/nura/components/ConversationComposer';
import { MemorySuggestionCard } from '../../src/features/nura/components/MemoryCards';
import { PendingActionCard } from '../../src/features/nura/components/PendingActionCard';
import { useComposerStore } from '../../src/features/nura/composerStore';
import {
  CONVERSATION_EMPTY,
  GENERIC_FAILURE,
  JUST_ASKING,
  LOG_SYMPTOM,
  LOG_SYMPTOM_PROMPT,
  OFFLINE_NOTICE,
  RETRY,
} from '../../src/features/nura/copy';
import {
  useAddMemory,
  useAssistantPreferences,
  useConfirmAction,
  useConversation,
  useSendMessage,
} from '../../src/features/nura/hooks';
import type { MemorySuggestion } from '../../src/features/nura/types';
import { useIsOffline } from '../../src/hooks/useNetworkStatus';
import { spacing } from '../../src/theme/tokens';

export default function ConversationScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const conversationId = id ?? '';
  const router = useRouter();
  const isOffline = useIsOffline();

  const thread = useConversation(conversationId);
  const preferences = useAssistantPreferences();
  const send = useSendMessage(conversationId);
  const confirm = useConfirmAction(conversationId);
  const remember = useAddMemory();
  const clearDraft = useComposerStore((state) => state.clearDraft);

  // What came back from the last send, kept so the offer cards survive the
  // refetch that follows. Local state is fine here: nothing presses these
  // before a render has happened.
  const [suggestion, setSuggestion] = useState<MemorySuggestion | null>(null);
  const [offerSymptomLog, setOfferSymptomLog] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [lastSent, setLastSent] = useState<string | null>(null);

  const messages = thread.data?.messages ?? [];
  const privacy = preferences.data?.mode === 'privacy';
  const latestAssistant = [...messages].reverse().find((m) => m.role === 'assistant');
  const pending =
    latestAssistant?.pendingAction?.state === 'pending'
      ? { message: latestAssistant, action: latestAssistant.pendingAction }
      : null;

  const submit = (text: string) => {
    setSuggestion(null);
    setOfferSymptomLog(false);
    setFailure(null);
    setLastSent(text);
    send.mutate(text, {
      onSuccess: (result) => {
        if (result.reply !== null) {
          // The message is in the thread now, so the composer can let go of
          // it. A failure leaves the draft alone, ready for Try again.
          clearDraft(conversationId);
          setLastSent(null);
        }
        setFailure(result.failureMessage ?? (result.failure ? GENERIC_FAILURE : null));
        setSuggestion(result.memorySuggestion);
        setOfferSymptomLog(result.suggestSymptomLog);
      },
      onError: () => setFailure(GENERIC_FAILURE),
    });
  };

  return (
    <Screen
      onRefresh={() => void thread.refetch()}
      refreshing={thread.isRefetching && !thread.isLoading}
    >
      <View style={{ gap: spacing.sm }}>
        {isOffline ? <OfflineBanner /> : null}
        {privacy ? <PrivacyModeBanner /> : null}

        {thread.isLoading ? (
          <Card>
            <SkeletonCard lines={4} />
          </Card>
        ) : (
          <AsyncState
            status={thread.isError ? 'error' : 'success'}
            error={thread.error}
            isEmpty={messages.length === 0}
            emptyMessage={CONVERSATION_EMPTY}
            onRetry={() => void thread.refetch()}
          >
            <View style={{ gap: spacing.sm }}>
              {messages.map((message) => (
                <View key={message.id} style={{ gap: spacing.xxs }}>
                  {message.safetyMode === 'serious' ? <SeriousModeBanner /> : null}
                  <ChatBubble message={message} />
                </View>
              ))}
            </View>
          </AsyncState>
        )}

        {send.isPending ? <AssistantTypingIndicator /> : null}

        {isOffline ? (
          <Card>
            <AppText variant="body" tone="secondary">
              {OFFLINE_NOTICE}
            </AppText>
          </Card>
        ) : null}

        {failure !== null ? (
          <Card style={{ gap: spacing.sm }}>
            <AppText variant="body">{failure}</AppText>
            <Button
              label={RETRY}
              onPress={() => {
                if (lastSent !== null) submit(lastSent);
              }}
              disabled={lastSent === null || send.isPending}
              accessibilityHint="Sends your message again"
            />
          </Card>
        ) : null}

        {pending !== null ? (
          <PendingActionCard
            action={pending.action}
            busy={confirm.isPending}
            onRespond={(confirmed) =>
              confirm.mutate({ messageId: pending.message.id, confirmed })
            }
          />
        ) : null}

        {suggestion !== null ? (
          <MemorySuggestionCard
            suggestion={suggestion}
            busy={remember.isPending}
            onRemember={() =>
              remember.mutate(
                {
                  content: suggestion.content,
                  category: suggestion.category,
                  source: 'conversation',
                },
                { onSuccess: () => setSuggestion(null) }
              )
            }
            onDismiss={() => setSuggestion(null)}
          />
        ) : null}

        {offerSymptomLog ? (
          <Card style={{ gap: spacing.sm }}>
            <AppText variant="body">{LOG_SYMPTOM_PROMPT}</AppText>
            <View style={{ flexDirection: 'row', gap: spacing.xs }}>
              <Button
                label={LOG_SYMPTOM}
                onPress={() => {
                  setOfferSymptomLog(false);
                  router.push('/symptoms/log');
                }}
                accessibilityHint="Opens the symptom form, where it is saved properly"
                style={{ flex: 1 }}
              />
              <Button
                label={JUST_ASKING}
                variant="secondary"
                onPress={() => setOfferSymptomLog(false)}
                style={{ flex: 1 }}
              />
            </View>
          </Card>
        ) : null}

        <ConversationComposer
          conversationId={conversationId}
          onSend={submit}
          busy={send.isPending}
          disabled={isOffline}
        />
      </View>
    </Screen>
  );
}
