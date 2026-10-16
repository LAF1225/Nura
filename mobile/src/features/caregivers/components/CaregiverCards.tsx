/**
 * The cards and rows the caregiver screens are built from.
 *
 * PRD 9, sections 15, 18, 77, 84, 86 and 88.
 *
 * Accessibility is the reason several of these look plainer than they could
 * (section 77): every state is announced as well as drawn, nothing is carried by
 * colour alone, and every pressable is at least 48dp. A permission row is a
 * `switch` with its own label and description rather than a coloured pill,
 * because a screen reader has to be able to say what it is and whether it is on.
 *
 * `PermissionToggleRow` is also where section 15's rule about wording lands: the
 * label and description come from the server, so the invitation screen and the
 * permission screen cannot describe a category differently.
 */
import { View } from 'react-native';

import { AppText, Card, ListRow, StatusChip, ToggleRow } from '../../../components';
import { spacing } from '../../../theme/tokens';
import {
  CHECK_IN_LABELS,
  CONTACT_INACTIVE,
  grantedSentence,
  MOVE_DOWN,
  MOVE_UP,
  PERMISSION_NOT_YET,
  priorityLabel,
  sharedAreasSentence,
  STATUS_LABELS,
  SUGGESTION_CURRENT,
  SUGGESTION_PROPOSED,
  SUGGESTION_STATUS_LABELS,
  SUGGESTION_TARGET_MISSING,
  suggestedBy,
} from '../copy';
import type {
  Caregiver,
  EmergencyContact,
  FamilyMessage,
  Permission,
  Suggestion,
  SupportedProfile,
} from '../types';

/**
 * One sentence saying something did not work.
 *
 * Not `FlowErrorCard`, which is for a flow with recovery actions (retry, start
 * again, get help). A permission that did not save needs one sentence and the
 * Save button still there, and announcing it as an alert is what tells a screen
 * reader user that the press they just made did not take.
 */
export function CareErrorNote({ message }: { message: string }) {
  return (
    <View accessible accessibilityRole="alert" accessibilityLabel={message}>
      <AppText variant="body" tone="danger">
        {message}
      </AppText>
    </View>
  );
}

// --- a caregiver in a list ---------------------------------------------------

export function CaregiverCard({
  caregiver,
  total,
  onPress,
}: {
  caregiver: Caregiver;
  total: number;
  onPress: () => void;
}) {
  const tone = caregiver.status === 'active' ? 'success' : 'neutral';
  return (
    <Card style={{ gap: spacing.xs }}>
      <View
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: spacing.sm,
        }}
      >
        <AppText variant="bodyStrong">{caregiver.invitedName}</AppText>
        <StatusChip label={STATUS_LABELS[caregiver.status]} tone={tone} />
      </View>
      <AppText variant="caption" tone="secondary">
        {caregiver.roleLabel}
      </AppText>
      <AppText variant="body" tone="secondary">
        {grantedSentence(caregiver.grantedCount, total)}
      </AppText>
      <ListRow
        label="Manage"
        onPress={onPress}
        showChevron
        accessibilityHint={`Opens what ${caregiver.invitedName} can see`}
      />
    </Card>
  );
}

// --- one permission ----------------------------------------------------------

export function PermissionToggleRow({
  permission,
  value,
  onChange,
}: {
  permission: Permission;
  value: boolean;
  onChange: (value: boolean) => void;
}) {
  // A granted category with nothing behind it says so (sections 94 and 18's
  // cousin): an empty section reads as "nothing recorded", which would be a
  // different and wrong statement.
  const dormant = value && !permission.hasData;
  return (
    <View style={{ gap: spacing.xxs }}>
      <ToggleRow
        label={permission.label}
        description={permission.description}
        value={value}
        onChange={onChange}
      />
      {dormant ? (
        <AppText
          variant="caption"
          tone="secondary"
          style={{ paddingHorizontal: spacing.md }}
        >
          {PERMISSION_NOT_YET[permission.key] ?? ''}
        </AppText>
      ) : null}
    </View>
  );
}

// --- the two lists an invitation shows (section 15) --------------------------

export function AccessSummary({
  title,
  items,
  tone = 'secondary',
}: {
  title: string;
  items: string[];
  tone?: 'secondary' | 'primary';
}) {
  if (items.length === 0) return null;
  return (
    <View style={{ gap: spacing.xxs }}>
      <AppText variant="bodyStrong">{title}</AppText>
      {items.map((item) => (
        <AppText key={item} variant="body" tone={tone}>
          {item}
        </AppText>
      ))}
    </View>
  );
}

// --- a suggestion ------------------------------------------------------------

/**
 * The explicit diff section 86 asks for.
 *
 * Both halves come from the server, labelled rather than implied: "Now" and
 * "Suggested" as their own lines, so the difference is readable aloud and does
 * not depend on seeing two values side by side.
 */
export function SuggestionCard({
  suggestion,
  onPress,
  showWho = true,
}: {
  suggestion: Suggestion;
  onPress?: () => void;
  showWho?: boolean;
}) {
  return (
    <Card style={{ gap: spacing.xs }}>
      {showWho ? (
        <AppText variant="bodyStrong">{suggestedBy(suggestion.caregiverName)}</AppText>
      ) : (
        <AppText variant="bodyStrong">{suggestion.actionLabel}</AppText>
      )}
      <AppText variant="caption" tone="secondary">
        {suggestion.actionLabel}
      </AppText>
      <AppText variant="body">{suggestion.diff.subject}</AppText>

      {suggestion.diff.current !== null ? (
        <View style={{ gap: spacing.xxs }}>
          <AppText variant="caption" tone="secondary">
            {SUGGESTION_CURRENT}
          </AppText>
          <AppText variant="body">{suggestion.diff.current}</AppText>
        </View>
      ) : null}

      <View style={{ gap: spacing.xxs }}>
        <AppText variant="caption" tone="secondary">
          {SUGGESTION_PROPOSED}
        </AppText>
        <AppText variant="bodyStrong">{suggestion.diff.proposed}</AppText>
      </View>

      {suggestion.diff.targetMissing ? (
        <AppText variant="body" tone="secondary">
          {SUGGESTION_TARGET_MISSING}
        </AppText>
      ) : null}

      <StatusChip
        label={SUGGESTION_STATUS_LABELS[suggestion.status] ?? suggestion.status}
        tone={suggestion.status === 'pending' ? 'warning' : 'neutral'}
      />

      {onPress ? (
        <ListRow
          label="Review"
          onPress={onPress}
          showChevron
          accessibilityHint="Opens this care request"
        />
      ) : null}
    </Card>
  );
}

// --- a message ---------------------------------------------------------------

/**
 * One line in a care thread.
 *
 * `mine` decides the alignment, and it comes from the side the *server* recorded
 * rather than from an account id the app matched: a deleted account must not turn
 * half a conversation into messages from nobody.
 */
export function FamilyMessageBubble({
  message,
  mine,
  statusLabel,
}: {
  message: FamilyMessage;
  mine: boolean;
  statusLabel?: string;
}) {
  const label = message.checkInCode
    ? (CHECK_IN_LABELS[message.checkInCode] ?? message.text ?? '')
    : (message.text ?? '');
  return (
    <View
      style={{
        alignSelf: mine ? 'flex-end' : 'flex-start',
        maxWidth: '86%',
        gap: spacing.xxs,
      }}
    >
      <Card style={{ paddingVertical: spacing.sm }}>
        <AppText variant="body" accessibilityLabel={`${mine ? 'You' : 'Them'}: ${label}`}>
          {label}
        </AppText>
      </Card>
      {statusLabel ? (
        <AppText
          variant="caption"
          tone="secondary"
          style={{ alignSelf: mine ? 'flex-end' : 'flex-start' }}
        >
          {statusLabel}
        </AppText>
      ) : null}
    </View>
  );
}

// --- an emergency contact ----------------------------------------------------

/**
 * One contact, with move-up and move-down rather than drag-and-drop.
 *
 * Section 89 allows either and says to prefer explicit controls when
 * drag-and-drop is unstable or inaccessible. A reorder that depends on a long
 * press and a steady drag is exactly what section 77's "48dp, screen readers,
 * large text" rules out for this product, and these two buttons are announceable
 * and work with a shaking hand.
 */
export function EmergencyContactRow({
  contact,
  isFirst,
  isLast,
  onMoveUp,
  onMoveDown,
  onPress,
}: {
  contact: EmergencyContact;
  isFirst: boolean;
  isLast: boolean;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onPress: () => void;
}) {
  const detail = [contact.relationshipLabel, contact.phone]
    .filter((part): part is string => Boolean(part))
    .join(' · ');
  return (
    <Card style={{ gap: spacing.xs }}>
      <View
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: spacing.sm,
        }}
      >
        <AppText variant="bodyStrong">{contact.name}</AppText>
        <AppText variant="caption" tone="secondary">
          {priorityLabel(contact.priority)}
        </AppText>
      </View>
      {detail ? (
        <AppText variant="body" tone="secondary">
          {detail}
        </AppText>
      ) : null}
      {!contact.isActive ? <StatusChip label={CONTACT_INACTIVE} tone="neutral" /> : null}

      {/* Hidden at the ends rather than present and inert: a control that
          announces itself and does nothing is worse than one that is not there. */}
      <View style={{ flexDirection: 'row', gap: spacing.sm }}>
        {!isFirst ? (
          <ListRow
            label={MOVE_UP}
            onPress={onMoveUp}
            accessibilityHint={`Moves ${contact.name} earlier in the list`}
          />
        ) : null}
        {!isLast ? (
          <ListRow
            label={MOVE_DOWN}
            onPress={onMoveDown}
            accessibilityHint={`Moves ${contact.name} later in the list`}
          />
        ) : null}
      </View>
      <ListRow
        label="Edit"
        onPress={onPress}
        showChevron
        accessibilityHint={`Opens ${contact.name}'s details`}
      />
    </Card>
  );
}

// --- the profile switcher ----------------------------------------------------

export function ProfileSwitcherRow({
  label,
  description,
  selected,
  onPress,
}: {
  label: string;
  description: string;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <ListRow
      label={label}
      description={description}
      role="radio"
      selected={selected}
      onPress={onPress}
      accessibilityHint={selected ? undefined : `Switches to ${label}`}
    />
  );
}

// --- what a caregiver supports -----------------------------------------------

export function SupportedProfileCard({
  profile,
  selected,
  onPress,
}: {
  profile: SupportedProfile;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Card style={{ gap: spacing.xs }}>
      <AppText variant="bodyStrong">{profile.profileName}</AppText>
      <AppText variant="caption" tone="secondary">
        {profile.roleLabel}
      </AppText>
      <AppText variant="body" tone="secondary">
        {sharedAreasSentence(profile.granted.length)}
      </AppText>
      <ListRow
        label={selected ? 'Currently viewing' : 'View their care'}
        role="radio"
        selected={selected}
        onPress={onPress}
        accessibilityHint={`Switches to ${profile.profileName}`}
      />
    </Card>
  );
}
