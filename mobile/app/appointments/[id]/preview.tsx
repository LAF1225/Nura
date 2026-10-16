/**
 * The report preview, and the export (PRD 7, sections 32-34).
 *
 * The preview renders the report's **own snapshot** -- the same frozen text the
 * PDF is made from -- so what somebody approves here and what they export cannot
 * disagree (PRD 7, sections 30 and 32).
 *
 * Everything section 32 asks for is on this screen: preview, go back, change the
 * selections, turn the appendix on or off, regenerate. Nothing exports by itself:
 * the share sheet opens only when the button is pressed (section 13).
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
} from '../../../src/components';
import { PreparationProgress } from '../../../src/features/appointments/components/PreparationProgress';
import { ReportPreviewCard } from '../../../src/features/appointments/components/ReportPreviewCard';
import {
  pageCountSentence,
  PREVIEW_INTRO,
  REGENERATE_ACTION,
  REGENERATE_HINT,
  reportVersionLine,
  SHARE_ACTION,
} from '../../../src/features/appointments/copy';
import { useReport, useShareReport } from '../../../src/features/appointments/hooks';
import { apiErrorMessage } from '../../../src/services/api';
import { spacing } from '../../../src/theme/tokens';

export default function ReportPreviewScreen() {
  const { id, reportId } = useLocalSearchParams<{ id: string; reportId: string }>();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  const appointmentId = id ?? '';
  const report = useReport(id, reportId);
  const share = useShareReport(appointmentId);

  const record = report.data;

  if (report.isLoading || record === undefined) {
    return (
      <Screen>
        <Card>
          <SkeletonCard lines={6} />
        </Card>
      </Screen>
    );
  }

  if (report.isError || record.snapshot === undefined) {
    return (
      <Screen>
        <AsyncState
          status="error"
          error={report.error}
          onRetry={() => void report.refetch()}
        >
          {null}
        </AsyncState>
      </Screen>
    );
  }

  const onShare = () => {
    setError(null);
    setSaved(null);
    share.mutate(record, {
      onSuccess: (outcome) => {
        if (!outcome.shared) {
          // No share sheet on this platform. The file is real, so this is
          // reported as what happened rather than as a failure.
          setSaved(`Saved to this phone as ${outcome.fileName}.`);
        }
      },
      onError: (cause) => setError(apiErrorMessage(cause)),
    });
  };

  const pages = pageCountSentence(record.pageCount);

  return (
    <Screen>
      <PreparationProgress current="preview" />

      <AppText variant="body" tone="secondary" style={{ marginTop: spacing.md }}>
        {PREVIEW_INTRO}
      </AppText>

      <View style={{ height: spacing.md }} />

      <AppText variant="caption" tone="secondary">
        {reportVersionLine(record.version, record.generatedLabel)}
        {pages ? ` · ${pages}` : ''}
      </AppText>

      <View style={{ height: spacing.md }} />

      <ReportPreviewCard snapshot={record.snapshot} />

      <View style={{ height: spacing.lg }} />

      {error ? (
        <AppText variant="body" tone="secondary" style={{ marginBottom: spacing.md }}>
          {error}
        </AppText>
      ) : null}
      {saved ? (
        <AppText variant="body" tone="secondary" style={{ marginBottom: spacing.md }}>
          {saved}
        </AppText>
      ) : null}

      <View style={{ gap: spacing.sm }}>
        <Button
          label={share.isPending ? 'Preparing the PDF…' : SHARE_ACTION}
          onPress={onShare}
          disabled={share.isPending}
          accessibilityHint="Downloads the PDF and opens your phone's share options"
        />
        <Button
          label="Change what is included"
          variant="secondary"
          onPress={() =>
            router.push({
              pathname: '/appointments/[id]/select',
              params: { id: appointmentId },
            })
          }
          accessibilityHint="Goes back to the sections that appear in the summary"
        />
        <Button
          label={REGENERATE_ACTION}
          variant="secondary"
          onPress={() =>
            router.push({
              pathname: '/appointments/[id]/select',
              params: { id: appointmentId },
            })
          }
          accessibilityHint={REGENERATE_HINT}
        />
        <AppText variant="caption" tone="secondary">
          {REGENERATE_HINT}
        </AppText>
        <Button
          label="All summaries"
          variant="ghost"
          onPress={() =>
            router.push({
              pathname: '/appointments/[id]/reports',
              params: { id: appointmentId },
            })
          }
          accessibilityHint="Shows every version generated for this appointment"
        />
      </View>
    </Screen>
  );
}
