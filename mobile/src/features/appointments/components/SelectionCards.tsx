/**
 * The tickable review cards (PRD 7, sections 15, 17, 25 and 62).
 *
 * One component per kind of thing the user chooses to include: a symptom, a
 * medication, a report section, a note. They share a shape on purpose -- a
 * checkbox, a name, and the counted facts underneath -- because the point of the
 * selection screens is that the user can see what each switch would put in the
 * report.
 *
 * **Nothing here recommends anything.** No card is highlighted, ordered by
 * importance, or marked as significant. PRD 7 section 15 puts that decision with
 * the user, and a "recommended" badge would be Nura making it for them.
 *
 * Selection is shown with a checkbox and announced to a screen reader, never by
 * colour alone (PRD 7, section 58).
 */
import { Ionicons } from '@expo/vector-icons';
import type { ReactNode } from 'react';
import { Pressable, View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { useTheme } from '../../../theme';
import { iconSize, minTouchTarget, radius, spacing } from '../../../theme/tokens';
import { symptomReviewLines } from '../copy';
import type { MedicationReview, SymptomReview } from '../types';

interface SelectableProps {
  label: string;
  selected: boolean;
  onToggle: () => void;
  accessibilityHint?: string;
  children?: ReactNode;
}

/**
 * The shared shell: a checkbox, a label, and whatever detail a caller adds.
 *
 * `accessibilityRole="checkbox"` with `accessibilityState.checked` is what makes
 * "Headache, ticked" reach a screen reader, which is the requirement colour alone
 * cannot meet.
 */
export function SelectableRow({
  label,
  selected,
  onToggle,
  accessibilityHint,
  children,
}: SelectableProps) {
  const theme = useTheme();

  return (
    <Pressable
      onPress={onToggle}
      accessibilityRole="checkbox"
      accessibilityLabel={label}
      accessibilityState={{ checked: selected }}
      accessibilityHint={accessibilityHint}
      style={({ pressed }) => ({
        minHeight: minTouchTarget,
        flexDirection: 'row',
        alignItems: 'flex-start',
        gap: spacing.sm,
        padding: spacing.md,
        borderRadius: radius.lg,
        borderWidth: 1,
        borderColor: selected ? theme.colors.accentStrong : theme.colors.border,
        backgroundColor: pressed ? theme.colors.surfaceSecondary : theme.colors.surface,
      })}
    >
      <Ionicons
        name={selected ? 'checkbox' : 'square-outline'}
        size={iconSize.md}
        color={selected ? theme.colors.accent : theme.colors.border}
        accessibilityElementsHidden
        importantForAccessibility="no"
      />
      <View style={{ flex: 1, gap: spacing.xxs }}>
        <AppText variant="bodyStrong">{label}</AppText>
        {children}
      </View>
    </Pressable>
  );
}

interface SymptomSelectionCardProps {
  review: SymptomReview;
  selected: boolean;
  onToggle: () => void;
  /** Which of this symptom's notes are ticked (PRD 7, section 16). */
  selectedNoteIds: string[];
  onToggleNote: (entryId: string) => void;
}

/**
 * One symptom, with its counts and its notes (PRD 7, sections 15 and 16).
 *
 * The notes are separately tickable because PRD 7 section 16 says "selected
 * notes": somebody's own words about a symptom are theirs to offer, and including
 * them by default would put a private sentence in a document without being asked.
 */
export function SymptomSelectionCard({
  review,
  selected,
  onToggle,
  selectedNoteIds,
  onToggleNote,
}: SymptomSelectionCardProps) {
  const lines = symptomReviewLines(review);
  const site = review.bodySite ? ` (${review.bodySite})` : '';

  return (
    <View style={{ gap: spacing.xs }}>
      <SelectableRow
        label={`${review.name}${site}`}
        selected={selected}
        onToggle={onToggle}
        accessibilityHint="Includes this symptom in the summary"
      >
        <AppText variant="body" tone="secondary">
          {lines.join(' · ')}
        </AppText>
        {review.firstNoticedLabel ? (
          <AppText variant="caption" tone="secondary">
            {`First noticed: ${review.firstNoticedLabel}`}
          </AppText>
        ) : null}
      </SelectableRow>

      {selected && review.notes.length > 0 ? (
        <View style={{ paddingLeft: spacing.lg, gap: spacing.xs }}>
          <AppText variant="caption" tone="secondary">
            Your own words — tick any to include
          </AppText>
          {review.notes.map((note) => (
            <SelectableRow
              key={note.entryId}
              label={note.text}
              selected={selectedNoteIds.includes(note.entryId)}
              onToggle={() => onToggleNote(note.entryId)}
              accessibilityHint="Quotes this note in the summary"
            />
          ))}
        </View>
      ) : null}
    </View>
  );
}

interface MedicationSelectionCardProps {
  review: MedicationReview;
  selected: boolean;
  onToggle: () => void;
}

/** One medication, as the report would list it (PRD 7, section 17). */
export function MedicationSelectionCard({
  review,
  selected,
  onToggle,
}: MedicationSelectionCardProps) {
  return (
    <SelectableRow
      label={review.displayName}
      selected={selected}
      onToggle={onToggle}
      accessibilityHint="Includes this medication in the summary"
    >
      <AppText variant="body" tone="secondary">
        {review.frequency ?? 'How often is not recorded'}
      </AppText>
      {review.reason ? (
        <AppText variant="caption" tone="secondary">
          {`For: ${review.reason}`}
        </AppText>
      ) : null}
    </SelectableRow>
  );
}

interface ReportSectionToggleProps {
  label: string;
  description?: string;
  selected: boolean;
  onToggle: () => void;
}

/** One of the report's section switches (PRD 7, section 25). */
export function ReportSectionToggle({
  label,
  description,
  selected,
  onToggle,
}: ReportSectionToggleProps) {
  return (
    <SelectableRow
      label={label}
      selected={selected}
      onToggle={onToggle}
      accessibilityHint="Includes this section in the summary"
    >
      {description ? (
        <AppText variant="caption" tone="secondary">
          {description}
        </AppText>
      ) : null}
    </SelectableRow>
  );
}
