/**
 * Delete your data (PRD 13, sections 21, 22 and 44).
 *
 * **Three deliberate steps, because section 21 forbids a one-tap destructive
 * action.** Reading what will go, typing a phrase exactly, then confirming.
 * The first step is a request that changes nothing and returns counts from the
 * database, so the warning somebody reads is the scope the service actually
 * has rather than a paragraph written once and left behind.
 *
 * **It says what Nura cannot do.** Section 44 asks for re-authentication "if
 * already supported", and it is not: Nura verifies a token from the identity
 * provider and never receives a password, so there is nothing here to check
 * one against. The limitation is stated on this screen rather than only in a
 * document, because this is the moment somebody would want to know it --
 * anybody holding an unlocked phone with a live session can complete this, and
 * the phrase is what stops it being a mis-tap rather than what stops it being
 * an intruder.
 *
 * **The phrase is echoed, never composed.** It arrives from the first request
 * and is compared exactly, trimmed of nothing. A phrase lower-cased into
 * matching is a phrase that could arrive by accident.
 *
 * The validation lives in `validation.ts` as a pure function for the reason
 * PRD 12 found the hard way: under React 19 + RNTL 14 a component's own
 * `useState` does not flush from `fireEvent`, so a rule tested through this
 * screen could not be tested at all. The rule is tested directly instead.
 */
import { useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import {
  AppText,
  Button,
  Card,
  DegradedModeBanner,
  Screen,
  TextField,
} from '../../src/components';
import { useIsOffline } from '../../src/hooks/useNetworkStatus';
import {
  DELETE_BUSY,
  DELETE_CANCEL,
  DELETE_CONFIRM,
  DELETE_DONE_TITLE,
  DELETE_PHRASE_LABEL,
  DELETE_PHRASE_MISMATCH,
  DELETE_START,
  deletionCounts,
  deletionResultSummary,
  remainingSummary,
} from '../../src/features/privacy/copy';
import { useConfirmDeletion, useRequestDeletion } from '../../src/features/privacy/hooks';
import { phraseMatches } from '../../src/features/privacy/validation';
import { apiErrorMessage } from '../../src/services/api/errors';
import { spacing } from '../../src/theme/tokens';

export default function DeleteDataScreen() {
  const router = useRouter();
  const request = useRequestDeletion();
  const confirm = useConfirmDeletion();
  const isOffline = useIsOffline();

  const [typed, setTyped] = useState('');
  const [message, setMessage] = useState<string | null>(null);

  const inventory = request.data ?? null;
  const result = confirm.data ?? null;

  // --- step three: it is done ----------------------------------------------
  if (result !== null) {
    return (
      <Screen>
        <View style={{ gap: spacing.lg }}>
          <AppText variant="title">{DELETE_DONE_TITLE}</AppText>
          <Card style={{ gap: spacing.sm }}>
            <AppText variant="body">
              {deletionResultSummary(
                result.rowsDeleted,
                result.filesDeleted,
                result.caregiversRevoked
              )}
            </AppText>
            {/* Reported rather than hidden. A file the row pointed at and
                storage did not have means something was already gone, and a
                privacy feature should not round that up to success. */}
            {result.filesMissing > 0 ? (
              <AppText variant="caption" tone="secondary">
                {result.filesMissing} file
                {result.filesMissing === 1 ? '' : 's'} had already been removed.
              </AppText>
            ) : null}
            <AppText variant="body" tone="secondary">
              {remainingSummary(result.otherProfilesRemaining)}
            </AppText>
          </Card>
          <Button
            label="Done"
            onPress={() => router.replace('/')}
            accessibilityHint="Returns to the start of the app"
          />
        </View>
      </Screen>
    );
  }

  // --- step one: what would go ---------------------------------------------
  if (inventory === null) {
    return (
      <Screen>
        {isOffline ? <DegradedModeBanner kind="offline" /> : null}
        <View style={{ gap: spacing.lg }}>
          <AppText variant="body">
            Deleting removes everything recorded on this profile. The next screen shows
            exactly what that is before anything happens.
          </AppText>
          <Button
            label={request.isPending ? 'Checking…' : DELETE_START}
            onPress={() => {
              setMessage(null);
              request.mutate(undefined, {
                onError: (error) => setMessage(apiErrorMessage(error)),
              });
            }}
            disabled={request.isPending}
            accessibilityHint="Shows what deleting this profile would remove"
          />
          <Button
            label={DELETE_CANCEL}
            variant="secondary"
            onPress={() => router.back()}
            accessibilityHint="Returns without deleting anything"
          />
          {message !== null ? (
            <AppText variant="body" tone="secondary" accessibilityLiveRegion="polite">
              {message}
            </AppText>
          ) : null}
        </View>
      </Screen>
    );
  }

  // --- step two: the warning, and the phrase -------------------------------
  const matches = phraseMatches(typed, inventory.confirmationPhrase);

  return (
    <Screen>
      {isOffline ? <DegradedModeBanner kind="offline" /> : null}
      <View style={{ gap: spacing.lg }}>
        <AppText variant="title">{inventory.title}</AppText>

        <Card style={{ gap: spacing.sm }}>
          {/* The server's warning, which lists the categories, and the counts
              it computed from the database. */}
          <AppText variant="body">{inventory.warning}</AppText>
          <AppText variant="bodyStrong">
            {deletionCounts(inventory.rowTotal, inventory.fileCount)}
          </AppText>
          {inventory.caregiverCount > 0 ? (
            <AppText variant="body" tone="secondary">
              {inventory.caregiverCount}{' '}
              {inventory.caregiverCount === 1 ? 'person' : 'people'} will lose access.
            </AppText>
          ) : null}
          {inventory.deviceCount > 0 ? (
            <AppText variant="body" tone="secondary">
              {inventory.deviceCount} {inventory.deviceCount === 1 ? 'robot' : 'robots'}{' '}
              will go back to being set up for nobody.
            </AppText>
          ) : null}
        </Card>

        <Card style={{ gap: spacing.sm }}>
          <AppText variant="body">{inventory.keeps}</AppText>
        </Card>

        {/* Section 44's documented limitation, said where it applies. */}
        <AppText variant="caption" tone="secondary">
          {inventory.reauthLimitation}
        </AppText>

        <View style={{ gap: spacing.sm }}>
          <AppText variant="body">{inventory.confirmPrompt}</AppText>
          <AppText variant="bodyStrong" accessibilityLabel={inventory.confirmationPhrase}>
            {inventory.confirmationPhrase}
          </AppText>
          <TextField
            label={DELETE_PHRASE_LABEL}
            value={typed}
            onChangeText={setTyped}
            autoCapitalize="characters"
            autoCorrect={false}
            accessibilityHint="Type the phrase shown above to confirm"
          />
          {typed.length > 0 && !matches ? (
            <AppText variant="caption" tone="secondary" accessibilityLiveRegion="polite">
              {DELETE_PHRASE_MISMATCH}
            </AppText>
          ) : null}
        </View>

        {/* No separate destructive variant exists in this design system, and
            adding one for a single screen would be a token nothing else uses.
            What makes this deliberate is the three steps and the typed phrase,
            not the colour. */}
        <Button
          label={confirm.isPending ? DELETE_BUSY : DELETE_CONFIRM}
          onPress={() => {
            setMessage(null);
            confirm.mutate(inventory.confirmationPhrase, {
              onError: (error) => setMessage(apiErrorMessage(error)),
            });
          }}
          // Both halves: the phrase has to match, and the request cannot
          // already be in flight. The server checks the phrase again.
          disabled={!matches || confirm.isPending}
          accessibilityHint="Permanently deletes this profile's data"
        />
        <Button
          label={DELETE_CANCEL}
          variant="secondary"
          onPress={() => router.back()}
          accessibilityHint="Returns without deleting anything"
        />

        {message !== null ? (
          <AppText variant="body" tone="secondary" accessibilityLiveRegion="polite">
            {message}
          </AppText>
        ) : null}
      </View>
    </Screen>
  );
}
