/**
 * Every summary generated for one appointment (PRD 7, sections 31 and 41).
 *
 * Versions, newest first, each with when it was made and what it covers.
 * Regenerating makes a new version and leaves the old ones alone, because
 * somebody may already have sent one -- so this screen never shows a version
 * being replaced (PRD 7, section 31).
 *
 * Deleting a version is explicit and says what it does not do: a report is a copy
 * of what was recorded, and removing the copy never removes the records
 * (section 65).
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
import {
  DELETE_REPORT_CONFIRM,
  pageCountSentence,
  PREPARE_ACTION,
  reportVersionLine,
  SHARE_ACTION,
} from '../../../src/features/appointments/copy';
import {
  useDeleteReport,
  useReports,
  useShareReport,
} from '../../../src/features/appointments/hooks';
import { apiErrorMessage } from '../../../src/services/api';
import { spacing } from '../../../src/theme/tokens';

export default function ReportHistoryScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);

  const appointmentId = id ?? '';
  const reports = useReports(id);
  const share = useShareReport(appointmentId);
  const remove = useDeleteReport(appointmentId);

  const rows = reports.data ?? [];

  return (
    <Screen
      onRefresh={() => void reports.refetch()}
      refreshing={reports.isRefetching && !reports.isLoading}
    >
      {reports.isLoading ? (
        <Card>
          <SkeletonCard lines={3} />
        </Card>
      ) : (
        <AsyncState
          status={reports.isError ? 'error' : 'success'}
          error={reports.error}
          isEmpty={rows.length === 0}
          emptyMessage="No summaries have been made for this appointment yet."
          onRetry={() => void reports.refetch()}
        >
          <View style={{ gap: spacing.md }}>
            {rows.map((report) => {
              const pages = pageCountSentence(report.pageCount);
              return (
                <Card key={report.id} style={{ gap: spacing.sm }}>
                  <View style={{ gap: spacing.xxs }}>
                    <AppText variant="bodyStrong">
                      {reportVersionLine(report.version, report.generatedLabel)}
                    </AppText>
                    <AppText variant="body" tone="secondary">
                      {report.periodLabel}
                    </AppText>
                    <AppText variant="caption" tone="secondary">
                      {[report.includeAppendix ? 'With appendix' : 'Summary only', pages]
                        .filter(Boolean)
                        .join(' · ')}
                    </AppText>
                  </View>

                  <Button
                    label="Preview"
                    variant="secondary"
                    onPress={() =>
                      router.push({
                        pathname: '/appointments/[id]/preview',
                        params: { id: appointmentId, reportId: report.id },
                      })
                    }
                    accessibilityHint="Shows what this version says"
                  />
                  <Button
                    label={SHARE_ACTION}
                    variant="secondary"
                    onPress={() => {
                      setError(null);
                      share.mutate(report, {
                        onError: (cause) => setError(apiErrorMessage(cause)),
                      });
                    }}
                    accessibilityHint="Downloads the PDF and opens your phone's share options"
                  />

                  {confirming === report.id ? (
                    <View style={{ gap: spacing.xs }}>
                      <AppText variant="body" tone="secondary">
                        {DELETE_REPORT_CONFIRM}
                      </AppText>
                      <Button
                        label="Delete this version"
                        onPress={() => {
                          setError(null);
                          remove.mutate(report.id, {
                            onSuccess: () => setConfirming(null),
                            onError: (cause) => setError(apiErrorMessage(cause)),
                          });
                        }}
                        accessibilityHint="Removes this version and its PDF"
                      />
                      <Button
                        label="Keep it"
                        variant="ghost"
                        onPress={() => setConfirming(null)}
                        accessibilityHint="Leaves this version alone"
                      />
                    </View>
                  ) : (
                    <Button
                      label="Delete version"
                      variant="ghost"
                      onPress={() => setConfirming(report.id)}
                      accessibilityHint="Asks whether to remove this version"
                    />
                  )}
                </Card>
              );
            })}
          </View>
        </AsyncState>
      )}

      {error ? (
        <AppText variant="body" tone="secondary" style={{ marginTop: spacing.md }}>
          {error}
        </AppText>
      ) : null}

      <View style={{ height: spacing.lg }} />

      <Button
        label={PREPARE_ACTION}
        onPress={() =>
          router.push({
            pathname: '/appointments/[id]/prepare',
            params: { id: appointmentId },
          })
        }
        accessibilityHint="Starts again from the review, to make a new version"
      />
    </Screen>
  );
}
