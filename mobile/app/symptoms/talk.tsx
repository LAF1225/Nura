/**
 * Talk to Nura -- the guided symptom conversation (PRD 6, ss26-29, 46, 67).
 *
 * A short guided chat that fills the same draft the manual form fills, and ends
 * on the same review screen (PRD 6, section 4). Everything about *what* to ask is
 * in `conversation/questions.ts` and everything about *reading an answer* is in
 * `conversation/extract.ts`; this screen renders bubbles and forwards taps, which
 * is why the interesting behaviour is testable without rendering anything.
 *
 * Three things it is careful about.
 *
 * **It is not an assistant** (PRD 6, section 27). There is no model behind it and
 * it makes no claim to understand. The intro says what it is, and the review
 * screen is where the user corrects whatever the rules got wrong.
 *
 * **Every question can be tapped as well as typed** (PRD 6, section 67). Somebody
 * who finds typing hard can complete the whole flow with the choice buttons, and
 * "Skip this" is always one of them.
 *
 * **It can be left at any point.** "That's everything" ends the conversation and
 * goes to the review screen, because somebody who has said what they wanted to say
 * should not have to answer four more questions to save it.
 */
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ScrollView, View } from 'react-native';

import {
  AppText,
  Button,
  Card,
  Screen,
  SkeletonCard,
  TextField,
} from '../../src/components';
import {
  ConversationBubble,
  ConversationChoices,
} from '../../src/features/symptoms/components/Conversation';
import { useSymptomDraftStore } from '../../src/features/symptoms/draftStore';
import { GUIDED_INTRO } from '../../src/features/symptoms/safetyMessages';
import { spacing } from '../../src/theme/tokens';

export default function TalkToNuraScreen() {
  const router = useRouter();
  const scroller = useRef<ScrollView>(null);

  const draft = useSymptomDraftStore((state) => state.draft);
  const conversation = useSymptomDraftStore((state) => state.conversation);
  const episodeName = useSymptomDraftStore((state) => state.episodeName);
  const start = useSymptomDraftStore((state) => state.start);
  const say = useSymptomDraftStore((state) => state.say);
  const tap = useSymptomDraftStore((state) => state.tap);
  const endConversation = useSymptomDraftStore((state) => state.endConversation);

  // The text box is the one piece of local state on this screen: it is cleared
  // the moment it is sent, and everything that matters afterwards lives in the
  // store.
  const [message, setMessage] = useState('');

  // On focus rather than on mount, and guarded. A plain effect keyed on `draft`
  // would start a fresh empty conversation on this screen the moment a save
  // cleared the draft -- while the screen was sitting unfocused in the back
  // stack -- and the overview would then offer to resume a description nobody
  // had written.
  useFocusEffect(
    useCallback(() => {
      if (draft === null || conversation === null) start('guided_app');
    }, [draft, conversation, start])
  );

  useEffect(() => {
    // New turns arrive at the bottom.
    scroller.current?.scrollToEnd({ animated: true });
  }, [conversation?.turns.length]);

  // One render before the effect above creates a draft.
  if (draft === null || conversation === null) {
    return (
      <Screen>
        <Card>
          <SkeletonCard lines={2} label="Getting ready" />
        </Card>
      </Screen>
    );
  }

  const send = () => {
    const text = message.trim();
    if (text.length === 0) return;
    setMessage('');
    say(text);
  };

  const choices = conversation.pendingConfirmation
    ? [
        { label: 'Yes', value: 'yes' },
        { label: 'No', value: 'no' },
        { label: 'I’m not sure', value: 'not sure' },
      ]
    : (conversation.current?.choices ?? []);

  return (
    <Screen padded scrollable={false}>
      <View style={{ flex: 1, gap: spacing.md }}>
        <AppText variant="caption" tone="secondary">
          {GUIDED_INTRO}
        </AppText>

        <ScrollView
          ref={scroller}
          style={{ flex: 1 }}
          contentContainerStyle={{ gap: spacing.sm, paddingBottom: spacing.md }}
          accessibilityLabel={
            episodeName
              ? `Conversation about your ${episodeName.toLowerCase()}`
              : 'Conversation with Nura'
          }
        >
          {conversation.turns.map((turn) => (
            <ConversationBubble key={turn.id} turn={turn} />
          ))}
        </ScrollView>

        <View style={{ gap: spacing.sm, paddingBottom: spacing.md }}>
          {conversation.finished ? (
            <Card style={{ gap: spacing.sm }}>
              <AppText variant="body" tone="secondary">
                That is everything Nura needs to ask.
              </AppText>
              <Button
                label="Review and save"
                onPress={() => router.push('/symptoms/review')}
                accessibilityHint="Shows everything Nura has, before it is saved"
              />
            </Card>
          ) : (
            <>
              <ConversationChoices choices={choices} onChoose={tap} />

              <TextField
                label="Your answer"
                value={message}
                onChangeText={setMessage}
                onSubmitEditing={send}
                returnKeyType="send"
                placeholder="Type your answer"
                multiline
                maxLength={500}
              />

              <View style={{ flexDirection: 'row', gap: spacing.xs }}>
                <Button
                  label="Send"
                  onPress={send}
                  disabled={message.trim().length === 0}
                  style={{ flex: 1 }}
                />
                <Button
                  label="That’s everything"
                  variant="secondary"
                  onPress={endConversation}
                  style={{ flex: 1 }}
                  accessibilityHint="Stops the questions and goes to the review screen"
                />
              </View>
            </>
          )}
        </View>
      </View>
    </Screen>
  );
}
