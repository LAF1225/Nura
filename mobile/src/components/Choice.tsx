/**
 * Controls for making a choice: a consent checkbox, a large selectable card,
 * and a preference toggle row (PRD 1, sections 16, 22, 27 and 40).
 *
 * All three announce their state to screen readers and show it with a shape,
 * not only a colour.
 */
import { Ionicons } from '@expo/vector-icons';
import type { ReactNode } from 'react';
import { Pressable, Switch, View } from 'react-native';

import { useTheme } from '../theme';
import { iconSize, minTouchTarget, radius, spacing } from '../theme/tokens';
import { AppText } from './AppText';

interface CheckboxProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  /** Optional richer label, e.g. text with an embedded link. */
  children?: ReactNode;
}

/** A single, separately-tickable acknowledgement (PRD 1, section 27). */
export function Checkbox({ label, checked, onChange, children }: CheckboxProps) {
  const theme = useTheme();

  return (
    <Pressable
      onPress={() => onChange(!checked)}
      accessibilityRole="checkbox"
      accessibilityLabel={label}
      accessibilityState={{ checked }}
      style={{
        flexDirection: 'row',
        alignItems: 'flex-start',
        gap: spacing.sm,
        minHeight: minTouchTarget,
        paddingVertical: spacing.xs,
      }}
    >
      <View
        style={{
          width: 24,
          height: 24,
          marginTop: 2,
          borderRadius: radius.sm,
          borderWidth: 2,
          borderColor: checked ? theme.colors.accentStrong : theme.colors.border,
          backgroundColor: checked ? theme.colors.accentStrong : 'transparent',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {/* A tick, so the state is visible without relying on colour. */}
        {checked ? (
          <Ionicons name="checkmark" size={16} color={theme.colors.onAccent} />
        ) : null}
      </View>

      <View style={{ flex: 1 }}>{children ?? <AppText>{label}</AppText>}</View>
    </Pressable>
  );
}

interface SelectableCardProps {
  title: string;
  description: string;
  icon?: keyof typeof Ionicons.glyphMap;
  selected: boolean;
  onPress: () => void;
}

/**
 * Large, clearly tappable card for a small set of options
 * (PRD 1, section 16: "use large, clear selectable cards").
 */
export function SelectableCard({
  title,
  description,
  icon,
  selected,
  onPress,
}: SelectableCardProps) {
  const theme = useTheme();

  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="radio"
      accessibilityLabel={title}
      accessibilityHint={description}
      accessibilityState={{ selected }}
      style={({ pressed }) => ({
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.md,
        padding: spacing.md,
        borderRadius: radius.lg,
        borderWidth: selected ? 2 : 1,
        borderColor: selected ? theme.colors.accentStrong : theme.colors.border,
        backgroundColor: pressed ? theme.colors.surfaceSecondary : theme.colors.surface,
      })}
    >
      {icon ? (
        <Ionicons
          name={icon}
          size={iconSize.lg}
          color={selected ? theme.colors.accentText : theme.colors.textSecondary}
        />
      ) : null}

      <View style={{ flex: 1, gap: spacing.xxs }}>
        <AppText variant="bodyStrong">{title}</AppText>
        <AppText variant="caption" tone="secondary">
          {description}
        </AppText>
      </View>

      {/* Selection shown by a filled check, not by the border colour alone. */}
      <Ionicons
        name={selected ? 'checkmark-circle' : 'ellipse-outline'}
        size={iconSize.md}
        color={selected ? theme.colors.accent : theme.colors.border}
      />
    </Pressable>
  );
}

interface ToggleRowProps {
  label: string;
  description?: string;
  value: boolean;
  onChange: (value: boolean) => void;
}

/** An on/off preference (PRD 1, section 22). */
export function ToggleRow({ label, description, value, onChange }: ToggleRowProps) {
  const theme = useTheme();

  return (
    <View
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.md,
        minHeight: minTouchTarget,
        paddingVertical: spacing.xs,
        paddingHorizontal: spacing.md,
      }}
    >
      <View style={{ flex: 1, gap: spacing.xxs }}>
        <AppText variant="bodyStrong">{label}</AppText>
        {description ? (
          <AppText variant="caption" tone="secondary">
            {description}
          </AppText>
        ) : null}
      </View>

      <Switch
        value={value}
        onValueChange={onChange}
        accessibilityLabel={label}
        accessibilityHint={description}
        trackColor={{ false: theme.colors.border, true: theme.colors.accent }}
        thumbColor={theme.colors.surface}
      />
    </View>
  );
}
