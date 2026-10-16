/**
 * Prepare for Appointment, step one: the review (PRD 7, sections 12-21).
 *
 * Everything the person has recorded over the chosen period, shown so they can
 * see it before deciding what to bring. The review *is* the selection: each
 * symptom and medication is tickable here, and the next screen is only for the
 * sections and the appendix.
 *
 * Three things this screen must not do, and does not:
 *
 * **It does not choose.** No symptom is highlighted, ordered by severity or
 * marked significant. PRD 7 section 15 puts that decision with the user, and an
 * ordering by anything but time would make it for them.
 *
 * **It does not interpret.** Counts, the user's own answers, and the plain
 * figures from the medication history. No pattern, no cause, no conclusion
 * (sections 3, 16, 18 and 20).
 *
 * **It does not grade adherence.** "13 of 14 scheduled doses marked taken" and
 * nothing about whether that is good (section 18).
 */
import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { View } from 'react-native';

import {
  AppText,
  AsyncState,
  Button,
  Card,
  Screen,
  SkeletonCard,
} from '../../../src/components';
import { PreparationProgress } from '../../../src/features/appointments/components/PreparationProgress';
import {
  MedicationSelectionCard,
  SymptomSelectionCard,
} from '../../../src/features/appointments/components/SelectionCards';
import {
  adherenceSentence,
  checkinSentence,
  NO_HEALTH_DATA,
  PERIOD_LABELS,
  PERIOD_ORDER,
  PREPARE_INTRO,
  skippedSentence,
} from '../../../src/features/appointments/copy';
import { usePreparation } from '../../../src/features/appointments/hooks';
import {
  isMedicationSelected,
  useReportSelectionStore,
} from '../../../src/features/appointments/selectionStore';
import type { ReportPeriodPreset } from '../../../src/features/appointments/types';
import { spacing } from '../../../src/theme/tokens';

export default function PrepareAppointmentScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [showNotes, setShowNotes] = useState(false);

  const preset = useReportSelectionStore((state) => state.preset);
  const selection = useReportSelectionStore((state) => state.selection);
  const start = useReportSelectionStore((state) => state.start);
  const setPreset = useReportSelectionStore((state) => state.setPreset);
  const toggleSymptom = useReportSelectionStore((state) => state.toggleSymptom);
  const toggleSymptomNote = useReportSelectionStore((state) => state.toggleSymptomNote);
  const toggleMedication = useReportSelectionStore((state) => state.toggleMedication);
  const toggleCheckinNote = useReportSelectionStore((state) => state.toggleCheckinNote);

  // `custom` needs two dates, which this screen does not collect; the period
  // chooser offers the four presets and leaves a custom range to a later PRD.
  const requested: ReportPeriodPreset = preset === 'custom' ? '30_days' : preset;
  const preparation = usePreparation(id, { preset: requested });
  const data = preparation.data;

  // On focus rather than on mount, and only once the review has loaded, so the
  // default selection is the server's own -- every section, every symptom.
  useFocusEffect(
    useCallback(() => {
      if (id !== undefined && data !== undefined) {
        start(id, data.defaultSelection);
      }
    }, [id, data, start])
  );

  if (preparation.isLoading || data === undefined) {
    return (
      <Screen>
        <Card>
          <SkeletonCard lines={5} />
        </Card>
      </Screen>
    );
  }

  if (preparation.isError) {
    return (
      <Screen>
        <AsyncState
          status="error"
          error={preparation.error}
          onRetry={() => void preparation.refetch()}
        >
          {null}
        </AsyncState>
      </Screen>
    );
  }

  const medicationIds = data.medications.map((review) => review.medicationId);

  return (
    <Screen
      onRefresh={() => void preparation.refetch()}
      refreshing={preparation.isRefetching && !preparation.isLoading}
    >
      <PreparationProgress current="review" />

      <AppText variant="body" tone="secondary" style={{ marginTop: spacing.sm }}>
        {PREPARE_INTRO}
      </AppText>

      <View style={{ height: spacing.lg }} />

      {/* The period, and why it is what it is (PRD 7, section 14). */}
      <Card style={{ gap: spacing.sm }}>
        <AppText variant="heading">Period</AppText>
        <AppText variant="bodyStrong">{data.period.label}</AppText>
        {data.period.sinceLabel ? (
          <AppText variant="body" tone="secondary">
            {data.period.sinceLabel}
          </AppText>
        ) : null}
        {data.period.note ? (
          <AppText variant="body" tone="secondary">
            {data.period.note}
          </AppText>
        ) : null}
        <View accessibilityRole="radiogroup" style={{ gap: spacing.xs }}>
          {PERIOD_ORDER.filter((option) => option !== 'custom').map((option) => (
            <Button
              key={option}
              label={PERIOD_LABELS[option]}
              variant={option === requested ? 'primary' : 'secondary'}
              onPress={() => setPreset(option)}
              accessibilityHint={`Summarises ${PERIOD_LABELS[option].toLowerCase()}`}
            />
          ))}
        </View>
      </Card>

      <View style={{ height: spacing.lg }} />

      {!data.hasHealthData ? (
        <Card style={{ marginBottom: spacing.lg }}>
          <AppText variant="body" tone="secondary">
            {NO_HEALTH_DATA}
          </AppText>
        </Card>
      ) : null}

      <View style={{ gap: spacing.lg }}>
        {data.symptoms.length > 0 ? (
          <View style={{ gap: spacing.xs }}>
            <AppText variant="heading" accessibilityRole="header">
              Recent symptoms
            </AppText>
            <AppText variant="caption" tone="secondary">
              Tick the ones you want in the summary. Nura does not decide which matter.
            </AppText>
            {data.symptoms.map((review) => (
              <SymptomSelectionCard
                key={review.episodeId}
                review={review}
                selected={selection.symptomEpisodeIds.includes(review.episodeId)}
                onToggle={() => toggleSymptom(review.episodeId)}
                selectedNoteIds={selection.symptomNoteEntryIds}
                onToggleNote={toggleSymptomNote}
              />
            ))}
          </View>
        ) : null}

        {data.medications.length > 0 ? (
          <View style={{ gap: spacing.xs }}>
            <AppText variant="heading" accessibilityRole="header">
              Current medications
            </AppText>
            {data.medications.map((review) => (
              <MedicationSelectionCard
                key={review.medicationId}
                review={review}
                selected={isMedicationSelected(selection, review.medicationId)}
                onToggle={() => toggleMedication(review.medicationId, medicationIds)}
              />
            ))}
          </View>
        ) : null}

        {data.adherence !== null ? (
          <Card style={{ gap: spacing.xxs }}>
            <AppText variant="heading">Medication doses</AppText>
            <AppText variant="body" tone="secondary">
              {adherenceSentence(data.adherence)}
            </AppText>
            {skippedSentence(data.adherence) ? (
              <AppText variant="body" tone="secondary">
                {skippedSentence(data.adherence)}
              </AppText>
            ) : null}
          </Card>
        ) : null}

        {data.dailyCheckins !== null ? (
          <Card style={{ gap: spacing.sm }}>
            <AppText variant="heading">Daily check-ins</AppText>
            <AppText variant="body" tone="secondary">
              {checkinSentence(data.dailyCheckins)}
            </AppText>
            {data.dailyCheckins.notes.length > 0 ? (
              <View style={{ gap: spacing.xs }}>
                <Button
                  label={showNotes ? 'Hide notes' : 'Choose notes to include'}
                  variant="secondary"
                  onPress={() => setShowNotes(!showNotes)}
                  accessibilityHint="Shows the notes you wrote with your check-ins"
                />
                {showNotes
                  ? data.dailyCheckins.notes.map((note) => (
                      <Button
                        key={note.checkinDate}
                        label={`${note.checkinDate}: ${note.note}`}
                        variant={
                          selection.checkinNoteDates.includes(note.checkinDate)
                            ? 'primary'
                            : 'secondary'
                        }
                        onPress={() => toggleCheckinNote(note.checkinDate)}
                        accessibilityHint="Includes or removes this note"
                      />
                    ))
                  : null}
              </View>
            ) : null}
          </Card>
        ) : null}

        {data.baseline !== null ? (
          <Card style={{ gap: spacing.xxs }}>
            <AppText variant="heading">Health background</AppText>
            <AppText variant="body" tone="secondary">
              {`${data.baseline.conditions.length} conditions · ${data.baseline.allergies.length} allergies`}
            </AppText>
            {data.baseline.bloodType ? (
              <AppText variant="body" tone="secondary">
                {`Blood type: ${data.baseline.bloodType}`}
              </AppText>
            ) : null}
            <AppText variant="caption" tone="secondary">
              You choose which of these go in on the next step.
            </AppText>
          </Card>
        ) : null}
      </View>

      <View style={{ height: spacing.lg }} />

      <Button
        label="Next: questions"
        onPress={() =>
          router.push({
            pathname: '/appointments/[id]/questions',
            params: { id: id ?? '' },
          })
        }
        accessibilityHint="Goes to the questions you want to ask"
      />
    </Screen>
  );
}
