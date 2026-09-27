/**
 * Logging a symptom by hand (PRD 6, sections 4, 11, 12 and 25).
 *
 * PRD 6 section 25's flow as one scrollable form rather than a wizard: the
 * questions are short, and making somebody tap Next eight times to describe a
 * headache is worse than letting them see the whole thing and fill in the parts
 * they can answer.
 *
 * **Only the first field is required.** Everything else says (optional) and means
 * it -- a useful record has to be savable without a severity, a character or a
 * location (PRD 6, sections 11 and 91).
 *
 * Every field writes straight into the shared draft store rather than into local
 * component state. That is what lets the review screen, the guided conversation
 * and this form all edit one thing, and what lets the draft survive the app being
 * closed (PRD 6, sections 29, 59 and 72).
 */
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback } from 'react';
import { View } from 'react-native';

import {
  AppText,
  Button,
  Card,
  Screen,
  SkeletonCard,
  TextField,
} from '../../src/components';
import { ChangeStateSelector } from '../../src/features/symptoms/components/ChangeStateSelector';
import { PhotoAttachmentPicker } from '../../src/features/symptoms/components/PhotoAttachmentPicker';
import { SeverityInput } from '../../src/features/symptoms/components/SeverityInput';
import { FIELD_HINTS, FIELD_LABELS, OPTIONAL } from '../../src/features/symptoms/copy';
import {
  formatItems,
  hasContent,
  parseItems,
  validateDraft,
} from '../../src/features/symptoms/draft';
import { useSymptomDraftStore } from '../../src/features/symptoms/draftStore';
import { useSymptomPicker } from '../../src/features/symptoms/useSymptomPicker';
import { NOT_ADVICE } from '../../src/features/symptoms/safetyMessages';
import { spacing } from '../../src/theme/tokens';

export default function LogSymptomScreen() {
  const router = useRouter();

  const draft = useSymptomDraftStore((state) => state.draft);
  const start = useSymptomDraftStore((state) => state.start);
  const patch = useSymptomDraftStore((state) => state.patch);
  const removePhoto = useSymptomDraftStore((state) => state.removePhoto);
  const picker = useSymptomPicker();

  // Opened directly, or after the app was relaunched with nothing in progress.
  // On focus rather than on mount, so a save that clears the draft cannot make
  // this screen create an empty one behind the user's back.
  useFocusEffect(
    useCallback(() => {
      if (draft === null) start('manual_app');
    }, [draft, start])
  );

  // One render before the effect above creates a draft.
  if (draft === null) {
    return (
      <Screen>
        <Card>
          <SkeletonCard lines={2} label="Getting ready" />
        </Card>
      </Screen>
    );
  }

  const errors = validateDraft(draft);
  const isFollowUp = draft.episodeId !== undefined;
  // An untouched form is not a form with a mistake in it. The missing-name
  // message appears once the person has started filling things in, and until
  // then the field's hint says what belongs there and Save is simply disabled.
  const started = hasContent(draft);

  return (
    <Screen>
      <View style={{ gap: spacing.lg, paddingBottom: spacing.xl }}>
        {!isFollowUp ? (
          <TextField
            label={FIELD_LABELS.mainSymptom}
            hint={FIELD_HINTS.mainSymptom}
            value={draft.mainSymptom ?? ''}
            onChangeText={(value) => patch({ mainSymptom: value })}
            error={started ? errors.mainSymptom : undefined}
            maxLength={120}
            autoFocus
          />
        ) : null}

        {!isFollowUp ? (
          <TextField
            label={`${FIELD_LABELS.onset} ${OPTIONAL}`}
            hint={FIELD_HINTS.onset}
            value={draft.onset ?? ''}
            onChangeText={(value) => patch({ onset: value })}
            maxLength={200}
          />
        ) : null}

        {!isFollowUp ? (
          <TextField
            label={`${FIELD_LABELS.site} ${OPTIONAL}`}
            hint={FIELD_HINTS.site}
            value={draft.site ?? ''}
            onChangeText={(value) => patch({ site: value })}
            maxLength={200}
          />
        ) : null}

        <SeverityInput
          label={`${FIELD_LABELS.severity} ${OPTIONAL}`}
          value={draft.severity}
          onChange={(severity) => patch({ severity })}
          onClear={() => patch({ severity: undefined })}
        />

        {!isFollowUp ? (
          <TextField
            label={`${FIELD_LABELS.character} ${OPTIONAL}`}
            hint={FIELD_HINTS.character}
            value={draft.character ?? ''}
            onChangeText={(value) => patch({ character: value })}
            maxLength={200}
          />
        ) : null}

        {/* Radiation is offered here even where the guided flow would skip it:
            a form the user is reading can carry a question that does not apply,
            as long as it is obviously optional (PRD 6, section 12). */}
        {!isFollowUp ? (
          <TextField
            label={`${FIELD_LABELS.radiation} ${OPTIONAL}`}
            hint={FIELD_HINTS.radiation}
            value={draft.radiation ?? ''}
            onChangeText={(value) => patch({ radiation: value })}
            maxLength={200}
          />
        ) : null}

        {/* The list fields are uncontrolled on purpose. Re-deriving the text
            from the parsed list on every keystroke would swallow the comma the
            moment it was typed, so the field keeps what was typed and the draft
            keeps what it means. */}
        <TextField
          key={`associated-${draft.clientEntryId}`}
          label={`${FIELD_LABELS.associatedSymptoms} ${OPTIONAL}`}
          hint={FIELD_HINTS.associatedSymptoms}
          defaultValue={formatItems(draft.associatedSymptoms)}
          onChangeText={(value) => patch({ associatedSymptoms: parseItems(value) })}
          maxLength={400}
        />

        {!isFollowUp ? (
          <TextField
            key={`timing-${draft.clientEntryId}`}
            label={`${FIELD_LABELS.timing} ${OPTIONAL}`}
            hint={FIELD_HINTS.timing}
            value={draft.timing ?? ''}
            onChangeText={(value) => patch({ timing: value })}
            maxLength={200}
          />
        ) : null}

        {!isFollowUp ? (
          <>
            <TextField
              key={`worse-${draft.clientEntryId}`}
              label={`${FIELD_LABELS.exacerbatingFactors} ${OPTIONAL}`}
              defaultValue={formatItems(draft.exacerbatingFactors)}
              onChangeText={(value) => patch({ exacerbatingFactors: parseItems(value) })}
              maxLength={400}
            />
            <TextField
              key={`better-${draft.clientEntryId}`}
              label={`${FIELD_LABELS.relievingFactors} ${OPTIONAL}`}
              defaultValue={formatItems(draft.relievingFactors)}
              onChangeText={(value) => patch({ relievingFactors: parseItems(value) })}
              maxLength={400}
            />
          </>
        ) : null}

        <ChangeStateSelector
          label={`${isFollowUp ? FIELD_LABELS.changeState : 'Has it changed since it started?'} ${OPTIONAL}`}
          value={draft.changeState}
          onChange={(changeState) => patch({ changeState })}
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

        <Card style={{ gap: spacing.sm }}>
          <Button
            label="Review and save"
            onPress={() => router.push('/symptoms/review')}
            disabled={Object.keys(errors).length > 0}
            accessibilityHint="Shows everything you have written before it is saved"
          />
          <AppText variant="caption" tone="secondary">
            {NOT_ADVICE}
          </AppText>
        </Card>
      </View>
    </Screen>
  );
}
