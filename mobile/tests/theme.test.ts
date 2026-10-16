/**
 * Theme preference behaviour (PRD 0, section 22).
 *
 * Covers the pure resolution rules, the store transition the Appearance screen
 * drives, and that the choice actually reaches disk so it survives a restart.
 *
 * The palette reaching rendered styles is covered by themeRendering.test.tsx.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { readFileSync } from 'fs';
import { join } from 'path';

import { useAppStore } from '../src/store/appStore';
import { darkTheme, getTheme, lightTheme, resolveThemeName } from '../src/theme/themes';

const STORAGE_KEY = 'nura-app-state';

/** Zustand's persist middleware writes asynchronously. */
const flushWrites = () => new Promise((resolve) => setTimeout(resolve, 0));

describe('resolveThemeName', () => {
  it('follows the device when the preference is "system"', () => {
    expect(resolveThemeName('system', 'dark')).toBe('dark');
    expect(resolveThemeName('system', 'light')).toBe('light');
  });

  it('falls back to light when the device appearance is not usable', () => {
    expect(resolveThemeName('system', null)).toBe('light');
    expect(resolveThemeName('system', undefined)).toBe('light');
    // React Native reports this when the platform has no preference.
    expect(resolveThemeName('system', 'unspecified')).toBe('light');
  });

  it('lets an explicit choice override the device', () => {
    expect(resolveThemeName('light', 'dark')).toBe('light');
    expect(resolveThemeName('dark', 'light')).toBe('dark');
  });
});

describe('getTheme', () => {
  it('returns a distinct palette per theme, not an inversion', () => {
    expect(getTheme('light')).toBe(lightTheme);
    expect(getTheme('dark')).toBe(darkTheme);
    expect(darkTheme.colors.background).not.toBe(lightTheme.colors.background);
    // Dark mode must avoid pure black (PRD 0, section 11).
    expect(darkTheme.colors.background.toLowerCase()).not.toBe('#000000');
  });
});

describe('theme preference store', () => {
  beforeEach(() => {
    useAppStore.setState({ themePreference: 'system' });
  });

  it('defaults to following the system', () => {
    expect(useAppStore.getState().themePreference).toBe('system');
  });

  it('changes the resolved theme when the preference changes', () => {
    const { setThemePreference } = useAppStore.getState();

    setThemePreference('dark');
    expect(useAppStore.getState().themePreference).toBe('dark');
    expect(
      getTheme(resolveThemeName(useAppStore.getState().themePreference, 'light'))
    ).toBe(darkTheme);

    setThemePreference('light');
    expect(
      getTheme(resolveThemeName(useAppStore.getState().themePreference, 'dark'))
    ).toBe(lightTheme);
  });
});

describe('theme preference persistence', () => {
  it('writes the chosen preference to storage so it survives a restart', async () => {
    useAppStore.getState().setThemePreference('dark');
    await flushWrites();

    const stored = await AsyncStorage.getItem(STORAGE_KEY);
    expect(stored).toBeTruthy();
    expect(JSON.parse(stored as string).state.themePreference).toBe('dark');
  });

  it('persists only preferences -- never the auth session', async () => {
    // Tokens belong in secure storage, not AsyncStorage (PRD 0, section 18).
    useAppStore.setState({
      session: {
        userId: 'u1',
        provider: 'email',
        email: 'person@example.test',
        phone: null,
      },
    });
    useAppStore.getState().setThemePreference('light');
    await flushWrites();

    const stored = await AsyncStorage.getItem(STORAGE_KEY);
    const persisted = JSON.parse(stored as string).state;

    expect(Object.keys(persisted).sort()).toEqual([
      'lastOnboardingStatus',
      'selectedDeviceId',
      'themePreference',
    ]);
    expect(persisted).not.toHaveProperty('session');
  });
});

describe('Today, Health, medication, symptom and appointment screens take their colours from the theme', () => {
  /**
   * PRD 3 section 41, PRD 5 section 61, PRD 6 section 68 and PRD 7 section 59:
   * no colour may be written into one of these components.
   * A hex literal in one of these files is a colour that will not change when
   * the user switches to Dark, so it is caught here rather than by eye.
   *
   * `themeRendering.test.tsx` proves the other half -- that the chosen palette
   * actually reaches a rendered style.
   */
  const FILES = [
    'app/(tabs)/index.tsx',
    'app/(tabs)/health.tsx',
    'app/(tabs)/nura.tsx',
    'app/customize-today.tsx',
    'src/components/Skeleton.tsx',
    'src/components/today/DailyCheckInCard.tsx',
    'src/components/today/GreetingHeader.tsx',
    'src/components/today/ImportantTodaySection.tsx',
    'src/components/today/NuraStatusCard.tsx',
    'src/components/today/OfflineBanner.tsx',
    'src/components/today/QuickActionsCard.tsx',
    'src/components/today/registry.tsx',
    'app/health/setup.tsx',
    'app/health/blood-type.tsx',
    'app/health/[section]/index.tsx',
    'app/health/[section]/[id].tsx',
    'src/features/health/components/RecordForm.tsx',
    'src/features/health/components/Completeness.tsx',
    'src/features/health/components/HealthProfileCard.tsx',
    'app/(tabs)/care.tsx',
    'app/medications/index.tsx',
    'app/medications/schedules.tsx',
    'app/medications/history.tsx',
    'app/medications/skip.tsx',
    'app/medications/schedule/[id].tsx',
    'app/medications/supply/index.tsx',
    'app/medications/supply/[medicationId].tsx',
    'src/features/medications/components/DoseActionButtons.tsx',
    'src/features/medications/components/DoseCard.tsx',
    'src/features/medications/components/MedicationScheduleRow.tsx',
    'src/features/medications/components/MedicationSummaryCards.tsx',
    'src/features/medications/components/MedicationsTodayCard.tsx',
    'src/features/medications/components/ScheduleForm.tsx',
    'app/symptoms/index.tsx',
    'app/symptoms/log.tsx',
    'app/symptoms/talk.tsx',
    'app/symptoms/review.tsx',
    'app/symptoms/history.tsx',
    'app/symptoms/[id]/index.tsx',
    'app/symptoms/[id]/update.tsx',
    'src/features/symptoms/components/ChangeStateSelector.tsx',
    'src/features/symptoms/components/Conversation.tsx',
    'src/features/symptoms/components/PhotoAttachmentPicker.tsx',
    'src/features/symptoms/components/SafetyNotice.tsx',
    'src/features/symptoms/components/SeverityInput.tsx',
    'src/features/symptoms/components/StructuredSummary.tsx',
    'src/features/symptoms/components/SymptomCard.tsx',
    'src/features/symptoms/components/SymptomPhotoView.tsx',
    'src/features/symptoms/components/SymptomTimelineRow.tsx',
    'src/features/symptoms/components/SymptomsTodayCard.tsx',
    'app/appointments/index.tsx',
    'app/appointments/new.tsx',
    'app/appointments/[id]/index.tsx',
    'app/appointments/[id]/edit.tsx',
    'app/appointments/[id]/prepare.tsx',
    'app/appointments/[id]/questions.tsx',
    'app/appointments/[id]/select.tsx',
    'app/appointments/[id]/preview.tsx',
    'app/appointments/[id]/reports.tsx',
    'src/features/appointments/components/AppointmentForm.tsx',
    'src/features/appointments/components/AppointmentRow.tsx',
    'src/features/appointments/components/AppointmentsTodayCard.tsx',
    'src/features/appointments/components/PreparationProgress.tsx',
    'src/features/appointments/components/QuestionList.tsx',
    'src/features/appointments/components/ReportPreviewCard.tsx',
    'src/features/appointments/components/SelectionCards.tsx',
    'app/(tabs)/nura.tsx',
    'app/nura/[id].tsx',
    'app/nura/history.tsx',
    'app/nura/instructions.tsx',
    'app/nura/memory.tsx',
    'app/nura/personality.tsx',
    'app/nura/proactivity.tsx',
    'app/nura/voice.tsx',
    'src/features/nura/components/AssistantTypingIndicator.tsx',
    'src/features/nura/components/Banners.tsx',
    'src/features/nura/components/ChatBubble.tsx',
    'src/features/nura/components/ConversationComposer.tsx',
    'src/features/nura/components/MemoryCards.tsx',
    'src/features/nura/components/PendingActionCard.tsx',
    'src/features/nura/components/PreferenceChoice.tsx',
    'src/features/nura/components/ProactivePromptCard.tsx',
    'app/caregivers/index.tsx',
    'app/caregivers/invite.tsx',
    'app/caregivers/[id].tsx',
    'app/caregivers/accept.tsx',
    'app/caregivers/notifications.tsx',
    'app/caregivers/requests/index.tsx',
    'app/caregivers/requests/[id].tsx',
    'app/care-mode/index.tsx',
    'app/care-mode/profiles.tsx',
    'app/care-mode/suggest.tsx',
    'app/care-mode/notifications.tsx',
    'app/family/index.tsx',
    'app/family/[threadId].tsx',
    'app/emergency-contacts/index.tsx',
    'app/emergency-contacts/[id].tsx',
    'src/features/caregivers/components/CaregiverCards.tsx',
    'src/features/caregivers/components/CareRequestsTodayCard.tsx',
    // PRD 10, section 119: every safety screen supports Light/Dark/System,
    // which here means none of them names a colour. Section 118 adds that no
    // status may be carried by colour alone -- the safety screens say every
    // state in words, so there is nothing for a palette to encode.
    'app/safety/index.tsx',
    'app/safety/start.tsx',
    'app/safety/check.tsx',
    'app/safety/emergency.tsx',
    'app/safety/history.tsx',
    'app/safety/capabilities.tsx',
    'app/safety/[eventId].tsx',
    'app/care-mode/safety-alerts.tsx',
    'src/features/safety/components/SafetyCards.tsx',
    // PRD 11, section 106: a serious or emergency card prioritises readability
    // over brand gradients, and section 130 asks for Light/Dark/System on the
    // device screens. Neither names a colour -- the serious variants pick a
    // *tone* rather than a value, so the palette still decides.
    'app/robot/index.tsx',
    'app/robot/capabilities.tsx',
    'app/robot/history.tsx',
    'app/robot/preview.tsx',
    'src/features/robot/components/RobotCards.tsx',
    // PRD 12's daily-life screens. The rows that carry a state do it with a
    // tone and an icon rather than a colour value, so the palette still
    // decides (section 48).
    'app/daily/index.tsx',
    'app/daily/tasks.tsx',
    'app/daily/task-form.tsx',
    'app/daily/reminders.tsx',
    'app/daily/reminder-form.tsx',
    'app/daily/alarms.tsx',
    'app/daily/alarm-form.tsx',
    'app/daily/routines.tsx',
    'app/daily/routine-form.tsx',
    'app/daily/routine/[id].tsx',
    'app/daily/run/[id].tsx',
    'app/daily/capabilities.tsx',
    'src/features/productivity/components/DailyLifeRows.tsx',
    'src/features/productivity/components/DailyLifeTodayCard.tsx',
    // PRD 13.
    'app/privacy/index.tsx',
    'app/privacy/export.tsx',
    'app/privacy/delete.tsx',
    'src/components/DegradedModeBanner.tsx',
  ];

  it.each(FILES)('%s contains no hard-coded colour', (file) => {
    const source = readFileSync(join(__dirname, '..', file), 'utf8');
    expect(source).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(source).not.toMatch(/\brgba?\(/);
  });
});
