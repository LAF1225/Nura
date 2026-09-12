/**
 * Countries, used by the phone dialling-code picker and the profile
 * country/region field (PRD 1, sections 11 and 18).
 *
 * Region limitation, stated plainly as PRD 1 section 11 asks: this is a
 * commonly-used subset, not the full ISO 3166 list. Anyone whose country is
 * missing cannot complete phone sign-up. Adding one is a single line here --
 * `code` is ISO 3166-1 alpha-2 and `dialling` is the E.164 country calling
 * code -- and nothing else needs to change.
 */

export interface Country {
  /** ISO 3166-1 alpha-2, uppercase. */
  code: string;
  name: string;
  /** E.164 country calling code, digits only. */
  dialling: string;
}

export const COUNTRIES: readonly Country[] = [
  { code: 'AE', name: 'United Arab Emirates', dialling: '971' },
  { code: 'AR', name: 'Argentina', dialling: '54' },
  { code: 'AT', name: 'Austria', dialling: '43' },
  { code: 'AU', name: 'Australia', dialling: '61' },
  { code: 'BD', name: 'Bangladesh', dialling: '880' },
  { code: 'BE', name: 'Belgium', dialling: '32' },
  { code: 'BR', name: 'Brazil', dialling: '55' },
  { code: 'CA', name: 'Canada', dialling: '1' },
  { code: 'CH', name: 'Switzerland', dialling: '41' },
  { code: 'CL', name: 'Chile', dialling: '56' },
  { code: 'CN', name: 'China', dialling: '86' },
  { code: 'CO', name: 'Colombia', dialling: '57' },
  { code: 'CZ', name: 'Czechia', dialling: '420' },
  { code: 'DE', name: 'Germany', dialling: '49' },
  { code: 'DK', name: 'Denmark', dialling: '45' },
  { code: 'EG', name: 'Egypt', dialling: '20' },
  { code: 'ES', name: 'Spain', dialling: '34' },
  { code: 'FI', name: 'Finland', dialling: '358' },
  { code: 'FR', name: 'France', dialling: '33' },
  { code: 'GB', name: 'United Kingdom', dialling: '44' },
  { code: 'GR', name: 'Greece', dialling: '30' },
  { code: 'HK', name: 'Hong Kong', dialling: '852' },
  { code: 'HU', name: 'Hungary', dialling: '36' },
  { code: 'ID', name: 'Indonesia', dialling: '62' },
  { code: 'IE', name: 'Ireland', dialling: '353' },
  { code: 'IL', name: 'Israel', dialling: '972' },
  { code: 'IN', name: 'India', dialling: '91' },
  { code: 'IT', name: 'Italy', dialling: '39' },
  { code: 'JP', name: 'Japan', dialling: '81' },
  { code: 'KE', name: 'Kenya', dialling: '254' },
  { code: 'KR', name: 'South Korea', dialling: '82' },
  { code: 'LK', name: 'Sri Lanka', dialling: '94' },
  { code: 'MA', name: 'Morocco', dialling: '212' },
  { code: 'MX', name: 'Mexico', dialling: '52' },
  { code: 'MY', name: 'Malaysia', dialling: '60' },
  { code: 'NG', name: 'Nigeria', dialling: '234' },
  { code: 'NL', name: 'Netherlands', dialling: '31' },
  { code: 'NO', name: 'Norway', dialling: '47' },
  { code: 'NP', name: 'Nepal', dialling: '977' },
  { code: 'NZ', name: 'New Zealand', dialling: '64' },
  { code: 'PH', name: 'Philippines', dialling: '63' },
  { code: 'PK', name: 'Pakistan', dialling: '92' },
  { code: 'PL', name: 'Poland', dialling: '48' },
  { code: 'PT', name: 'Portugal', dialling: '351' },
  { code: 'QA', name: 'Qatar', dialling: '974' },
  { code: 'RO', name: 'Romania', dialling: '40' },
  { code: 'SA', name: 'Saudi Arabia', dialling: '966' },
  { code: 'SE', name: 'Sweden', dialling: '46' },
  { code: 'SG', name: 'Singapore', dialling: '65' },
  { code: 'TH', name: 'Thailand', dialling: '66' },
  { code: 'TR', name: 'Türkiye', dialling: '90' },
  { code: 'TW', name: 'Taiwan', dialling: '886' },
  { code: 'TZ', name: 'Tanzania', dialling: '255' },
  { code: 'UA', name: 'Ukraine', dialling: '380' },
  { code: 'UG', name: 'Uganda', dialling: '256' },
  { code: 'US', name: 'United States', dialling: '1' },
  { code: 'VN', name: 'Vietnam', dialling: '84' },
  { code: 'ZA', name: 'South Africa', dialling: '27' },
];

export const DEFAULT_COUNTRY_CODE = 'GB';

export function findCountry(code: string | null | undefined): Country | undefined {
  if (!code) return undefined;
  const upper = code.toUpperCase();
  return COUNTRIES.find((country) => country.code === upper);
}

/**
 * The device's region if we recognise it, otherwise the default.
 * `regionCode` comes from expo-localization and may be null on some devices.
 */
export function countryForRegion(regionCode: string | null | undefined): Country {
  return findCountry(regionCode) ?? findCountry(DEFAULT_COUNTRY_CODE)!;
}
