/**
 * How a card is laid out on Nura's screen (PRD 11, sections 95, 37 and 106).
 *
 * Section 95 recommends a preview and is explicit about the label: **preview
 * only**. So this screen draws the eight layouts from the protocol's own
 * vocabulary with sample content, and says in its own words that it does not
 * mean the robot showed anything.
 *
 * Two things it deliberately does *not* do.
 *
 * **It does not fetch a payload.** Showing the card currently queued would be
 * more impressive and would mean the app reading a presentation the robot has
 * not been given -- which is exactly the confusion between "queued" and
 * "shown" that section 14 exists to prevent. The real queue is the history
 * screen, where every row says which it is.
 *
 * **It does not pretend to be a screen.** There is no 240x320 frame, no
 * simulated bezel and no animation. Section 62 puts simulator controls out of
 * production UI, and a convincing mock-up of hardware that does not exist is
 * the same mistake in a nicer font.
 */
import { View } from 'react-native';

import { AppText, Card, Screen } from '../../src/components';
import { PreviewCard } from '../../src/features/robot/components/RobotCards';
import * as copy from '../../src/features/robot/copy';
import { LAYOUTS } from '../../src/features/robot/protocol';
import { spacing } from '../../src/theme/tokens';

/**
 * One sample per layout, using the same vocabulary the firmware draws.
 *
 * The medication sample is the **private** one, because private is the
 * default (section 104) and a preview that showed a tablet name would be
 * teaching the wrong expectation.
 */
const SAMPLES: Record<string, { lines: string[]; serious?: boolean }> = {
  FACE: { lines: ['Nura’s face', 'Two eyes, resting'] },
  TITLE_BODY: { lines: ['Nura', 'Finish setting up in the Nura app'] },
  TITLE_VALUE: { lines: ['Next dose', '8:00 PM'] },
  REMINDER: { lines: ['Medication', 'Reminder due', 'Use the Nura app to respond.'] },
  MESSAGE: { lines: ['Message', 'Ayesha', 'Call me when you’re free.'] },
  STATUS: { lines: ['Safety Monitoring', 'ON until 10:30 PM'], serious: true },
  EMERGENCY: {
    lines: [
      'EMERGENCY MODE',
      'Nura is processing your safety request.',
      'Calling is not configured.',
    ],
    serious: true,
  },
  PAIRING_CODE: { lines: ['Pairing code', '482 731'] },
};

export default function RobotPreviewScreen() {
  return (
    <Screen>
      <AppText variant="title" accessibilityRole="header">
        {copy.PREVIEW_TITLE}
      </AppText>

      <Card
        style={{ gap: spacing.xxs, marginTop: spacing.sm }}
        accessible
        accessibilityRole="alert"
        accessibilityLabel={`Preview only. ${copy.PREVIEW_HINT}`}
      >
        <AppText variant="bodyStrong">Preview only</AppText>
        <AppText variant="body" tone="secondary">
          This is how the card would look on Nura’s screen. It does not mean the robot
          showed it.
        </AppText>
      </Card>

      <View style={{ gap: spacing.sm, marginTop: spacing.lg }}>
        <AppText variant="bodyStrong" accessibilityRole="header">
          {copy.PREVIEW_SAMPLES_TITLE}
        </AppText>
        {LAYOUTS.map((layout) => (
          <PreviewCard
            key={layout}
            layout={layout}
            lines={SAMPLES[layout]?.lines ?? []}
            serious={SAMPLES[layout]?.serious}
          />
        ))}
      </View>
    </Screen>
  );
}
