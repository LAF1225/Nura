/**
 * The appointment form (PRD 7, sections 8 and 58).
 *
 * One component for adding and for editing, because they collect the same fields
 * and validate the same way. It reads and writes the form store rather than
 * holding local state, so the draft survives navigation and the app closing
 * (PRD 7, section 53).
 *
 * **Only the title, the date and the time are required.** PRD 7 section 8 asks
 * for the optional fields to stay optional, and the Save button is enabled as soon
 * as those three are valid.
 *
 * **The date and time are typed, not picked.** A native date picker would be
 * nicer, and PRD 7 section 58 asks for accessible date controls -- which a plain
 * labelled text field with a stated format genuinely is, while a custom wheel is
 * the control most often unusable with a screen reader. The format is shown in the
 * hint and validated on the field, so nobody has to guess.
 */
import { View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { Button } from '../../../components/Button';
import { SelectableCard, ToggleRow } from '../../../components/Choice';
import { TextField } from '../../../components/TextField';
import { spacing } from '../../../theme/tokens';
import { TYPE_LABELS, TYPE_ORDER } from '../copy';
import {
  NOTES_MAX_LENGTH,
  PHONE_MAX_LENGTH,
  SHORT_TEXT_MAX_LENGTH,
  TITLE_MAX_LENGTH,
  validateDraft,
} from '../draft';
import { useAppointmentFormStore } from '../formStore';
import type { ClinicianBrief } from '../types';

interface AppointmentFormProps {
  /** The user's own clinician list, for the optional link (PRD 7, section 6). */
  clinicians: ClinicianBrief[];
  /** True while the save is in flight. */
  isSaving: boolean;
  saveLabel: string;
  onSave: () => void;
  errorMessage?: string | null;
}

export function AppointmentForm({
  clinicians,
  isSaving,
  saveLabel,
  onSave,
  errorMessage,
}: AppointmentFormProps) {
  const draft = useAppointmentFormStore((state) => state.draft);
  const patch = useAppointmentFormStore((state) => state.patch);
  const setType = useAppointmentFormStore((state) => state.setType);
  const setClinician = useAppointmentFormStore((state) => state.setClinician);

  if (draft === null) return null;

  const errors = validateDraft(draft);
  const canSave = Object.keys(errors).length === 0 && !isSaving;
  // Errors are shown only once the field has been typed into, so an untouched
  // form does not open covered in red. Whitespace counts as typing: somebody who
  // has pressed space needs to be told that is not a name.
  const showError = (field: keyof typeof errors, value: string) =>
    value.length > 0 ? errors[field] : undefined;

  return (
    <View style={{ gap: spacing.lg }}>
      <TextField
        label="What is the appointment?"
        hint="For example, “Cardiology follow-up” or “Blood test”."
        value={draft.title}
        onChangeText={(title) => patch({ title })}
        error={showError('title', draft.title)}
        maxLength={TITLE_MAX_LENGTH}
        autoCapitalize="sentences"
      />

      <View style={{ flexDirection: 'row', gap: spacing.sm }}>
        <View style={{ flex: 1 }}>
          <TextField
            label="Date"
            hint="YYYY-MM-DD"
            value={draft.date}
            onChangeText={(date) => patch({ date })}
            error={showError('date', draft.date)}
            keyboardType="numbers-and-punctuation"
            maxLength={10}
          />
        </View>
        <View style={{ flex: 1 }}>
          <TextField
            label="Time"
            hint="24-hour, e.g. 15:30"
            value={draft.time}
            onChangeText={(time) => patch({ time })}
            error={showError('time', draft.time)}
            keyboardType="numbers-and-punctuation"
            maxLength={5}
          />
        </View>
      </View>

      <AppText variant="caption" tone="secondary">
        {`Times are kept in ${draft.timezone}, so this stays the same if you travel.`}
      </AppText>

      <View style={{ gap: spacing.xs }}>
        <AppText variant="bodyStrong" accessibilityRole="header">
          Kind of appointment
        </AppText>
        <View accessibilityRole="radiogroup" style={{ gap: spacing.xs }}>
          {TYPE_ORDER.map((type) => (
            <SelectableCard
              key={type}
              title={TYPE_LABELS[type]}
              description="Used to group your appointments. Nothing medical is inferred from it."
              selected={draft.appointmentType === type}
              onPress={() => setType(type)}
            />
          ))}
        </View>
      </View>

      {clinicians.length > 0 ? (
        <View style={{ gap: spacing.xs }}>
          <AppText variant="bodyStrong" accessibilityRole="header">
            Who are you seeing?
          </AppText>
          <AppText variant="caption" tone="secondary">
            Optional. Linking a clinician lets Nura work out what has changed since you
            last saw them.
          </AppText>
          <View accessibilityRole="radiogroup" style={{ gap: spacing.xs }}>
            <SelectableCard
              title="Not linked"
              description="Leave this appointment without a clinician."
              selected={draft.clinicianId === null}
              onPress={() => setClinician(null)}
            />
            {clinicians.map((clinician) => (
              <SelectableCard
                key={clinician.id}
                title={clinician.name}
                description={clinician.specialty ?? 'From your list of doctors'}
                selected={draft.clinicianId === clinician.id}
                onPress={() => setClinician(clinician.id)}
              />
            ))}
          </View>
        </View>
      ) : null}

      <TextField
        label="Where is it?"
        hint="Optional."
        value={draft.locationName}
        onChangeText={(locationName) => patch({ locationName })}
        maxLength={SHORT_TEXT_MAX_LENGTH}
      />

      <TextField
        label="Address"
        hint="Optional."
        value={draft.address}
        onChangeText={(address) => patch({ address })}
        maxLength={SHORT_TEXT_MAX_LENGTH}
      />

      <TextField
        label="Phone number"
        hint="Optional."
        value={draft.phone}
        onChangeText={(phone) => patch({ phone })}
        keyboardType="phone-pad"
        maxLength={PHONE_MAX_LENGTH}
      />

      <TextField
        label="Anything to remember"
        hint="Optional. For example, “bring the previous scan”."
        value={draft.notes}
        onChangeText={(notes) => patch({ notes })}
        multiline
        numberOfLines={3}
        maxLength={NOTES_MAX_LENGTH}
      />

      <ToggleRow
        label="Remind me"
        description="A day before, and two hours before."
        value={draft.remindersEnabled}
        onChange={(remindersEnabled) => patch({ remindersEnabled })}
      />

      {errorMessage ? (
        <AppText variant="body" tone="secondary">
          {errorMessage}
        </AppText>
      ) : null}

      <Button
        label={isSaving ? 'Saving…' : saveLabel}
        onPress={onSave}
        disabled={!canSave}
        accessibilityHint="Saves this appointment"
      />
    </View>
  );
}
