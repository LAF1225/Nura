/**
 * Form validation (PRD 1, sections 37 and 54).
 */
import {
  MIN_PASSWORD_LENGTH,
  toE164,
  validateEmail,
  validateOtp,
  validatePassword,
  validatePasswordConfirmation,
  validatePhoneNumber,
  validatePreferredName,
} from '../src/utils/validation';

describe('email validation', () => {
  it.each(['person@example.com', 'a.b+tag@sub.domain.co.uk'])('accepts %s', (value) => {
    expect(validateEmail(value)).toBeNull();
  });

  it.each([
    '',
    '   ',
    'person',
    'person@',
    '@example.com',
    'person@example',
    'a b@c.com',
  ])('rejects %p', (value) => {
    expect(validateEmail(value)).toBeTruthy();
  });

  it('ignores surrounding whitespace', () => {
    expect(validateEmail('  person@example.com  ')).toBeNull();
  });
});

describe('password validation', () => {
  it('states the requirement rather than just refusing', () => {
    const message = validatePassword('short');
    expect(message).toContain(String(MIN_PASSWORD_LENGTH));
  });

  it('accepts a password of the minimum length', () => {
    expect(validatePassword('a'.repeat(MIN_PASSWORD_LENGTH))).toBeNull();
  });

  it('checks the confirmation matches', () => {
    expect(validatePasswordConfirmation('password123', 'password123')).toBeNull();
    expect(validatePasswordConfirmation('password123', 'password124')).toBeTruthy();
    expect(validatePasswordConfirmation('password123', '')).toBeTruthy();
  });
});

describe('preferred name validation', () => {
  it('rejects an empty name with the PRD wording', () => {
    expect(validatePreferredName('   ')).toBe('Preferred name cannot be empty.');
  });

  it('accepts an ordinary name', () => {
    expect(validatePreferredName('Ada')).toBeNull();
  });

  it('rejects something implausibly long', () => {
    expect(validatePreferredName('a'.repeat(65))).toBeTruthy();
  });
});

describe('phone numbers', () => {
  it('builds E.164, dropping the national trunk zero', () => {
    expect(toE164('44', '07700 900123')).toBe('+447700900123');
    expect(toE164('92', '0300 1234567')).toBe('+923001234567');
    expect(toE164('1', '(555) 010-9999')).toBe('+15550109999');
  });

  it('accepts a plausible number', () => {
    expect(validatePhoneNumber('44', '07700 900123')).toBeNull();
  });

  it.each([
    ['', 'empty'],
    ['12', 'too short'],
    ['1234567890123456', 'beyond the 15-digit E.164 limit'],
  ])('rejects %p (%s)', (value) => {
    expect(validatePhoneNumber('44', value)).toBeTruthy();
  });
});

describe('one-time codes', () => {
  it('accepts six digits', () => {
    expect(validateOtp('123456')).toBeNull();
    expect(validateOtp('123 456')).toBeNull();
  });

  it.each(['', '12345', '1234567'])('rejects %p', (value) => {
    expect(validateOtp(value)).toBeTruthy();
  });
});
