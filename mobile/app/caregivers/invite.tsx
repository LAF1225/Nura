/**
 * Inviting someone to help (PRD 9, sections 11, 12, 13, 15 and 66).
 *
 * Two things make this screen different from every other form in the app.
 *
 * **Nothing is granted by default** (section 66). Every category starts off, and
 * the person inviting has to choose. A form that arrived with medications and
 * appointments already ticked would be a broad default permission wearing a
 * checkbox.
 *
 * **Nura cannot send the invitation, and the screen says so** (section 12). There
 * is no mail sender or SMS gateway in this system, so what comes back is a link
 * for the primary user to pass on, shown once. A Send button that quietly did
 * nothing would be worse than this sentence.
 *
 * The form lives in a store rather than in component state, for the reason this
 * project keeps rediscovering: a store update re-renders under React 19 where a
 * local `useState` update from a fired event does not.
 */
import { useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { AppText, Button, Card, ListRow, Screen, TextField } from '../../src/components';
import { CAREGIVER_ROLES } from '../../src/features/caregivers/api';
import {
  CareErrorNote,
  PermissionToggleRow,
} from '../../src/features/caregivers/components/CaregiverCards';
import {
  INVITE_CONTACT_HINT,
  INVITE_CONTACT_LABEL,
  INVITE_DELIVERY,
  INVITE_FAILED,
  INVITE_INTRO,
  INVITE_LINK_ONCE,
  INVITE_LINK_PRIVATE,
  INVITE_LINK_TITLE,
  INVITE_NAME_HINT,
  INVITE_NAME_LABEL,
  INVITE_PERMISSIONS_LABEL,
  INVITE_ROLE_HINT,
  INVITE_ROLE_LABEL,
  INVITE_SEND,
  inviteExpirySentence,
} from '../../src/features/caregivers/copy';
import {
  useCreateInvitation,
  usePermissionCatalogue,
} from '../../src/features/caregivers/hooks';
import { useCareFormStore } from '../../src/features/caregivers/stores';
import type { CaregiverRole, InviteCreated } from '../../src/features/caregivers/types';
import { spacing } from '../../src/theme/tokens';

const ROLE_LABELS: Record<CaregiverRole, string> = {
  primary_caregiver: 'Primary caregiver',
  family: 'Family',
  caregiver: 'Caregiver',
  emergency_contact: 'Emergency contact',
  other: 'Other',
};

export default function InviteCaregiverScreen() {
  const router = useRouter();
  const create = useCreateInvitation();
  // The labels come from the server so this form and the permission screen
  // cannot describe a category differently (section 15).
  const catalogue = usePermissionCatalogue();
  const [created, setCreated] = useState<InviteCreated | null>(null);
  const [failed, setFailed] = useState(false);

  const name = useCareFormStore((state) => state.invitedName);
  const contact = useCareFormStore((state) => state.inviteContact);
  const role = useCareFormStore((state) => state.inviteRole);
  const permissions = useCareFormStore((state) => state.invitePermissions);
  const setName = useCareFormStore((state) => state.setInvitedName);
  const setContact = useCareFormStore((state) => state.setInviteContact);
  const setRole = useCareFormStore((state) => state.setInviteRole);
  const toggle = useCareFormStore((state) => state.toggleInvitePermission);
  const resetInvite = useCareFormStore((state) => state.resetInvite);

  const canSend = name.trim().length > 0 && !create.isPending;

  function send() {
    // Read at press time rather than from the render that queued this handler:
    // a press arriving before a store update has re-rendered would otherwise
    // send the previous value.
    const state = useCareFormStore.getState();
    const trimmed = state.invitedName.trim();
    if (trimmed.length === 0) return;
    const typed = state.inviteContact.trim();
    setFailed(false);
    create.mutate(
      {
        invitedName: trimmed,
        role: state.inviteRole as CaregiverRole,
        // One field for either, split on the @: asking somebody to choose
        // "email or phone" from a segmented control before typing is a step
        // that earns nothing, and this is a note rather than an address.
        email: typed.includes('@') ? typed : null,
        phone: typed.length > 0 && !typed.includes('@') ? typed : null,
        permissions: state.invitePermissions,
      },
      {
        onSuccess: (result) => {
          setCreated(result);
          resetInvite();
        },
        onError: () => setFailed(true),
      }
    );
  }

  if (created !== null) {
    return (
      <Screen>
        <View style={{ gap: spacing.md }}>
          <AppText variant="heading" accessibilityRole="header">
            {INVITE_LINK_TITLE}
          </AppText>
          <AppText variant="body">{INVITE_DELIVERY}</AppText>

          <Card style={{ gap: spacing.xs }}>
            {/* Selectable so it can be copied, and nothing else on the screen
                repeats it: section 13's single-use token is shown once. */}
            <AppText
              variant="body"
              selectable
              accessibilityLabel={`Invitation link for ${created.caregiver.invitedName}`}
            >
              {created.token}
            </AppText>
          </Card>

          <AppText variant="caption" tone="secondary">
            {INVITE_LINK_ONCE}
          </AppText>
          <AppText variant="caption" tone="secondary">
            {INVITE_LINK_PRIVATE}
          </AppText>
          {created.expiresAt ? (
            <AppText variant="caption" tone="secondary">
              {inviteExpirySentence(created.expiresAt.slice(0, 10))}
            </AppText>
          ) : null}

          <Button label="Done" onPress={() => router.back()} />
        </View>
      </Screen>
    );
  }

  return (
    <Screen>
      <View style={{ gap: spacing.md }}>
        <AppText variant="body" tone="secondary">
          {INVITE_INTRO}
        </AppText>

        <TextField
          label={INVITE_NAME_LABEL}
          hint={INVITE_NAME_HINT}
          value={name}
          onChangeText={setName}
        />
        <TextField
          label={INVITE_CONTACT_LABEL}
          hint={INVITE_CONTACT_HINT}
          value={contact}
          onChangeText={setContact}
          autoCapitalize="none"
        />

        <View style={{ gap: spacing.xxs }}>
          <AppText variant="bodyStrong">{INVITE_ROLE_LABEL}</AppText>
          <AppText variant="caption" tone="secondary">
            {INVITE_ROLE_HINT}
          </AppText>
          {CAREGIVER_ROLES.map((option) => (
            <ListRow
              key={option}
              label={ROLE_LABELS[option]}
              role="radio"
              selected={role === option}
              onPress={() => setRole(option)}
            />
          ))}
        </View>

        <View style={{ gap: spacing.xxs }}>
          <AppText variant="bodyStrong">{INVITE_PERMISSIONS_LABEL}</AppText>
          {(catalogue.data ?? []).map((permission) => (
            <PermissionToggleRow
              key={permission.key}
              permission={permission}
              value={permissions[permission.key] === true}
              onChange={() => toggle(permission.key)}
            />
          ))}
        </View>

        {failed ? <CareErrorNote message={INVITE_FAILED} /> : null}

        <Button label={INVITE_SEND} onPress={send} disabled={!canSend} />
      </View>
    </Screen>
  );
}
