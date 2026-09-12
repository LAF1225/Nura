/**
 * Grouped settings rows, as used by the More and Appearance screens.
 *
 * `ListGroup` draws the card and the dividers; `ListRow` is one tappable row.
 * A row can behave either as a navigation button or as a radio option -- the
 * `role` prop sets the right accessibility semantics for each (PRD 0,
 * section 24).
 */
import { Ionicons } from '@expo/vector-icons';
import { Children, Fragment, type ReactNode } from 'react';
import { Pressable, View } from 'react-native';

import { useTheme } from '../theme';
import { iconSize, minTouchTarget, radius, spacing } from '../theme/tokens';
import { AppText } from './AppText';

export function ListGroup({ children }: { children: ReactNode }) {
  const theme = useTheme();
  const rows = Children.toArray(children);

  return (
    <View
      style={{
        backgroundColor: theme.colors.surface,
        borderRadius: radius.lg,
        borderWidth: 1,
        borderColor: theme.colors.border,
        overflow: 'hidden',
      }}
    >
      {rows.map((row, index) => (
        <Fragment key={index}>
          {index > 0 ? (
            <View
              style={{
                height: 1,
                marginLeft: spacing.md,
                backgroundColor: theme.colors.border,
              }}
            />
          ) : null}
          {row}
        </Fragment>
      ))}
    </View>
  );
}

interface ListRowProps {
  label: string;
  /** Secondary line under the label. */
  description?: string;
  /** Right-aligned secondary value. */
  value?: string;
  leadingIcon?: keyof typeof Ionicons.glyphMap;
  /** `radio` announces a selectable option; `button` announces navigation. */
  role?: 'button' | 'radio';
  /** Shows a checkmark and marks the row selected for screen readers. */
  selected?: boolean;
  showChevron?: boolean;
  onPress?: () => void;
  accessibilityHint?: string;
}

export function ListRow({
  label,
  description,
  value,
  leadingIcon,
  role = 'button',
  selected = false,
  showChevron = false,
  onPress,
  accessibilityHint,
}: ListRowProps) {
  const theme = useTheme();
  const interactive = typeof onPress === 'function';

  return (
    <Pressable
      onPress={onPress}
      disabled={!interactive}
      accessibilityRole={interactive ? role : 'text'}
      accessibilityLabel={label}
      accessibilityHint={accessibilityHint}
      accessibilityState={role === 'radio' ? { selected } : undefined}
      style={({ pressed }) => ({
        minHeight: minTouchTarget,
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.sm,
        paddingVertical: spacing.sm,
        paddingHorizontal: spacing.md,
        backgroundColor:
          pressed && interactive ? theme.colors.surfaceSecondary : 'transparent',
      })}
    >
      {leadingIcon ? (
        <Ionicons name={leadingIcon} size={iconSize.md} color={theme.colors.accent} />
      ) : null}

      <View style={{ flex: 1 }}>
        <AppText variant="bodyStrong">{label}</AppText>
        {description ? (
          <AppText variant="caption" tone="secondary">
            {description}
          </AppText>
        ) : null}
      </View>

      {value ? (
        <AppText variant="body" tone="secondary">
          {value}
        </AppText>
      ) : null}

      {/* Selection is shown with a checkmark, not colour alone. */}
      {selected ? (
        <Ionicons name="checkmark" size={iconSize.md} color={theme.colors.accent} />
      ) : null}

      {showChevron ? (
        <Ionicons
          name="chevron-forward"
          size={iconSize.md}
          color={theme.colors.textSecondary}
        />
      ) : null}
    </Pressable>
  );
}
