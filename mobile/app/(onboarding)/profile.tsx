/**
 * Basic profile (PRD 1, sections 18-21, and 28 for assisted setup).
 *
 * Only the essentials, and it should not feel like a hospital admission form.
 * No medical questions at all -- those come after pairing, in a later PRD.
 *
 * An age *band* is collected rather than a date of birth (PRD 1, section 20):
 * it is enough for age-appropriate behaviour without storing a precise
 * identifier.
 */
import { useRouter } from 'expo-router';
import { getLocales } from 'expo-localization';
import { useMemo, useState } from 'react';
import { View } from 'react-native';

import {
  AppText,
  Button,
  Card,
  ListGroup,
  ListRow,
  Screen,
  StepIndicator,
  TextField,
} from '../../src/components';
import { COUNTRIES, countryForRegion } from '../../src/constants/countries';
import { LANGUAGES } from '../../src/constants/languages';
import {
  useCreateProfile,
  useOnboarding,
  useUpdateOnboarding,
  useUpdateSettings,
} from '../../src/hooks/useOnboarding';
import { apiErrorMessage } from '../../src/services/api';
import { useAppStore } from '../../src/store/appStore';
import { spacing } from '../../src/theme/tokens';
import type { AgeRange } from '../../src/types/account';
import { validatePreferredName } from '../../src/utils/validation';

const AGE_RANGES: { value: AgeRange; label: string }[] = [
  { value: 'under_18', label: 'Under 18' },
  { value: '18_29', label: '18 to 29' },
  { value: '30_44', label: '30 to 44' },
  { value: '45_59', label: '45 to 59' },
  { value: '60_74', label: '60 to 74' },
  { value: '75_plus', label: '75 or older' },
  { value: 'prefer_not_to_say', label: 'Prefer not to say' },
];

type Picker = 'age' | 'language' | 'country' | null;

export default function ProfileScreen() {
  const router = useRouter();
  const onboarding = useOnboarding();
  const createProfile = useCreateProfile();
  const updateSettings = useUpdateSettings();
  const updateOnboarding = useUpdateOnboarding();

  const isAssisted = onboarding.data?.setupMode === 'assisted';

  // Apple hands over a name on first sign-in only; use it as a starting point.
  const suggestedName = useAppStore((state) => state.suggestedName);
  const deviceLocale = useMemo(() => getLocales()[0], []);

  const [name, setName] = useState(suggestedName ?? '');
  const [ageRange, setAgeRange] = useState<AgeRange | null>(null);
  const [language, setLanguage] = useState(
    () => LANGUAGES.find((l) => l.code === deviceLocale?.languageCode)?.code ?? 'en'
  );
  const [country, setCountry] = useState(
    () => countryForRegion(deviceLocale?.regionCode ?? null).code
  );
  const [pronouns, setPronouns] = useState('');
  const [picker, setPicker] = useState<Picker>(null);
  const [submitted, setSubmitted] = useState(false);

  const nameError = submitted ? validatePreferredName(name) : null;
  const busy =
    createProfile.isPending || updateSettings.isPending || updateOnboarding.isPending;
  const failure = createProfile.error ?? updateSettings.error ?? updateOnboarding.error;

  async function submit() {
    if (busy) return;
    setSubmitted(true);
    if (validatePreferredName(name)) return;

    try {
      await createProfile.mutateAsync({
        preferredName: name.trim(),
        ageRange,
        countryRegion: country,
        pronouns: pronouns.trim() || null,
        // In assisted setup the profile describes the other person, and this
        // account is their helper (PRD 1, section 34).
        role: isAssisted ? 'setup_helper' : 'self',
      });
      // Language belongs to account settings, not the profile
      // (PRD 1, section 32).
      await updateSettings.mutateAsync({ language });
      await updateOnboarding.mutateAsync({ status: 'basic_profile_complete' });
      router.push('/preferences');
    } catch {
      // Shown from the mutation error state below.
    }
  }

  if (picker) {
    const options =
      picker === 'age'
        ? AGE_RANGES.map((o) => ({
            key: o.value,
            label: o.label,
            selected: ageRange === o.value,
            pick: () => setAgeRange(o.value),
          }))
        : picker === 'language'
          ? LANGUAGES.map((l) => ({
              key: l.code,
              label: l.name,
              selected: language === l.code,
              pick: () => setLanguage(l.code),
            }))
          : COUNTRIES.map((c) => ({
              key: c.code,
              label: c.name,
              selected: country === c.code,
              pick: () => setCountry(c.code),
            }));

    const title =
      picker === 'age'
        ? 'Age range'
        : picker === 'language'
          ? 'Language'
          : 'Country or region';

    return (
      <Screen>
        <AppText variant="title" style={{ marginBottom: spacing.md }}>
          {title}
        </AppText>
        <ListGroup>
          {options.map((option) => (
            <ListRow
              key={option.key}
              label={option.label}
              role="radio"
              selected={option.selected}
              onPress={() => {
                option.pick();
                setPicker(null);
              }}
            />
          ))}
        </ListGroup>
      </Screen>
    );
  }

  const selectedAge = AGE_RANGES.find((o) => o.value === ageRange)?.label ?? 'Choose';
  const selectedLanguage = LANGUAGES.find((l) => l.code === language)?.name ?? 'English';
  const selectedCountry = COUNTRIES.find((c) => c.code === country)?.name ?? 'Choose';

  return (
    <Screen>
      <StepIndicator step={2} totalSteps={5} />

      {isAssisted ? (
        <Card style={{ marginBottom: spacing.lg, gap: spacing.sm }}>
          <AppText variant="body">
            The person using Nura should remain in control of their health information and
            permissions whenever possible.
          </AppText>
        </Card>
      ) : null}

      <AppText variant="title" style={{ marginBottom: spacing.xs }}>
        {isAssisted ? 'Who will primarily use Nura?' : 'What should Nura call you?'}
      </AppText>
      <AppText variant="body" tone="secondary" style={{ marginBottom: spacing.lg }}>
        Just the basics for now.
      </AppText>

      <View style={{ gap: spacing.md }}>
        <TextField
          label={isAssisted ? 'Their preferred name' : 'Preferred name'}
          value={name}
          onChangeText={setName}
          error={nameError}
          autoCapitalize="words"
          autoComplete="name"
        />

        <ListGroup>
          <ListRow
            label={isAssisted ? 'Their age range' : 'Age range'}
            value={selectedAge}
            showChevron
            onPress={() => setPicker('age')}
          />
          <ListRow
            label="Language"
            value={selectedLanguage}
            showChevron
            onPress={() => setPicker('language')}
          />
          <ListRow
            label="Country or region"
            value={selectedCountry}
            showChevron
            onPress={() => setPicker('country')}
          />
        </ListGroup>

        <TextField
          label="Pronouns (optional)"
          value={pronouns}
          onChangeText={setPronouns}
          hint="For example she/her, he/him or they/them."
          autoCapitalize="none"
        />
      </View>

      {failure ? (
        <Card style={{ marginTop: spacing.md }}>
          <AppText variant="body" tone="danger" accessibilityLiveRegion="polite">
            {apiErrorMessage(failure)}
          </AppText>
        </Card>
      ) : null}

      <Button
        label={busy ? 'Saving…' : 'Continue'}
        onPress={submit}
        disabled={busy}
        style={{ marginTop: spacing.xl }}
      />
    </Screen>
  );
}
