/**
 * Pairing help (PRD 2, section 20).
 *
 * Written for anyone setting Nura up -- no serial monitors or developer tools.
 * Developer diagnostics live in firmware/xiao_esp32s3/README.md instead.
 */
import { View } from 'react-native';

import { AppText, Card, Screen } from '../../src/components';
import { spacing } from '../../src/theme/tokens';

const SECTIONS: { title: string; steps: string[] }[] = [
  {
    title: 'Nura isn’t appearing',
    steps: [
      'Check Nura is plugged in and powered on.',
      'Move your phone close to Nura.',
      'Make sure Nura is in pairing mode. A new Nura shows a short code like “Nura-1B2C” on its screen. An already set-up Nura needs its button held for 3 seconds.',
      'Turn Bluetooth off and on again on your phone.',
      'Restart Nura by unplugging it for a few seconds.',
      'Close and reopen the Nura app, then search again.',
    ],
  },
  {
    title: 'The code doesn’t work',
    steps: [
      'Enter the 6 digits exactly as Nura’s screen shows them.',
      'Codes change every couple of minutes. If it changed, use the new one.',
      'Check the four characters in the app match the ones on Nura, in case another Nura is nearby.',
    ],
  },
  {
    title: 'Nura won’t join Wi-Fi',
    steps: [
      'Check the Wi-Fi password — it’s case-sensitive.',
      'Nura needs a 2.4 GHz network. Most home routers provide one alongside 5 GHz.',
      'Networks that ask you to sign in on a web page, like some hotels, won’t work.',
      'Move Nura closer to your router for setup.',
    ],
  },
  {
    title: 'Nura is offline',
    steps: [
      'Check your home internet is working on another device.',
      'If you changed your Wi-Fi name or password, hold Nura’s button for 3 seconds and choose Reconnect in the app.',
      'Being offline doesn’t unlink Nura from your account.',
    ],
  },
];

export default function PairingHelpScreen() {
  return (
    <Screen>
      <View style={{ gap: spacing.md }}>
        {SECTIONS.map((section) => (
          <Card key={section.title} style={{ gap: spacing.xs }}>
            <AppText variant="heading" accessibilityRole="header">
              {section.title}
            </AppText>
            {section.steps.map((step) => (
              <AppText key={step} variant="body" tone="secondary">
                • {step}
              </AppText>
            ))}
          </Card>
        ))}
      </View>
    </Screen>
  );
}
