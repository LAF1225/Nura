/**
 * One form for six kinds of record (PRD 4, sections 29, 30 and 44).
 *
 * The section spec says what the fields are; this renders them. That is what
 * keeps a medication form and an allergy form feeling like the same product
 * rather than two questionnaires, and it means accessibility -- labels,
 * announced errors, 48 dp targets -- is got right once instead of six times.
 *
 * Presentational on purpose: the screen owns the values, and every decision
 * about what a value means lives in `form.ts`, where it can be tested without
 * rendering anything.
 */
import { Ionicons } from '@expo/vector-icons';
import { Pressable, View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { TextField } from '../../../components/TextField';
import { ToggleRow } from '../../../components/Choice';
import { useTheme } from '../../../theme';
import { iconSize, minTouchTarget, radius, spacing } from '../../../theme/tokens';
import { precisionKey, type FieldErrors } from '../form';
import type { FieldOption, FieldSpec, FormValues, SectionSpec } from '../types';

/** How an approximate date is being answered (PRD 4, section 31). */
const PRECISION_OPTIONS: FieldOption[] = [
  { value: 'exact', label: 'Exact date' },
  { value: 'year', label: 'Year only' },
  // The honest third answer. Without it, someone who does not remember has to
  // invent something or leave the whole record unsaved.
  { value: 'unknown', label: 'Not sure' },
];

interface ChoiceChipsProps {
  label: string;
  options: FieldOption[];
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

function ChoiceChips({ label, options, value, onChange, disabled }: ChoiceChipsProps) {
  const theme = useTheme();

  return (
    <View style={{ gap: spacing.xs }}>
      <AppText variant="bodyStrong">{label}</AppText>
      <View
        accessibilityRole="radiogroup"
        accessibilityLabel={label}
        style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs }}
      >
        {options.map((option) => {
          const selected = option.value === value;
          return (
            <Pressable
              key={option.value || 'none'}
              onPress={() => onChange(option.value)}
              disabled={disabled}
              accessibilityRole="radio"
              accessibilityLabel={option.label}
              accessibilityState={{ selected, disabled: Boolean(disabled) }}
              style={({ pressed }) => ({
                minHeight: minTouchTarget,
                justifyContent: 'center',
                paddingHorizontal: spacing.md,
                borderRadius: radius.pill,
                borderWidth: selected ? 2 : 1,
                borderColor: selected ? theme.colors.accentStrong : theme.colors.border,
                backgroundColor:
                  selected || pressed
                    ? theme.colors.surfaceSecondary
                    : theme.colors.surface,
                opacity: disabled ? 0.6 : 1,
              })}
            >
              <View
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: spacing.xxs,
                }}
              >
                {/* A tick as well as the border, so the selection is never
                    carried by colour alone (PRD 4, section 44). */}
                {selected ? (
                  <Ionicons
                    name="checkmark"
                    size={iconSize.sm}
                    color={theme.colors.accentText}
                  />
                ) : null}
                <AppText variant="body">{option.label}</AppText>
              </View>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

interface FieldProps {
  field: FieldSpec;
  values: FormValues;
  errors: FieldErrors;
  onChange: (key: string, value: string | boolean | null) => void;
  disabled?: boolean;
}

function asText(value: string | boolean | null | undefined): string {
  return typeof value === 'string' ? value : '';
}

function Field({ field, values, errors, onChange, disabled }: FieldProps) {
  switch (field.kind) {
    case 'switch':
      return (
        <ToggleRow
          label={field.label}
          description={field.hint}
          value={values[field.key] === true}
          onChange={(next) => onChange(field.key, next)}
        />
      );

    case 'choice':
      return (
        <ChoiceChips
          label={field.label}
          options={field.options ?? []}
          value={asText(values[field.key])}
          onChange={(next) => onChange(field.key, next)}
          disabled={disabled}
        />
      );

    case 'approximateDate': {
      const yearKey = field.yearKey ?? `${field.key}_year`;
      const precision = asText(values[precisionKey(field)]);

      return (
        <View style={{ gap: spacing.sm }}>
          <ChoiceChips
            label={field.label}
            options={PRECISION_OPTIONS}
            value={precision}
            onChange={(next) => onChange(precisionKey(field), next)}
            disabled={disabled}
          />

          {precision === 'exact' ? (
            <TextField
              label="Date"
              value={asText(values[field.key])}
              onChangeText={(next) => onChange(field.key, next)}
              placeholder="YYYY-MM-DD"
              error={errors[field.key]}
              hint={field.hint}
              editable={!disabled}
              autoCapitalize="none"
            />
          ) : null}

          {precision === 'year' ? (
            <TextField
              label="Year"
              value={asText(values[yearKey])}
              onChangeText={(next) => onChange(yearKey, next)}
              placeholder="YYYY"
              keyboardType="numeric"
              maxLength={4}
              error={errors[yearKey]}
              hint={field.hint}
              editable={!disabled}
            />
          ) : null}

          {precision === 'unknown' ? (
            <AppText variant="caption" tone="secondary">
              That’s fine — Nura will leave this blank rather than guess.
            </AppText>
          ) : null}
        </View>
      );
    }

    case 'date':
      return (
        <TextField
          label={field.label}
          value={asText(values[field.key])}
          onChangeText={(next) => onChange(field.key, next)}
          placeholder="YYYY-MM-DD"
          error={errors[field.key]}
          hint={field.hint}
          editable={!disabled}
          autoCapitalize="none"
        />
      );

    case 'longtext':
      return (
        <TextField
          label={field.label}
          value={asText(values[field.key])}
          onChangeText={(next) => onChange(field.key, next)}
          placeholder={field.placeholder}
          error={errors[field.key]}
          hint={field.hint}
          editable={!disabled}
          multiline
          numberOfLines={4}
          maxLength={field.maxLength}
        />
      );

    default:
      return (
        <TextField
          label={field.label}
          value={asText(values[field.key])}
          onChangeText={(next) => onChange(field.key, next)}
          placeholder={field.placeholder}
          error={errors[field.key]}
          hint={field.hint}
          editable={!disabled}
          maxLength={field.maxLength}
          keyboardType={field.keyboardType}
          autoCapitalize={field.keyboardType === 'email-address' ? 'none' : 'sentences'}
        />
      );
  }
}

interface RecordFormProps {
  spec: SectionSpec;
  values: FormValues;
  errors: FieldErrors;
  onChange: (key: string, value: string | boolean | null) => void;
  /** True while a save is in flight. */
  disabled?: boolean;
}

export function RecordForm({
  spec,
  values,
  errors,
  onChange,
  disabled,
}: RecordFormProps) {
  return (
    <View style={{ gap: spacing.lg }}>
      {spec.fields.map((field) => (
        <Field
          key={field.key}
          field={field}
          values={values}
          errors={errors}
          onChange={onChange}
          disabled={disabled}
        />
      ))}
    </View>
  );
}
