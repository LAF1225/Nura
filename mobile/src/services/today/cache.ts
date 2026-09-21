/**
 * The last Today the backend gave us (PRD 3, sections 26 and 30).
 *
 * So that a phone with no signal still shows the user their day -- their
 * check-in, their card layout -- instead of an error where the screen used to
 * be. It is a *display* cache and nothing more: it is never written back, and
 * it never decides anything.
 *
 * One deliberate limit. A cached summary is only used for the day it was
 * fetched on. Yesterday's check-in shown as today's would be a lie, and a
 * wrong answer is worse than an honest blank.
 *
 * The robot's status is the other thing this cannot honestly carry, so the
 * screen suppresses it: offline, we genuinely do not know whether Nura is
 * connected, and saying "Online" from a cached value would break the rule that
 * presence only ever comes from the backend.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import type { TodaySummary } from '../../types/today';
import { parseTodaySummary } from '../api/today';

const STORAGE_KEY = 'nura.today.lastSummary';

/**
 * Stored in wire format rather than as the parsed model, so the same
 * validation runs on the way back out. A value written by an older build that
 * no longer parses is dropped rather than trusted.
 */
export async function saveTodaySnapshot(raw: unknown): Promise<void> {
  try {
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(raw));
  } catch {
    // A cache that cannot be written is not worth failing a request over.
  }
}

export async function loadTodaySnapshot(): Promise<TodaySummary | null> {
  try {
    const stored = await AsyncStorage.getItem(STORAGE_KEY);
    if (!stored) return null;
    return parseTodaySummary(JSON.parse(stored));
  } catch {
    return null;
  }
}

export async function clearTodaySnapshot(): Promise<void> {
  await AsyncStorage.removeItem(STORAGE_KEY);
}
