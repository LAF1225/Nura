/**
 * The draft, read back before it is saved (PRD 6, sections 30 and 76).
 *
 * The screen both flows end on, and the reason the guided conversation is safe to
 * ship at all: whatever the rules extracted, the person sees it in plain words
 * and can change any of it before anything is stored.
 *
 * Only rows with something in them are drawn, so a sparse description reads as a
 * short summary rather than a form full of blanks -- which is what makes "you can
 * leave things out" feel true rather than merely permitted (PRD 6, section 11).
 *
 * The rows that show what the user *denied* or was *unsure* about are not
 * decoration. A summary that dropped them would claim more certainty than they
 * expressed (PRD 6, section 24).
 */
import { View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { Card } from '../../../components/Card';
import { useTheme } from '../../../theme';
import { spacing } from '../../../theme/tokens';
import { summaryRows } from '../copy';
import type { SymptomDraft } from '../types';

interface StructuredSummaryProps {
  draft: SymptomDraft;
  /** The episode's name, when this is a follow-up and the draft has none. */
  heading?: string;
}

export function StructuredSummary({ draft, heading }: StructuredSummaryProps) {
  const theme = useTheme();
  const rows = summaryRows(draft);
  const title = draft.mainSymptom ?? heading ?? 'Update';

  return (
    <Card style={{ gap: spacing.sm }}>
      <AppText variant="heading" accessibilityRole="header">
        {title}
      </AppText>

      {rows.length === 0 ? (
        <AppText variant="body" tone="secondary">
          Nothing added yet.
        </AppText>
      ) : (
        <View style={{ gap: spacing.sm }}>
          {rows.map((row, index) => (
            <View
              key={row.label}
              // One accessibility element per row, so a screen reader reads
              // "How bad: 5 out of 10" rather than two disconnected strings.
              accessible
              accessibilityLabel={`${row.label}: ${row.value}`}
              style={{
                gap: spacing.xxs,
                paddingTop: index === 0 ? 0 : spacing.sm,
                borderTopWidth: index === 0 ? 0 : 1,
                borderTopColor: theme.colors.border,
              }}
            >
              <AppText variant="caption" tone="secondary">
                {row.label}
              </AppText>
              <AppText variant="body">{row.value}</AppText>
            </View>
          ))}
        </View>
      )}
    </Card>
  );
}
