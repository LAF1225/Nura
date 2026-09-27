/**
 * Attaching and removing symptom photos (PRD 6, sections 31, 32, 35 and 60).
 *
 * Three things it is careful about.
 *
 * **It says what Nura does with a photo, every time.** `PHOTO_NOTICE` is on the
 * screen whenever a photo can be attached, not buried in a settings page: a
 * person photographing their own skin deserves to be told in that moment that
 * nothing is going to analyse it (PRD 6, section 32).
 *
 * **A photo that has not uploaded says so** (PRD 6, section 60). The thumbnail
 * is the local file and the label reads "Pending upload" until the backend has
 * confirmed it. Nothing here reports success early.
 *
 * **Removing asks first** (PRD 6, section 35), through the platform alert -- which
 * is also why the confirmation is testable, unlike a piece of local state.
 */
import { Alert, Image, Pressable, View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { Button } from '../../../components/Button';
import { useTheme } from '../../../theme';
import { minTouchTarget, radius, spacing } from '../../../theme/tokens';
import { DELETE_PHOTO_BODY, DELETE_PHOTO_TITLE, PENDING_PHOTO_LABEL } from '../copy';
import { PHOTO_NOTICE } from '../safetyMessages';
import { MAX_PHOTOS_PER_ENTRY } from '../photos';
import type { LocalPhotoDraft } from '../types';

const THUMBNAIL = 76;

interface PhotoAttachmentPickerProps {
  photos: LocalPhotoDraft[];
  onTakePhoto: () => void;
  onPickPhoto: () => void;
  onRemove: (clientPhotoId: string) => void;
  /** Shown under the buttons when a pick did not produce a photo. */
  message?: string | null;
  busy?: boolean;
}

export function PhotoAttachmentPicker({
  photos,
  onTakePhoto,
  onPickPhoto,
  onRemove,
  message,
  busy = false,
}: PhotoAttachmentPickerProps) {
  const theme = useTheme();
  const full = photos.length >= MAX_PHOTOS_PER_ENTRY;

  const confirmRemove = (photo: LocalPhotoDraft) => {
    Alert.alert(DELETE_PHOTO_TITLE, DELETE_PHOTO_BODY, [
      { text: 'Keep it', style: 'cancel' },
      {
        text: 'Remove',
        style: 'destructive',
        onPress: () => onRemove(photo.clientPhotoId),
      },
    ]);
  };

  return (
    <View style={{ gap: spacing.sm }}>
      <AppText variant="bodyStrong">Photos (optional)</AppText>

      {photos.length > 0 ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs }}>
          {photos.map((photo, index) => (
            <Pressable
              key={photo.clientPhotoId}
              onPress={() => confirmRemove(photo)}
              accessibilityRole="button"
              accessibilityLabel={`Photo ${index + 1}, ${PENDING_PHOTO_LABEL}`}
              accessibilityHint="Removes this photo"
              style={{ gap: spacing.xxs }}
            >
              <Image
                source={{ uri: photo.localUri }}
                style={{
                  width: THUMBNAIL,
                  height: THUMBNAIL,
                  borderRadius: radius.md,
                  borderWidth: 1,
                  borderColor: theme.colors.border,
                }}
                accessibilityIgnoresInvertColors
              />
              <AppText variant="caption" tone="secondary">
                {PENDING_PHOTO_LABEL}
              </AppText>
            </Pressable>
          ))}
        </View>
      ) : null}

      {full ? (
        <AppText variant="caption" tone="secondary">
          {`You can attach up to ${MAX_PHOTOS_PER_ENTRY} photos.`}
        </AppText>
      ) : (
        <View style={{ flexDirection: 'row', gap: spacing.xs }}>
          <Button
            label="Take a photo"
            variant="secondary"
            disabled={busy}
            onPress={onTakePhoto}
            style={{ flex: 1, minHeight: minTouchTarget }}
          />
          <Button
            label="Choose a photo"
            variant="secondary"
            disabled={busy}
            onPress={onPickPhoto}
            style={{ flex: 1, minHeight: minTouchTarget }}
          />
        </View>
      )}

      {message ? (
        <AppText variant="body" tone="secondary">
          {message}
        </AppText>
      ) : null}

      {/* Said here, where a photo is being attached, and not only in a privacy
          page nobody reads (PRD 6, section 32). */}
      <AppText variant="caption" tone="secondary">
        {PHOTO_NOTICE}
      </AppText>
    </View>
  );
}
