/**
 * The Nura tab (PRD 8, section 5).
 *
 * The assistant is the point of the screen, so the conversation button is the
 * first thing on it and everything else is below. Recent threads next,
 * because reopening one is the second commonest thing somebody comes here to
 * do (section 8), then the settings that shape how Nura talks.
 *
 * The robot's status card from PRD 3 stays. It answers "is my Nura there?",
 * which is what this tab was opened for before there was an assistant -- and
 * PRD 8 section 4 is explicit that none of this depends on the robot being
 * there at all.
 *
 * Proactive prompts sit above the conversation because they are the one thing
 * on the screen that is time-sensitive, and each one can be waved away for
 * good (sections 35 and 36).
 */
import { useRouter } from 'expo-router';
import { Image, View } from 'react-native';

import { AppText, Button, Card, ListGroup, ListRow, Screen } from '../../src/components';
import { NuraStatusCard } from '../../src/components/today';
import { PrivacyModeBanner } from '../../src/features/nura/components/Banners';
import { ProactivePromptCard } from '../../src/features/nura/components/ProactivePromptCard';
import {
  ASSISTANT_UNAVAILABLE,
  INSTRUCTIONS_LINK,
  MEMORY_LINK,
  NEW_CONVERSATION,
  NURA_INTRO,
  PERSONALITY_LINK,
  PROACTIVITY_LINK,
  RECENT_HEADING,
  SEE_ALL_CONVERSATIONS,
  SETTINGS_HEADING,
  START_CONVERSATION,
  VOICE_LINK,
} from '../../src/features/nura/copy';
import {
  useAssistantHome,
  useDismissPrompt,
  useStartConversation,
} from '../../src/features/nura/hooks';
import { useToday } from '../../src/hooks/useToday';
import { spacing } from '../../src/theme/tokens';

const BRAND_MARK = require('../../assets/branding/nura-mark-transparent.png');

export default function NuraScreen() {
  const router = useRouter();
  const today = useToday();
  const home = useAssistantHome();
  const start = useStartConversation();
  const dismiss = useDismissPrompt();

  const recent = home.data?.recentConversations ?? [];
  const prompts = home.data?.prompts ?? [];
  const available = home.data?.assistantAvailable ?? false;
  const privacy = home.data?.preferences.mode === 'privacy';

  const openConversation = (id: string) =>
    router.push({ pathname: '/nura/[id]', params: { id } });

  return (
    <Screen
      onRefresh={() => void home.refetch()}
      refreshing={home.isRefetching && !home.isLoading}
    >
      <View style={{ alignItems: 'center', gap: spacing.sm, marginVertical: spacing.lg }}>
        <Image
          source={BRAND_MARK}
          accessibilityElementsHidden
          importantForAccessibility="no"
          style={{ width: 72, height: 72 }}
          resizeMode="contain"
        />
        <AppText variant="title">Nura</AppText>
      </View>

      <View style={{ gap: spacing.md }}>
        {privacy ? <PrivacyModeBanner /> : null}

        {/* Shown only once the home request has answered: an "assistant not
            set up" notice that turns out to be wrong is worse than a
            moment's wait (PRD 8, section 55). */}
        {home.data !== undefined && !available ? (
          <Card>
            <AppText variant="body" tone="secondary">
              {ASSISTANT_UNAVAILABLE}
            </AppText>
          </Card>
        ) : null}

        {prompts.map((prompt) => (
          <ProactivePromptCard
            key={`${prompt.kind}:${prompt.subjectKey}`}
            prompt={prompt}
            onAct={() => {
              if (prompt.route !== null) router.push(prompt.route as never);
            }}
            onDismiss={() =>
              dismiss.mutate({ kind: prompt.kind, subjectKey: prompt.subjectKey })
            }
          />
        ))}

        <Card style={{ gap: spacing.sm }}>
          <AppText variant="body" tone="secondary">
            {NURA_INTRO}
          </AppText>
          <Button
            label={recent.length === 0 ? START_CONVERSATION : NEW_CONVERSATION}
            disabled={!available || start.isPending}
            onPress={() =>
              start.mutate(undefined, {
                onSuccess: (conversation) => openConversation(conversation.id),
              })
            }
            accessibilityHint="Opens a new conversation with Nura"
          />
        </Card>

        {recent.length > 0 ? (
          <View style={{ gap: spacing.xs }}>
            <AppText variant="bodyStrong">{RECENT_HEADING}</AppText>
            <ListGroup>
              {recent.map((conversation) => (
                <ListRow
                  key={conversation.id}
                  label={conversation.title}
                  onPress={() => openConversation(conversation.id)}
                />
              ))}
            </ListGroup>
            <Button
              label={SEE_ALL_CONVERSATIONS}
              variant="ghost"
              onPress={() => router.push('/nura/history')}
            />
          </View>
        ) : null}

        {today.data ? <NuraStatusCard device={today.data.device} /> : null}

        <View style={{ gap: spacing.xs }}>
          <AppText variant="bodyStrong">{SETTINGS_HEADING}</AppText>
          <ListGroup>
            <ListRow
              label={PERSONALITY_LINK}
              onPress={() => router.push('/nura/personality')}
            />
            <ListRow label={VOICE_LINK} onPress={() => router.push('/nura/voice')} />
            <ListRow
              label={MEMORY_LINK}
              value={`${home.data?.memoryCount ?? 0}`}
              onPress={() => router.push('/nura/memory')}
            />
            <ListRow
              label={PROACTIVITY_LINK}
              onPress={() => router.push('/nura/proactivity')}
            />
            <ListRow
              label={INSTRUCTIONS_LINK}
              onPress={() => router.push('/nura/instructions')}
            />
          </ListGroup>
        </View>
      </View>
    </Screen>
  );
}
