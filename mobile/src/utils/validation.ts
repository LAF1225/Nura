/**
 * Form validation (PRD 1, section 37).
 *
 * These give immediate feedback while typing. The backend and the auth
 * provider remain authoritative -- passing these checks is not a guarantee the
 * server will accept the value.
 *
 * Each function returns a message to show, or null when the value is fine.
 */

/** Minimum password length Nura asks for. Stated up front, never as a surprise. */
export const MIN_PASSWORD_LENGTH = 8;

// Deliberately permissive. Email syntax is famously hard to pin down, and an
// over-strict pattern rejects addresses that genuinely work; the real check is
// whether the provider accepts it.
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateEmail(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return 'Enter your email address.';
  }
  if (!EMAIL_PATTERN.test(trimmed)) {
    return 'That does not look like a valid email address.';
  }
  return null;
}

export function validatePassword(value: string): string | null {
  if (!value) {
    return 'Enter a password.';
  }
  if (value.length < MIN_PASSWORD_LENGTH) {
    return `Use at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  return null;
}

export function validatePasswordConfirmation(
  password: string,
  confirmation: string
): string | null {
  if (!confirmation) {
    return 'Re-enter your password.';
  }
  if (password !== confirmation) {
    return 'Those passwords do not match.';
  }
  return null;
}

export function validatePreferredName(value: string): string | null {
  if (!value.trim()) {
    return 'Preferred name cannot be empty.';
  }
  if (value.trim().length > 64) {
    return 'That name is a little too long.';
  }
  return null;
}

/**
 * Combines a dialling code and a local number into E.164, the format auth
 * providers expect (for example "+44" and "7700 900123" -> "+447700900123").
 */
export function toE164(diallingCode: string, nationalNumber: string): string {
  const digits = nationalNumber.replace(/\D/g, '').replace(/^0+/, '');
  const code = diallingCode.replace(/\D/g, '');
  return `+${code}${digits}`;
}

export function validatePhoneNumber(
  diallingCode: string,
  nationalNumber: string
): string | null {
  const digits = nationalNumber.replace(/\D/g, '').replace(/^0+/, '');
  if (!digits) {
    return 'Enter your phone number.';
  }
  // E.164 allows at most 15 digits including the country code.
  const total = diallingCode.replace(/\D/g, '').length + digits.length;
  if (digits.length < 4 || total > 15) {
    return 'That does not look like a valid phone number.';
  }
  return null;
}

/** One-time codes are six digits for every provider Nura supports. */
export function validateOtp(value: string): string | null {
  const digits = value.replace(/\D/g, '');
  if (!digits) {
    return 'Enter the code we sent you.';
  }
  if (digits.length !== 6) {
    return 'The code is 6 digits.';
  }
  return null;
}
