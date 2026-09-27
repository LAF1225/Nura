/**
 * Picking and preparing a symptom photo (PRD 6, sections 31, 32, 34 and 60).
 *
 * Two things this module does, and one it very deliberately does not.
 *
 * It **asks for the narrowest permission that works** and only at the moment the
 * user taps Add a photo, so the prompt arrives with an obvious reason. Declining
 * is handled honestly: the symptom still saves, and only the photo is missing.
 *
 * It **compresses before uploading** (PRD 6, section 34). A modern phone camera
 * produces 4-8MB files; a symptom photo does not need to be one, and sending
 * full-resolution images of somebody's skin over a mobile connection is both slow
 * and more data leaving the phone than necessary.
 *
 * It **does not look at the image** (PRD 6, section 32). There is no
 * classification, no wound assessment, no rash identification. The only thing
 * read from a photo here is its size in bytes.
 */
import * as ImageManipulator from 'expo-image-manipulator';
import * as ImagePicker from 'expo-image-picker';

import { createLogger } from '../../utils/logger';
import { newClientId } from './draft';
import type { LocalPhotoDraft, PhotoContentType } from './types';

const log = createLogger('symptoms');

/**
 * The longest edge a stored symptom photo has.
 *
 * Generous enough to see a rash or a swelling clearly, small enough to upload on
 * a poor connection. Nothing in Nura examines the result, so this is about the
 * user being able to see it and show it to somebody.
 */
export const MAX_DIMENSION = 1600;

/** JPEG quality. 0.7 is visually clean at this size and roughly a fifth of the bytes. */
export const COMPRESSION_QUALITY = 0.7;

/** Mirrors the server's `max_photo_bytes`, so a refusal is caught before upload. */
export const MAX_PHOTO_BYTES = 6 * 1024 * 1024;

/** Mirrors the server's `max_photos_per_entry` (PRD 6, section 31). */
export const MAX_PHOTOS_PER_ENTRY = 5;

export type PickOutcome =
  | { kind: 'picked'; photo: LocalPhotoDraft }
  /** The user closed the picker. Not an error and not worth saying anything about. */
  | { kind: 'cancelled' }
  /** Permission was refused. The symptom still saves without a photo. */
  | { kind: 'denied'; source: 'camera' | 'library' }
  | { kind: 'tooLarge' }
  | { kind: 'failed' };

/**
 * Compresses whatever was picked and describes it as a draft photo.
 *
 * Always JPEG: it is accepted everywhere, it compresses well, and normalising
 * here means a HEIC from an iPhone and a PNG from a screenshot arrive as the
 * same thing rather than as three upload paths.
 */
async function prepare(uri: string): Promise<LocalPhotoDraft | 'tooLarge'> {
  const context = ImageManipulator.ImageManipulator.manipulate(uri);
  context.resize({ width: MAX_DIMENSION });
  const image = await context.renderAsync();
  const saved = await image.saveAsync({
    compress: COMPRESSION_QUALITY,
    format: ImageManipulator.SaveFormat.JPEG,
  });

  const byteSize = await fileSize(saved.uri);
  if (byteSize > MAX_PHOTO_BYTES) return 'tooLarge';

  return {
    // Generated now, before any upload is attempted, so the id survives a
    // failure and a retry replaces nothing (PRD 6, section 61).
    clientPhotoId: newClientId('photo'),
    localUri: saved.uri,
    contentType: 'image/jpeg' as PhotoContentType,
    byteSize,
  };
}

/**
 * How big a local file is.
 *
 * Read by fetching the file URI, which is the one way that works on both
 * platforms without a filesystem dependency. A failure here is not fatal: the
 * server checks the size too, so an unknown size is reported as zero and the
 * upload is allowed to try.
 */
async function fileSize(uri: string): Promise<number> {
  try {
    const response = await fetch(uri);
    const blob = await response.blob();
    return blob.size;
  } catch {
    return 0;
  }
}

/** Takes a photo with the camera (PRD 6, section 31). */
export async function takePhoto(): Promise<PickOutcome> {
  const permission = await ImagePicker.requestCameraPermissionsAsync();
  if (!permission.granted) return { kind: 'denied', source: 'camera' };

  try {
    const result = await ImagePicker.launchCameraAsync({
      mediaTypes: ['images'],
      quality: 1,
      // No editing step: cropping a symptom photo is not something Nura should
      // be steering, and the extra screen is one more thing in the way.
      allowsEditing: false,
      exif: false,
    });
    return await outcomeFor(result);
  } catch {
    log.warn('could not open the camera');
    return { kind: 'failed' };
  }
}

/** Chooses an existing photo (PRD 6, section 31). */
export async function pickPhoto(): Promise<PickOutcome> {
  const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
  if (!permission.granted) return { kind: 'denied', source: 'library' };

  try {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 1,
      allowsEditing: false,
      // Location and camera metadata are stripped: a symptom photo does not
      // need to carry where it was taken (PRD 6, section 62).
      exif: false,
    });
    return await outcomeFor(result);
  } catch {
    log.warn('could not open the photo library');
    return { kind: 'failed' };
  }
}

async function outcomeFor(result: ImagePicker.ImagePickerResult): Promise<PickOutcome> {
  if (result.canceled) return { kind: 'cancelled' };
  const asset = result.assets[0];
  if (asset === undefined) return { kind: 'cancelled' };

  try {
    const prepared = await prepare(asset.uri);
    if (prepared === 'tooLarge') return { kind: 'tooLarge' };
    // The URI is never logged: a photo path is as sensitive as what is in it
    // (PRD 6, section 62).
    log.info('a symptom photo was attached');
    return { kind: 'picked', photo: prepared };
  } catch {
    log.warn('could not prepare a symptom photo');
    return { kind: 'failed' };
  }
}

/** What to say when a pick did not produce a photo. Null for a plain cancel. */
export function pickMessage(outcome: PickOutcome): string | null {
  switch (outcome.kind) {
    case 'picked':
    case 'cancelled':
      return null;
    case 'denied':
      return outcome.source === 'camera'
        ? 'Nura needs permission to use the camera. You can still save this symptom without a photo.'
        : 'Nura needs permission to see your photos. You can still save this symptom without a photo.';
    case 'tooLarge':
      return 'That photo is too large to attach. Try taking a new one.';
    case 'failed':
      return 'Nura could not attach that photo. Please try again.';
  }
}
