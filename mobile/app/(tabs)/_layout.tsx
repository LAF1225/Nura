/**
 * Bottom tab navigator for the five primary sections (PRD 0, section 8).
 *
 * Tabs are declared from `TABS` so the locked order lives in exactly one
 * place. Headers are off: each screen renders its own heading, which gives the
 * calmer, card-led layout the brand asks for.
 */
import { Ionicons } from '@expo/vector-icons';
import { Tabs } from 'expo-router';

import { TABS } from '../../src/navigation/tabs';
import { useTheme } from '../../src/theme';
import { fontSize, iconSize } from '../../src/theme/tokens';

export default function TabsLayout() {
  const theme = useTheme();

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: theme.colors.tabActive,
        tabBarInactiveTintColor: theme.colors.tabInactive,
        tabBarStyle: {
          backgroundColor: theme.colors.surface,
          borderTopColor: theme.colors.border,
        },
        tabBarLabelStyle: { fontSize: fontSize.xs },
        sceneStyle: { backgroundColor: theme.colors.background },
      }}
    >
      {TABS.map((tab) => (
        <Tabs.Screen
          key={tab.name}
          name={tab.name}
          options={{
            title: tab.title,
            tabBarIcon: ({ focused, color }) => (
              <Ionicons
                name={focused ? tab.iconActive : tab.icon}
                size={iconSize.md}
                color={color}
              />
            ),
          }}
        />
      ))}
    </Tabs>
  );
}
