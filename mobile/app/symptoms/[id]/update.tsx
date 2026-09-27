/**
 * Adding a follow-up to an existing symptom (PRD 6, sections 23 and 47).
 *
 * The whole point of this screen is what it does *not* ask. PRD 6 section 47
 * requires a later update without re-entering the original description, so there
 * is no name, no onset, no location and no character here -- only what can have
 * changed: how bad it is, which way it is going, anything new alongside it, a
 * note, and a photo.
 *
 * The same shared draft and the same review screen as everything else, so a
 * follow-up ends up as an ordinary entry on the episode rather than a second kind
 * of record (PRD 6, section 4).
 */
import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback } from 'react';
import { View } from 'react-native';

import {
  AppText,
  Button,
  Card,
  Screen,
  SkeletonCard,
  TextField,
} from '../../../src/components';
import { ChangeStateSelector } from '../../../src/features/symptoms/components/ChangeStateSelector';
import { PhotoAttachmentPicker } from '../../../src/features/symptoms/components/PhotoAttachmentPicker';
import { SeverityInput } from '../../../src/features/symptoms/components/SeverityInput';
import {
  episodeTitle,
  FIELD_HINTS,
  FIELD_LABELS,
  onsetSentence,
  OPTIONAL,
} from '../../../src/features/symptoms/copy';
import {
  formatItems,
  hasContent,
  parseItems,
} from '../../../src/features/symptoms/draft';
import { useSymptomDraftStore } from '../../../src/features/symptoms/draftStore';
import { useSymptomEpisode } from '../../../src/features/symptoms/hooks';
import { useSymptomPicker } from '../../../src/features/symptoms/useSymptomPicker';
import { spacing } from '../../../src/theme/tokens';

export default function UpdateSymptomScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const episodeId = typeof id === 'string' ? id : '';

  const episode = useSymptomEpisode(episodeId);
  const draft = useSymptomDraftStore((state) => state.draft);
  const start = useSymptomDraftStore((state) => state.start);
  const patch = useSymptomDraftStore((state) => state.patch);
  const removePhoto = useSymptomDraftStore((state) => state.removePhoto);
  const setEpisodeName = useSymptomDraftStore((state) => state.setEpisodeName);
  const picker = useSymptomPicker();

  const name = episode.data?.name;

  // A draft for a different symptom -- or none at all -- is replaced. One for
  // this symptom is picked up where it was left (PRD 6, section 59).
  useFocusEffect(
    useCallback(() => {
      if (draft === null || draft.episodeId !== episodeId) {
        start('manual_app', { episodeId, episodeName: name });
      } else if (name !== undefined) {
        // The draft is started as soon as this screen is focused, which can be
        // before the episode has loaded. The name arrives second, and the review
        // screen needs it to head the summary with the symptom.
        setEpisodeName(name);
      }
    }, [draft, episodeId, name, setEpisodeName, start])
  );

  if (episode.isLoading || draft === null) {
    return (
      <Screen>
        <Card>
          <SkeletonCard lines={3} label="Loading this symptom" />
        </Card>
      </Screen>
    );
  }

  const data = episode.data;

  return (
    <Screen>
      <View style={{ gap: spacing.lg, paddingBottom: spacing.xl }}>
        {data ? (
          <View style={{ gap: spacing.xxs }}>
            <AppText variant="title" accessibilityRole="header">
              {episodeTitle(data.name, data.latestEntry?.severity)}
            </AppText>
            <AppText variant="body" tone="secondary">
              {onsetSentence(data) ?? 'Add how it is doing now.'}
            </AppText>
            {/* Nothing below re-asks for any of this: the description above is
                the one already recorded (PRD 6, section 47). */}
          </View>
        ) : null}

        <SeverityInput
          label={`${FIELD_LABELS.severity} ${OPTIONAL}`}
          value={draft.severity}
          onChange={(severity) => patch({ severity })}
          onClear={() => patch({ severity: undefined })}
        />

        <ChangeStateSelector
          label={`${FIELD_LABELS.changeState} ${OPTIONAL}`}
          value={draft.changeState}
          onChange={(changeState) => patch({ changeState })}
        />

        <TextField
          key={`associated-${draft.clientEntryId}`}
          label={`${FIELD_LABELS.associatedSymptoms} ${OPTIONAL}`}
          hint={FIELD_HINTS.associatedSymptoms}
          defaultValue={formatItems(draft.associatedSymptoms)}
          onChangeText={(value) => patch({ associatedSymptoms: parseItems(value) })}
          maxLength={400}
        />

        <TextField
          label={`${FIELD_LABELS.note} ${OPTIONAL}`}
          hint={FIELD_HINTS.note}
          value={draft.note ?? ''}
          onChangeText={(value) => patch({ note: value })}
          multiline
          numberOfLines={4}
          maxLength={2000}
        />

        <PhotoAttachmentPicker
          photos={draft.photos ?? []}
          onTakePhoto={picker.takePhoto}
          onPickPhoto={picker.pickPhoto}
          onRemove={removePhoto}
          message={picker.message}
          busy={picker.busy}
        />

        <View style={{ gap: spacing.sm }}>
          <Button
            label="Review and save"
            onPress={() => router.push('/symptoms/review')}
            disabled={!hasContent(draft)}
            accessibilityHint="Shows this update before it is saved"
          />
          <Button
            label="Talk to Nura instead"
            variant="secondary"
            onPress={() => {
              start('guided_app', { episodeId, episodeName: name });
              router.push('/symptoms/talk');
            }}
            accessibilityHint="Answers a few short questions instead of filling this in"
          />
        </View>
      </View>
    </Screen>
  );
}
