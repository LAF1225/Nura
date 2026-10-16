/**
 * The in-app report preview (PRD 7, sections 32, 58 and 59).
 *
 * Renders the report's **own snapshot** -- the same frozen text the PDF is made
 * from -- so what somebody approves on screen and what they export cannot
 * disagree. That is the whole reason the backend stores the finished sentences
 * rather than a query to re-run (PRD 7, section 30).
 *
 * Deliberately not a picture of a PDF page. A rasterised page cannot be read by a
 * screen reader, does not reflow at larger text sizes, and does not follow
 * Light/Dark -- all of which PRD 7 section 58 asks for. This is real text in the
 * app's own styles; the PDF has its own printable design (section 59).
 */
import { View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { Card } from '../../../components/Card';
import { useTheme } from '../../../theme';
import { spacing } from '../../../theme/tokens';
import type { ReportSection, ReportSnapshot } from '../types';

interface ReportPreviewCardProps {
  snapshot: ReportSnapshot;
  /** Set false to show only the one-page summary, leaving the appendix out. */
  showAppendix?: boolean;
}

function SectionBlock({ section }: { section: ReportSection }) {
  const theme = useTheme();

  return (
    <View style={{ gap: spacing.xs }}>
      {section.heading ? (
        <AppText variant="bodyStrong" accessibilityRole="header">
          {section.heading}
        </AppText>
      ) : null}

      {section.items.map((item, index) => (
        <View key={index} style={{ gap: spacing.xxs }}>
          {item.title ? (
            <AppText variant="body" style={{ fontWeight: '600' }}>
              {item.title}
            </AppText>
          ) : null}
          {item.lines.map((line, lineIndex) => (
            <AppText
              key={lineIndex}
              variant="body"
              tone={item.title ? 'primary' : 'secondary'}
              style={{ paddingLeft: item.title ? spacing.sm : 0 }}
            >
              {item.title ? line : `• ${line}`}
            </AppText>
          ))}
        </View>
      ))}

      <View style={{ height: 1, backgroundColor: theme.colors.border }} />
    </View>
  );
}

export function ReportPreviewCard({
  snapshot,
  showAppendix = true,
}: ReportPreviewCardProps) {
  const appendix = showAppendix ? snapshot.appendixSections : [];

  return (
    <Card style={{ gap: spacing.md }}>
      <View style={{ gap: spacing.xxs }}>
        <AppText variant="heading" accessibilityRole="header">
          {snapshot.title}
        </AppText>
        {snapshot.header.patient ? (
          <AppText variant="bodyStrong">{snapshot.header.patient}</AppText>
        ) : null}
        {snapshot.header.lines.map((line, index) => (
          <AppText key={index} variant="body" tone="secondary">
            {line}
          </AppText>
        ))}
        {snapshot.period.note ? (
          <AppText variant="body" tone="secondary">
            {snapshot.period.note}
          </AppText>
        ) : null}
      </View>

      {snapshot.summarySections.map((section) => (
        <SectionBlock key={section.key} section={section} />
      ))}

      {appendix.map((section) => (
        <SectionBlock key={section.key} section={section} />
      ))}

      <View style={{ gap: spacing.xxs }}>
        {snapshot.footerLines.map((line, index) => (
          <AppText key={index} variant="caption" tone="secondary">
            {line}
          </AppText>
        ))}
      </View>
    </Card>
  );
}
