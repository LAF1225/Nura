/**
 * Review before save (PRD 6, sections 30, 76 and 77).
 *
 * Both flows end here, and this screen is the reason the guided conversation is
 * safe to ship: whatever the extraction rules made of what somebody typed, they
 * see it in plain words and can change any of it before a single thing is stored.
 *
 * **The safety notice appears here, and does not block the save**
 * (PRD 6, section 77). Somebody who has recorded a symptom as worsening sees the
 * reviewed guidance above the Save button, not in a dialog in front of it: the
 * description is theirs to finish.
 *
 * **Nothing is saved until Save is pressed** (PRD 6, section 29). Up to this point
 * the whole thing has been a draft on the phone.
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { AppText, Button, Card, Screen } from '../../src/components';
import { SafetyNotice } from '../../src/features/symptoms/components/SafetyNotice';
import { StructuredSummary } from '../../src/features/symptoms/components/StructuredSummary';
import {
  REVIEW_HINT,
  REVIEW_TITLE,
  SAVE_OFFLINE_HINT,
} from '../../src/features/symptoms/copy';
import { hasContent, validateDraft } from '../../src/features/symptoms/draft';
import { useSymptomDraftStore } from '../../src/features/symptoms/draftStore';
import { useSaveSymptom } from '../../src/features/symptoms/hooks';
import { WORSENING_NOTICE } from '../../src/features/symptoms/safetyMessages';
import { apiErrorMessage } from '../../src/services/api';
import { spacing } from '../../src/theme/tokens';

export default function ReviewSymptomScreen() {
  const router = useRouter();

  const draft = useSymptomDraftStore((state) => state.draft);
  const episodeName = useSymptomDraftStore((state) => state.episodeName);
  const recurOf = useSymptomDraftStore((state) => state.recurOf);
  const clear = useSymptomDraftStore((state) => state.clear);
  const save = useSaveSymptom();

  if (draft === null) {
    return (
      <Screen>
        <Card>
          <AppText variant="body" tone="secondary">
            This symptom has been saved.
          </AppText>
        </Card>
      </Screen>
    );
  }

  const errors = validateDraft(draft);
  const ready = Object.keys(errors).length === 0 && hasContent(draft);

  // The user said it is getting worse, so the reviewed sentence is shown before
  // they save rather than after (PRD 6, sections 42 and 77). The server returns
  // the same text on the way back, and the detail screen shows it from there.
  const notice = draft.changeState === 'worsening' ? WORSENING_NOTICE : null;

  const onSave = async () => {
    try {
      const outcome = await save.mutateAsync({
        draft,
        displayName: draft.mainSymptom ?? episodeName ?? undefined,
        recurOf: recurOf ?? undefined,
      });
      clear();
      if (outcome.episodeId !== null) {
        router.replace({ pathname: '/symptoms/[id]', params: { id: outcome.episodeId } });
      } else {
        // Saved on this phone with nowhere to point at yet. The overview lists
        // it from the queue (PRD 6, section 59).
        router.replace('/symptoms');
      }
    } catch {
      // `save` holds the error; the card below shows it. Nothing is lost -- the
      // draft is still here and still editable.
    }
  };

  return (
    <Screen>
      <View style={{ gap: spacing.lg, paddingBottom: spacing.xl }}>
        <View style={{ gap: spacing.xxs }}>
          <AppText variant="title" accessibilityRole="header">
            {REVIEW_TITLE}
          </AppText>
          <AppText variant="body" tone="secondary">
            {REVIEW_HINT}
          </AppText>
        </View>

        <StructuredSummary draft={draft} heading={episodeName ?? undefined} />

        <SafetyNotice notice={notice} />

        {save.isError ? (
          <Card style={{ gap: spacing.xs }}>
            <AppText variant="bodyStrong">Nura couldn’t save this</AppText>
            <AppText variant="body" tone="secondary">
              {apiErrorMessage(save.error)}
            </AppText>
            <AppText variant="caption" tone="secondary">
              What you wrote is still here. You can change it and try again.
            </AppText>
          </Card>
        ) : null}

        <View style={{ gap: spacing.sm }}>
          <Button
            label="Save"
            onPress={() => void onSave()}
            disabled={!ready || save.isPending}
            accessibilityHint="Stores this symptom in your health record"
          />
          <Button
            label="Edit"
            variant="secondary"
            onPress={() => {
              if (draft.mode === 'guided_app') {
                router.push('/symptoms/talk');
              } else if (draft.episodeId !== undefined) {
                router.push({
                  pathname: '/symptoms/[id]/update',
                  params: { id: draft.episodeId },
                });
              } else {
                router.push('/symptoms/log');
              }
            }}
            accessibilityHint="Goes back so you can change what you wrote"
          />
        </View>

        {!ready ? (
          <AppText variant="caption" tone="secondary">
            {errors.mainSymptom ?? 'Add something before saving.'}
          </AppText>
        ) : (
          <AppText variant="caption" tone="secondary">
            {SAVE_OFFLINE_HINT}
          </AppText>
        )}
      </View>
    </Screen>
  );
}
