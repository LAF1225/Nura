/**
 * Adding or changing one health record (PRD 4, sections 20, 30, 36 and 46).
 *
 * One screen for all six record types: the route says which section, the
 * section spec says which fields, and `form.ts` decides what the values mean.
 *
 * Two promises this screen keeps:
 *
 * **An edit that could not be saved is not lost.** If a save fails, the values
 * stay on screen *and* are written to the device, so closing the app does not
 * throw them away (PRD 4, section 36).
 *
 * **Nothing is removed without being asked.** Delete goes through a native
 * alert naming the record (section 46).
 */
import { useLocalSearchParams, useNavigation, useRouter } from 'expo-router';
import { useEffect, useLayoutEffect, useState } from 'react';
import { Alert, View } from 'react-native';

import { AppText, Button, Card, Screen, SkeletonCard } from '../../../src/components';
import { RecordForm } from '../../../src/features/health/components/RecordForm';
import { clearDraft, loadDraft, saveDraft } from '../../../src/features/health/drafts';
import {
  buildPayload,
  initialValues,
  isValid,
  validate,
  type FieldErrors,
} from '../../../src/features/health/form';
import {
  useDeleteRecord,
  useHealthRecords,
  useSaveRecord,
} from '../../../src/features/health/hooks';
import { isRecordSection, SECTIONS } from '../../../src/features/health/sections';
import type { FormValues, HealthRecord } from '../../../src/features/health/types';
import { apiErrorMessage } from '../../../src/services/api';
import { spacing } from '../../../src/theme/tokens';

function recordTitle(record: HealthRecord | null, field: string): string {
  const value = record?.[field];
  return typeof value === 'string' && value.length > 0 ? value : 'this record';
}

export default function HealthRecordFormScreen() {
  const { section, id } = useLocalSearchParams<{ section: string; id: string }>();
  const router = useRouter();
  const navigation = useNavigation();

  const spec = isRecordSection(section) ? SECTIONS[section] : SECTIONS.conditions;
  const known = isRecordSection(section);
  const isNew = id === 'new';

  const records = useHealthRecords(spec);
  const save = useSaveRecord(spec);
  const remove = useDeleteRecord(spec);

  const record = isNew ? null : (records.data?.find((item) => item.id === id) ?? null);

  /**
   * Edits are an overlay on the record rather than copied into state when it
   * arrives: nothing to keep in sync, no effect, and the form renders
   * correctly on the first frame it has data.
   */
  const [edits, setEdits] = useState<FormValues | null>(null);
  const [errors, setErrors] = useState<FieldErrors>({});
  const values = edits ?? initialValues(spec, record);

  useLayoutEffect(() => {
    navigation.setOptions({
      title: isNew ? `Add ${spec.singular}` : `Edit ${spec.singular}`,
    });
  }, [navigation, isNew, spec]);

  // An unsaved form from last time, if there is one for exactly this record.
  useEffect(() => {
    let active = true;
    void loadDraft(spec.key, isNew ? 'new' : String(id)).then((draft) => {
      if (active && draft) setEdits(draft);
    });
    return () => {
      active = false;
    };
  }, [spec.key, id, isNew]);

  const change = (key: string, value: string | boolean | null) => {
    setEdits({ ...values, [key]: value });
    // Clearing the error as the field changes means someone is not told they
    // are wrong while they are in the middle of fixing it.
    if (errors[key]) {
      setErrors((current) => {
        const next = { ...current };
        delete next[key];
        return next;
      });
    }
  };

  const onSave = () => {
    const found = validate(spec, values);
    setErrors(found);
    if (!isValid(found)) return;

    save.mutate(
      { recordId: isNew ? undefined : String(id), payload: buildPayload(spec, values) },
      {
        onSuccess: () => {
          void clearDraft();
          router.back();
        },
        onError: () => {
          // Kept on the device, so the answer survives the app closing.
          void saveDraft(spec.key, isNew ? 'new' : String(id), values);
        },
      }
    );
  };

  const onRemove = () => {
    Alert.alert(
      `Remove this ${spec.singular}?`,
      `This removes ${recordTitle(record, spec.titleField)} from your Nura health profile.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Remove',
          style: 'destructive',
          onPress: () =>
            remove.mutate(String(id), {
              onSuccess: () => {
                void clearDraft();
                router.back();
              },
            }),
        },
      ]
    );
  };

  if (!known) {
    return (
      <Screen>
        <Card>
          <AppText variant="body" tone="secondary">
            That part of your health profile isn’t available in this version of Nura.
          </AppText>
        </Card>
      </Screen>
    );
  }

  // Waiting on the record this form is editing.
  if (!isNew && records.isLoading) {
    return (
      <Screen>
        <Card>
          <SkeletonCard lines={5} label="Loading" />
        </Card>
      </Screen>
    );
  }

  if (!isNew && !records.isLoading && record === null) {
    return (
      <Screen>
        <Card style={{ gap: spacing.sm }}>
          <AppText variant="body" tone="secondary">
            That {spec.singular} is no longer in your health profile.
          </AppText>
          <Button label="Go back" variant="secondary" onPress={() => router.back()} />
        </Card>
      </Screen>
    );
  }

  const busy = save.isPending || remove.isPending;

  return (
    <Screen>
      <View style={{ gap: spacing.xl }}>
        <RecordForm
          spec={spec}
          values={values}
          errors={errors}
          onChange={change}
          disabled={busy}
        />

        {save.isError ? (
          <Card style={{ gap: spacing.xs }}>
            <AppText variant="body" tone="secondary">
              {apiErrorMessage(save.error)}
            </AppText>
            {/* The promise in PRD 4 section 36, stated plainly. */}
            <AppText variant="caption" tone="secondary">
              What you typed has been kept on this phone. Try again when you’re ready.
            </AppText>
          </Card>
        ) : null}

        {remove.isError ? (
          <AppText variant="body" tone="secondary">
            {apiErrorMessage(remove.error)}
          </AppText>
        ) : null}

        <View style={{ gap: spacing.sm }}>
          <Button
            label={save.isPending ? 'Saving…' : 'Save'}
            disabled={busy}
            onPress={onSave}
          />
          <Button
            label="Cancel"
            variant="secondary"
            disabled={busy}
            onPress={() => {
              void clearDraft();
              router.back();
            }}
          />
          {!isNew ? (
            <Button
              label={`Remove ${spec.singular}`}
              variant="ghost"
              disabled={busy}
              onPress={onRemove}
              accessibilityHint={`Removes this ${spec.singular} from your health profile`}
            />
          ) : null}
        </View>

        <AppText variant="caption" tone="secondary">
          Only what you enter is stored. Nura does not check or interpret it.
        </AppText>
      </View>
    </Screen>
  );
}
