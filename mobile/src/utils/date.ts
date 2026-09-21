/**
 * The user's day, and how to greet them in it (PRD 3, sections 39 and 40).
 *
 * Both functions read the *device's* clock deliberately. Someone checking in
 * at 11pm in Karachi means that day, not the following one, so "today" is
 * computed from local time and sent to the backend rather than left for the
 * server to guess from UTC.
 */

/** `YYYY-MM-DD` for a date, in the device's own time zone. */
export function localDateString(date: Date = new Date()): string {
  // Built by hand from the local parts. `toISOString()` would convert to UTC
  // first, which is exactly the bug this function exists to avoid: at 11pm in
  // Karachi it returns tomorrow's date.
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export type Greeting = 'Good morning' | 'Good afternoon' | 'Good evening';

/**
 * Time-of-day greeting (PRD 3, section 40).
 *
 *   05:00-11:59  Good morning
 *   12:00-16:59  Good afternoon
 *   17:00-04:59  Good evening
 *
 * The small hours are evening rather than morning: someone awake at 2am is
 * still in their night, and "Good morning" at that hour reads as a machine
 * that has not noticed.
 */
export function greetingForHour(hour: number): Greeting {
  if (hour >= 5 && hour < 12) return 'Good morning';
  if (hour >= 12 && hour < 17) return 'Good afternoon';
  return 'Good evening';
}

/**
 * "Good morning, Safdar" -- or just "Good morning" when there is no name yet.
 *
 * The name is never invented or substituted with an email address: a greeting
 * addressed to `person@example.com` is worse than one with no name at all
 * (PRD 3, section 8).
 */
export function greetingFor(preferredName: string | null | undefined, date = new Date()) {
  const greeting = greetingForHour(date.getHours());
  const name = preferredName?.trim();
  return name ? `${greeting}, ${name}` : greeting;
}

/** Initials for the profile button, e.g. "Safdar Ali" -> "SA". Empty if none. */
export function initialsFor(preferredName: string | null | undefined): string {
  const words = (preferredName ?? '').trim().split(/\s+/).filter(Boolean);
  return words
    .slice(0, 2)
    .map((word) => [...word][0]?.toUpperCase() ?? '')
    .join('');
}
