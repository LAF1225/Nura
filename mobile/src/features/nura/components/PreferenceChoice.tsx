/**
 * A three-step preference control (PRD 8, sections 23 and 83).
 *
 * Section 62 draws sliders and section 23 allows either a 0-100 scale or
 * Low / Medium / High, asking for one consistent UI. This is that choice, and
 * the reason is accessibility rather than taste: a three-way control has 48dp
 * targets, announces its options and its selection to a screen reader, works
 * with a shaking hand, and reads the same at every type size. A 101-point
 * slider does none of those things, and the extra precision would not change
 * a single word of the prompt it feeds.
 *
 * The same control serves proactivity (four steps) and verbosity, so every
 * setting on every Nura screen works the same way.
 */
import { View } from 'react-native';

import { AppText, Button } from '../../../components';
import { spacing } from '../../../theme/tokens';

interface PreferenceChoiceProps<T extends string> {
  label: string;
  /** Quiet guidance under the label. */
  description?: string;
  options: readonly T[];
  /** Display text per option. */
  labels: Record<string, string>;
  value: T;
  onChange: (value: T) => void;
  /** What choosing an option does, for a screen reader. */
  hint?: string;
}

export function PreferenceChoice<T extends string>({
  label,
  description,
  options,
  labels,
  value,
  onChange,
  hint,
}: PreferenceChoiceProps<T>) {
  return (
    <View style={{ gap: spacing.xs }}>
      <AppText variant="bodyStrong">{label}</AppText>

      {description ? (
        <AppText variant="caption" tone="secondary">
          {description}
        </AppText>
      ) : null}

      <View style={{ flexDirection: 'row', gap: spacing.xxs }}>
        {options.map((option) => (
          <Button
            key={option}
            label={labels[option] ?? option}
            variant={option === value ? 'primary' : 'secondary'}
            onPress={() => onChange(option)}
            // The group's label is repeated per option, because a screen
            // reader reaching a lone "Medium" button has no way to know
            // which of five dials it belongs to.
            accessibilityLabel={`${label}: ${labels[option] ?? option}`}
            accessibilityHint={hint}
            style={{ flex: 1 }}
          />
        ))}
      </View>
    </View>
  );
}
