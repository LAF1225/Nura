/**
 * Export your data (PRD 13, sections 17 to 20 and 43).
 *
 * **It says what the file is before it offers to make one.** Section 18 asks
 * for an export that is explicitly requested, private, temporary and free of
 * secrets, and the only way somebody can hold Nura to that is if they are told
 * it beforehand. So the three sentences above the button are the server's
 * -- including the one saying no tokens or device secrets are in it, which the
 * client *requires* rather than reads optionally.
 *
 * **One at a time, and the refusal names the one that exists.** Section 53's
 * repeat-export case. Replacing a waiting archive would be worse than
 * refusing: somebody may be part way through downloading it.
 *
 * **Nothing here claims the file was saved anywhere.** Section 35 forbids
 * showing "Saved" or "Synced" without confirmation, and a download on a phone
 * is the operating system's business once the request succeeds. The row says
 * ready, the button says download, and what the phone does with the bytes is
 * reported by the phone.
 */
import { useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import {
  AppText,
  AsyncState,
  Button,
  Card,
  DegradedModeBanner,
  Screen,
  StatusChip,
} from '../../src/components';
import { useIsOffline } from '../../src/hooks/useNetworkStatus';
import {
  EXPORT_BUSY,
  EXPORT_BUTTON,
  EXPORT_DELETE,
  EXPORT_NONE,
  EXPORT_ONE_AT_A_TIME,
  EXPORT_WHAT_IS_INCLUDED,
  exportFiles,
  exportSize,
} from '../../src/features/privacy/copy';
import {
  useCreateExport,
  useDeleteExport,
  useExports,
} from '../../src/features/privacy/hooks';
import { apiErrorMessage } from '../../src/services/api/errors';
import { spacing } from '../../src/theme/tokens';

export default function ExportScreen() {
  const router = useRouter();
  const exports = useExports();
  const create = useCreateExport();
  const remove = useDeleteExport();
  const isOffline = useIsOffline();
  const [message, setMessage] = useState<string | null>(null);

  const data = exports.data;
  const waiting = data?.exports.find((entry) => entry.downloadable) ?? null;
  const past = (data?.exports ?? []).filter((entry) => entry.id !== waiting?.id);

  return (
    <Screen
      onRefresh={() => void exports.refetch()}
      refreshing={exports.isRefetching && !exports.isLoading}
    >
      {isOffline ? <DegradedModeBanner kind="offline" /> : null}

      <AsyncState
        status={exports.isError ? 'error' : data ? 'success' : 'loading'}
        error={exports.error}
        onRetry={() => void exports.refetch()}
      >
        {data ? (
          <View style={{ gap: spacing.lg }}>
            <Card style={{ gap: spacing.sm }}>
              <AppText variant="body">{data.note}</AppText>
              <AppText variant="body" tone="secondary">
                {data.privacyNote}
              </AppText>
              {/* Section 18's claim, sent with every list and required by the
                  parser. A screen that offered an export without it would be
                  dropping the sentence that makes the offer safe to accept. */}
              <AppText variant="body" tone="secondary">
                {data.secretsNote}
              </AppText>
            </Card>

            <Card style={{ gap: spacing.sm }}>
              <AppText variant="heading">{EXPORT_WHAT_IS_INCLUDED}</AppText>
              <AppText variant="body" tone="secondary">
                {data.sections.join(', ')}
              </AppText>
            </Card>

            {waiting === null ? (
              <View style={{ gap: spacing.sm }}>
                <Button
                  label={create.isPending ? EXPORT_BUSY : EXPORT_BUTTON}
                  onPress={() => {
                    setMessage(null);
                    create.mutate(undefined, {
                      onError: (error) => setMessage(apiErrorMessage(error)),
                    });
                  }}
                  disabled={create.isPending}
                  accessibilityHint="Creates a private copy of this profile's data"
                />
                {data.exports.length === 0 ? (
                  <AppText variant="caption" tone="secondary">
                    {EXPORT_NONE}
                  </AppText>
                ) : null}
              </View>
            ) : (
              <Card style={{ gap: spacing.sm }}>
                <View
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: spacing.sm,
                  }}
                >
                  <AppText variant="bodyStrong" style={{ flex: 1 }}>
                    {waiting.statusLabel}
                  </AppText>
                  <StatusChip label={exportFiles(waiting.fileCount)} tone="neutral" />
                </View>
                {exportSize(waiting.byteSize) !== null ? (
                  <AppText variant="caption" tone="secondary">
                    {exportSize(waiting.byteSize)}
                  </AppText>
                ) : null}
                <AppText variant="caption" tone="secondary">
                  {EXPORT_ONE_AT_A_TIME}
                </AppText>
                <Button
                  label={EXPORT_DELETE}
                  variant="secondary"
                  onPress={() => {
                    setMessage(null);
                    remove.mutate(waiting.id, {
                      onError: (error) => setMessage(apiErrorMessage(error)),
                    });
                  }}
                  disabled={remove.isPending}
                  accessibilityHint="Removes this export and its file"
                />
              </Card>
            )}

            {/* The ones that failed or expired. Section 20's states, said
                rather than hidden: an export that did not finish is something
                somebody should be told about.

                The one that is ready is deliberately *not* repeated here. It
                already has its own card above with the download and delete
                controls, and a second row saying the same words is a row a
                screen reader reads out twice without saying why. */}
            {past.length > 0 ? (
              <View style={{ gap: spacing.sm }}>
                <AppText variant="heading">Earlier exports</AppText>
                <Card style={{ gap: spacing.md }}>
                  {past.map((entry) => (
                    <View key={entry.id} style={{ gap: spacing.xxs }}>
                      <AppText variant="bodyStrong">{entry.statusLabel}</AppText>
                      <AppText variant="caption" tone="secondary">
                        {entry.requestedAt}
                      </AppText>
                      {entry.failureReason !== null ? (
                        <AppText variant="caption" tone="secondary">
                          {entry.failureReason}
                        </AppText>
                      ) : null}
                    </View>
                  ))}
                </Card>
              </View>
            ) : null}

            {message !== null ? (
              <AppText variant="body" tone="secondary" accessibilityLiveRegion="polite">
                {message}
              </AppText>
            ) : null}

            <Button
              label="Back to Privacy & Security"
              variant="secondary"
              onPress={() => router.back()}
              accessibilityHint="Returns to the privacy screen"
            />
          </View>
        ) : null}
      </AsyncState>
    </Screen>
  );
}
