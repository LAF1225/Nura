/**
 * One caregiver: their label, what they can see, and removing them.
 *
 * PRD 9, sections 52, 53, 54 and 83.
 *
 * Detail and permissions on one screen rather than two. Section 83 lists them
 * separately and this is the deviation: everything a person does here is about
 * the same question -- what can this person see -- and sending them through a
 * second screen to answer it adds a step without adding clarity. The role
 * selector carries the sentence section 54 needs, right next to itself.
 *
 * **Save is explicit.** A toggle changes what is being edited; the request goes
 * when Save is pressed. Section 53 asks for the server-side effect to be
 * immediate *after a successful save*, and a screen that fired a request per
 * toggle would make a half-finished permission set real for as long as somebody
 * was still deciding.
 */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import {
  AppText,
  AsyncState,
  Button,
  Card,
  ListRow,
  Screen,
  StatusChip,
} from '../../src/components';
import { CAREGIVER_ROLES } from '../../src/features/caregivers/api';
import {
  CareErrorNote,
  PermissionToggleRow,
} from '../../src/features/caregivers/components/CaregiverCards';
import {
  PERMISSIONS_FAILED,
  PERMISSIONS_INTRO,
  PERMISSIONS_SAVE,
  PERMISSIONS_SAVED,
  PERMISSIONS_TITLE,
  REMOVE_BODY,
  confirmRemoveLabel,
  KEEP_BUTTON,
  REMOVE_BUTTON,
  REMOVE_FAILED,
  REMOVE_TITLE,
  ROLE_NOTE,
  STATUS_LABELS,
  WITHDRAW_INVITATION_BODY,
} from '../../src/features/caregivers/copy';
import {
  useCaregivers,
  useRevokeCaregiver,
  useUpdateCaregiverRole,
  useUpdatePermissions,
} from '../../src/features/caregivers/hooks';
import {
  NO_EDITED_PERMISSIONS,
  useCareFormStore,
} from '../../src/features/caregivers/stores';
import type { CaregiverRole } from '../../src/features/caregivers/types';
import { spacing } from '../../src/theme/tokens';

const ROLE_LABELS: Record<CaregiverRole, string> = {
  primary_caregiver: 'Primary caregiver',
  family: 'Family',
  caregiver: 'Caregiver',
  emergency_contact: 'Emergency contact',
  other: 'Other',
};

export default function CaregiverDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const relationshipId = id ?? '';
  const router = useRouter();
  const caregivers = useCaregivers(true);
  const updatePermissions = useUpdatePermissions();
  const updateRole = useUpdateCaregiverRole();
  const revoke = useRevokeCaregiver();

  // Selected with a stable fallback: `?? {}` inside a selector builds a new
  // object every render, which Zustand reads as a change and re-renders for
  // ever.
  const edited =
    useCareFormStore((state) => state.editedPermissions[relationshipId]) ??
    NO_EDITED_PERMISSIONS;
  const setEdited = useCareFormStore((state) => state.setEditedPermission);
  const clearEdited = useCareFormStore((state) => state.clearEditedPermissions);

  const [saved, setSaved] = useState(false);
  const [failed, setFailed] = useState(false);
  // In the store, so the second press sees the first one (React 19 + RNTL).
  const confirming = useCareFormStore((state) => state.confirmingRemoval);
  const setConfirming = useCareFormStore((state) => state.setConfirmingRemoval);
  const confirmingRemove = confirming === relationshipId;

  const caregiver = (caregivers.data?.caregivers ?? []).find(
    (row) => row.id === relationshipId
  );

  function save() {
    // Read at press time: a press arriving before a store update has
    // re-rendered would otherwise send the previous set.
    const pending = useCareFormStore.getState().editedPermissions[relationshipId] ?? {};
    if (Object.keys(pending).length === 0) return;
    setFailed(false);
    updatePermissions.mutate(
      { relationshipId, permissions: pending },
      {
        onSuccess: () => {
          clearEdited(relationshipId);
          setSaved(true);
        },
        onError: () => setFailed(true),
      }
    );
  }

  const dirty = Object.keys(edited).length > 0;

  return (
    <Screen
      onRefresh={() => void caregivers.refetch()}
      refreshing={caregivers.isRefetching && !caregivers.isLoading}
    >
      <AsyncState
        status={caregivers.isError ? 'error' : 'success'}
        error={caregivers.error}
        isEmpty={caregiver === undefined}
        emptyMessage="That caregiver is no longer here."
        loadingLabel="Loading caregiver"
        onRetry={() => void caregivers.refetch()}
      >
        {caregiver === undefined ? null : (
          <View style={{ gap: spacing.lg }}>
            <View style={{ gap: spacing.xs }}>
              <AppText variant="title" accessibilityRole="header">
                {caregiver.invitedName}
              </AppText>
              <StatusChip
                label={STATUS_LABELS[caregiver.status]}
                tone={caregiver.status === 'active' ? 'success' : 'neutral'}
              />
              {caregiver.inviteEmail || caregiver.invitePhone ? (
                <AppText variant="body" tone="secondary">
                  {caregiver.inviteEmail ?? caregiver.invitePhone}
                </AppText>
              ) : null}
            </View>

            <View style={{ gap: spacing.xxs }}>
              <AppText variant="bodyStrong">How they are related</AppText>
              <AppText variant="caption" tone="secondary">
                {ROLE_NOTE}
              </AppText>
              {CAREGIVER_ROLES.map((option) => (
                <ListRow
                  key={option}
                  label={ROLE_LABELS[option]}
                  role="radio"
                  selected={caregiver.role === option}
                  onPress={() => updateRole.mutate({ relationshipId, role: option })}
                />
              ))}
            </View>

            <View style={{ gap: spacing.xxs }}>
              <AppText variant="heading" accessibilityRole="header">
                {PERMISSIONS_TITLE}
              </AppText>
              <AppText variant="caption" tone="secondary">
                {PERMISSIONS_INTRO}
              </AppText>
              {caregiver.permissions.map((permission) => {
                const value = edited[permission.key] ?? permission.allowed;
                return (
                  <PermissionToggleRow
                    key={permission.key}
                    permission={permission}
                    value={value}
                    onChange={(next) => {
                      setSaved(false);
                      setEdited(relationshipId, permission.key, next);
                    }}
                  />
                );
              })}
            </View>

            {failed ? <CareErrorNote message={PERMISSIONS_FAILED} /> : null}

            <Button
              label={saved && !dirty ? PERMISSIONS_SAVED : PERMISSIONS_SAVE}
              onPress={save}
              disabled={!dirty || updatePermissions.isPending}
            />

            <Card style={{ gap: spacing.sm }}>
              <AppText variant="bodyStrong">{REMOVE_TITLE}</AppText>
              <AppText variant="body" tone="secondary">
                {caregiver.status === 'pending' ? WITHDRAW_INVITATION_BODY : REMOVE_BODY}
              </AppText>
              {/* The confirm step says who, and offers a way out. Two presses
                  of an identically-labelled button would give somebody no sign
                  that the first one did anything -- and section 77 asks for
                  approval controls that state what will change. */}
              {confirmingRemove ? (
                <View style={{ gap: spacing.sm }}>
                  <Button
                    label={confirmRemoveLabel(caregiver.invitedName)}
                    onPress={() =>
                      revoke.mutate(relationshipId, {
                        onSuccess: () => {
                          setConfirming(null);
                          router.back();
                        },
                        onError: () => setFailed(true),
                      })
                    }
                    disabled={revoke.isPending}
                  />
                  <Button
                    label={KEEP_BUTTON}
                    variant="ghost"
                    onPress={() => setConfirming(null)}
                  />
                </View>
              ) : (
                <Button
                  label={REMOVE_BUTTON}
                  variant="secondary"
                  onPress={() => setConfirming(relationshipId)}
                  accessibilityHint="Asks you to confirm before removing them"
                />
              )}
              {revoke.isError ? <CareErrorNote message={REMOVE_FAILED} /> : null}
            </Card>
          </View>
        )}
      </AsyncState>
    </Screen>
  );
}
