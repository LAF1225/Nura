/**
 * Choosing what goes in the summary (PRD 7, sections 25, 27 and 28).
 *
 * The switch list from PRD 7 section 25, plus the appendix toggle from section 27.
 * Symptoms and medications were chosen on the review screen, where their counts
 * are visible; this screen is for the sections, the notes and the appendix.
 *
 * **Only what is ticked appears.** That is the whole contract of the screen, and
 * the backend honours it literally -- an unticked section is absent from the
 * report rather than present and empty (PRD 7, section 25).
 *
 * **Photos are not offered.** PRD 7 section 28 permits deferring them, and they
 * are deferred: a symptom photo is the one thing in Nura that never leaves the
 * backend without an authenticated per-byte check (PRD 6, section 63), and
 * embedding one in a shareable PDF would remove that control. Their existence is
 * reported so nobody thinks they were lost.
 */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import {
  AppText,
  Button,
  Card,
  Screen,
  SkeletonCard,
  TextField,
  ToggleRow,
} from '../../../src/components';
import { OfflineBanner } from '../../../src/components/today';
import { PreparationProgress } from '../../../src/features/appointments/components/PreparationProgress';
import { ReportSectionToggle } from '../../../src/features/appointments/components/SelectionCards';
import {
  APPENDIX_HINT,
  APPENDIX_LABEL,
  OFFLINE_REPORT,
  SECTION_LABELS,
  SELECTION_INTRO,
} from '../../../src/features/appointments/copy';
import {
  useGenerateReport,
  usePreparation,
} from '../../../src/features/appointments/hooks';
import { useReportSelectionStore } from '../../../src/features/appointments/selectionStore';
import type { ReportSectionKey } from '../../../src/features/appointments/types';
import { useIsOffline } from '../../../src/hooks/useNetworkStatus';
import { apiErrorMessage } from '../../../src/services/api';
import { spacing } from '../../../src/theme/tokens';

/** The order the switches are shown in, following the report's own order. */
const SECTION_ORDER: readonly ReportSectionKey[] = [
  'questions',
  'medications',
  'adherence',
  'daily_checkins',
  'conditions',
  'allergies',
  'procedures',
  'blood_type',
  'medical_notes',
];

export default function SelectReportContentScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const isOffline = useIsOffline();
  const [error, setError] = useState<string | null>(null);

  const appointmentId = id ?? '';
  const preset = useReportSelectionStore((state) => state.preset);
  const selection = useReportSelectionStore((state) => state.selection);
  const toggleSection = useReportSelectionStore((state) => state.toggleSection);
  const toggleMedicalNote = useReportSelectionStore((state) => state.toggleMedicalNote);
  const setAppendix = useReportSelectionStore((state) => state.setAppendix);
  const setSkipReasonNotes = useReportSelectionStore((state) => state.setSkipReasonNotes);
  const setFocus = useReportSelectionStore((state) => state.setFocus);

  const requested = preset === 'custom' ? '30_days' : preset;
  const preparation = usePreparation(id, { preset: requested });
  const generate = useGenerateReport(appointmentId);
  const data = preparation.data;

  const photoCount = (data?.symptoms ?? [])
    .filter((review) => selection.symptomEpisodeIds.includes(review.episodeId))
    .reduce((total, review) => total + review.photoCount, 0);

  const onGenerate = () => {
    setError(null);
    if (isOffline) {
      // Said plainly rather than attempted. PRD 7 section 53: do not pretend
      // generation succeeded while offline.
      setError(OFFLINE_REPORT);
      return;
    }
    // Read at press time rather than from the render closure: a press that
    // arrives before React has committed the last toggle would otherwise
    // generate from the selection as it was a moment ago.
    const current = useReportSelectionStore.getState();
    generate.mutate(
      {
        selection: current.selection,
        preset: current.preset,
        periodStart: current.customStart,
        periodEnd: current.customEnd,
      },
      {
        onSuccess: (report) =>
          router.push({
            pathname: '/appointments/[id]/preview',
            params: { id: appointmentId, reportId: report.id },
          }),
        onError: (cause) => setError(apiErrorMessage(cause)),
      }
    );
  };

  return (
    <Screen>
      <PreparationProgress current="choose" />

      {isOffline ? (
        <View style={{ marginTop: spacing.md }}>
          <OfflineBanner />
        </View>
      ) : null}

      <AppText variant="body" tone="secondary" style={{ marginTop: spacing.md }}>
        {SELECTION_INTRO}
      </AppText>

      <View style={{ height: spacing.lg }} />

      <Card style={{ gap: spacing.sm }}>
        <AppText variant="heading" accessibilityRole="header">
          Reason for this visit
        </AppText>
        <TextField
          label="What is the visit about?"
          hint="Optional. Written at the top of the summary, in your words."
          value={selection.focus ?? ''}
          onChangeText={setFocus}
          multiline
          numberOfLines={2}
          maxLength={200}
        />
      </Card>

      <View style={{ height: spacing.lg }} />

      {preparation.isLoading ? (
        <Card>
          <SkeletonCard lines={5} />
        </Card>
      ) : (
        <View style={{ gap: spacing.xs }}>
          {SECTION_ORDER.map((key) => (
            <ReportSectionToggle
              key={key}
              label={SECTION_LABELS[key] ?? key}
              selected={selection.include[key] === true}
              onToggle={() => toggleSection(key)}
            />
          ))}
        </View>
      )}

      {selection.include.medical_notes && (data?.medicalNotes.length ?? 0) > 0 ? (
        <View style={{ gap: spacing.xs, marginTop: spacing.md }}>
          <AppText variant="caption" tone="secondary">
            Tick the notes you want attached
          </AppText>
          {(data?.medicalNotes ?? []).map((note) => (
            <ReportSectionToggle
              key={note.noteId}
              label={note.title}
              description={note.body}
              selected={selection.medicalNoteIds.includes(note.noteId)}
              onToggle={() => toggleMedicalNote(note.noteId)}
            />
          ))}
        </View>
      ) : null}

      <View style={{ height: spacing.lg }} />

      <Card style={{ gap: spacing.sm }}>
        <ToggleRow
          label={APPENDIX_LABEL}
          description={APPENDIX_HINT}
          value={selection.includeAppendix}
          onChange={setAppendix}
        />
        {(data?.adherence?.skipNotes.length ?? 0) > 0 ? (
          <ToggleRow
            label="Include what you wrote about skipped doses"
            description="Your own words. Left out unless you ask for them."
            value={selection.includeSkipReasonNotes}
            onChange={setSkipReasonNotes}
          />
        ) : null}
      </Card>

      {photoCount > 0 ? (
        <AppText variant="caption" tone="secondary" style={{ marginTop: spacing.md }}>
          {photoCount === 1
            ? 'You have 1 symptom photo. Photos stay in Nura and are not put in the PDF.'
            : `You have ${photoCount} symptom photos. Photos stay in Nura and are not put in the PDF.`}
        </AppText>
      ) : null}

      <View style={{ height: spacing.lg }} />

      {error ? (
        <AppText variant="body" tone="secondary" style={{ marginBottom: spacing.md }}>
          {error}
        </AppText>
      ) : null}

      <Button
        label={generate.isPending ? 'Making the summary…' : 'Make the summary'}
        onPress={onGenerate}
        disabled={generate.isPending}
        accessibilityHint="Builds a one-page summary from what you ticked"
      />
    </Screen>
  );
}
