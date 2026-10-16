/**
 * Adding or editing one emergency contact (PRD 9, sections 43, 45 and 46).
 *
 * `new` is the create form and any other id is the edit form, so one screen holds
 * the whole of what a contact is -- and the two cannot drift about which fields
 * exist.
 *
 * **Priority is not on this form.** The chain's order is changed by reordering the
 * whole list, which is what keeps it contiguous (section 45) -- and the backend
 * has no priority field on the create or the patch, so a form with one would be
 * offering something the server refuses.
 *
 * **There is no "verified" state.** Section 46 recommends verification *if the
 * infrastructure exists*; nothing in this system can send a code to a phone, so a
 * badge that could only ever read "unverified" would say less than its absence.
 *
 * The form lives in a store rather than in component state, for the React 19
 * re-render reason this project keeps meeting.
 */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { View } from 'react-native';

import {
  AppText,
  Button,
  Card,
  Screen,
  TextField,
  ToggleRow,
} from '../../src/components';
import { CareErrorNote } from '../../src/features/caregivers/components/CaregiverCards';
import {
  CONTACT_ACTIVE_LABEL,
  CONTACT_DELETE,
  CONTACT_FAILED,
  CONTACT_NAME_LABEL,
  CONTACT_PHONE_LABEL,
  CONTACT_RELATIONSHIP_HINT,
  CONTACT_RELATIONSHIP_LABEL,
  CONTACT_SAVE,
  CONTACT_SAVED,
  CONTACTS_NOT_YET,
} from '../../src/features/caregivers/copy';
import {
  useCreateContact,
  useDeleteContact,
  useEmergencyContacts,
  useUpdateContact,
} from '../../src/features/caregivers/hooks';
import { useCareFormStore } from '../../src/features/caregivers/stores';
import { spacing } from '../../src/theme/tokens';

export default function EmergencyContactFormScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const contactId = id ?? 'new';
  const isNew = contactId === 'new';
  const router = useRouter();

  const contacts = useEmergencyContacts();
  const create = useCreateContact();
  const update = useUpdateContact();
  const remove = useDeleteContact();

  const name = useCareFormStore((state) => state.contactName);
  const phone = useCareFormStore((state) => state.contactPhone);
  const relationship = useCareFormStore((state) => state.contactRelationship);
  const active = useCareFormStore((state) => state.contactActive);
  const setName = useCareFormStore((state) => state.setContactName);
  const setPhone = useCareFormStore((state) => state.setContactPhone);
  const setRelationship = useCareFormStore((state) => state.setContactRelationship);
  const setActive = useCareFormStore((state) => state.setContactActive);
  const loadContact = useCareFormStore((state) => state.loadContact);
  const resetContact = useCareFormStore((state) => state.resetContact);

  const [saved, setSaved] = useState(false);
  const [failed, setFailed] = useState(false);

  const existing = (contacts.data?.contacts ?? []).find((row) => row.id === contactId);

  // Loaded once the contact arrives, and cleared for a new one. The store is
  // shared, so a form opened after another must not inherit its values.
  //
  // The ref is what stops a background refetch overwriting what somebody is
  // halfway through typing: the form is filled from the server once per contact
  // and not again.
  const loadedFor = useRef<string | null>(null);
  useEffect(() => {
    if (isNew) {
      if (loadedFor.current !== 'new') {
        resetContact();
        loadedFor.current = 'new';
      }
      return;
    }
    if (existing === undefined || loadedFor.current === existing.id) return;
    loadContact({
      name: existing.name,
      phone: existing.phone ?? '',
      relationship: existing.relationshipLabel ?? '',
      isActive: existing.isActive,
    });
    loadedFor.current = existing.id;
  }, [isNew, existing, loadContact, resetContact]);

  function save() {
    // Read at press time, for the usual reason.
    const state = useCareFormStore.getState();
    const trimmed = state.contactName.trim();
    if (trimmed.length === 0) return;
    const input = {
      name: trimmed,
      phone: state.contactPhone.trim().length > 0 ? state.contactPhone.trim() : null,
      relationshipLabel:
        state.contactRelationship.trim().length > 0
          ? state.contactRelationship.trim()
          : null,
      isActive: state.contactActive,
    };
    setFailed(false);
    const options = {
      onSuccess: () => {
        setSaved(true);
        resetContact();
        router.back();
      },
      onError: () => setFailed(true),
    };
    if (isNew) {
      create.mutate(input, options);
    } else {
      update.mutate({ contactId, input }, options);
    }
  }

  const pending = create.isPending || update.isPending;

  return (
    <Screen>
      <View style={{ gap: spacing.md }}>
        <Card>
          <AppText variant="caption" tone="secondary">
            {CONTACTS_NOT_YET}
          </AppText>
        </Card>

        <TextField label={CONTACT_NAME_LABEL} value={name} onChangeText={setName} />
        <TextField
          label={CONTACT_PHONE_LABEL}
          value={phone}
          onChangeText={setPhone}
          keyboardType="phone-pad"
        />
        <TextField
          label={CONTACT_RELATIONSHIP_LABEL}
          hint={CONTACT_RELATIONSHIP_HINT}
          value={relationship}
          onChangeText={setRelationship}
        />
        <ToggleRow label={CONTACT_ACTIVE_LABEL} value={active} onChange={setActive} />

        {failed ? <CareErrorNote message={CONTACT_FAILED} /> : null}

        <Button
          label={saved ? CONTACT_SAVED : CONTACT_SAVE}
          onPress={save}
          disabled={name.trim().length === 0 || pending}
        />

        {!isNew ? (
          <Button
            label={CONTACT_DELETE}
            variant="secondary"
            onPress={() =>
              remove.mutate(contactId, {
                onSuccess: () => router.back(),
                onError: () => setFailed(true),
              })
            }
            disabled={remove.isPending}
          />
        ) : null}
      </View>
    </Screen>
  );
}
