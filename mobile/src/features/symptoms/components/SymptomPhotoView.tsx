/**
 * A stored symptom photo, fetched with the user's own token (PRD 6, s32 and 63).
 *
 * There is no public URL and no signed one. The image source is the API route
 * plus an Authorization header, so the backend re-checks the profile, the episode,
 * the entry and the photo before it serves a byte -- and a URL that leaked into a
 * log or a screenshot would be useless to whoever found it.
 *
 * Nothing here looks at the image. It is displayed, and it can be deleted
 * (PRD 6, sections 32 and 35).
 */
import { Alert, Image, Pressable, View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { useTheme } from '../../../theme';
import { radius, spacing } from '../../../theme/tokens';
import { DELETE_PHOTO_BODY, DELETE_PHOTO_TITLE } from '../copy';
import { useSymptomPhotoSource } from '../hooks';
import type { SymptomPhoto } from '../types';

interface SymptomPhotoViewProps {
  episodeId: string;
  photo: SymptomPhoto;
  /** Square edge in points. The thumbnail size on a history row. */
  size?: number;
  onRemove?: (photoId: string) => void;
  onPress?: () => void;
  index?: number;
}

export function SymptomPhotoView({
  episodeId,
  photo,
  size = 76,
  onRemove,
  onPress,
  index = 0,
}: SymptomPhotoViewProps) {
  const theme = useTheme();
  const source = useSymptomPhotoSource(episodeId, photo.entryId, photo.id);

  const frame = {
    width: size,
    height: size,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surfaceSecondary,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
  };

  const confirmRemove = () => {
    if (onRemove === undefined) return;
    Alert.alert(DELETE_PHOTO_TITLE, DELETE_PHOTO_BODY, [
      { text: 'Keep it', style: 'cancel' },
      { text: 'Remove', style: 'destructive', onPress: () => onRemove(photo.id) },
    ]);
  };

  const image =
    source.data == null ? (
      <View style={frame}>
        {/* Not an error: the token is still being read, or the user has just
            signed out. A placeholder is honest; a broken-image icon is not. */}
        <AppText variant="caption" tone="secondary">
          Photo
        </AppText>
      </View>
    ) : (
      <Image
        source={{ uri: source.data.uri, headers: source.data.headers }}
        style={frame}
        accessibilityIgnoresInvertColors
      />
    );

  const label = `Photo ${index + 1}`;

  if (onPress === undefined && onRemove === undefined) {
    return (
      <View accessible accessibilityLabel={label}>
        {image}
      </View>
    );
  }

  return (
    <Pressable
      onPress={onPress ?? confirmRemove}
      onLongPress={onRemove === undefined ? undefined : confirmRemove}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={
        onPress === undefined ? 'Removes this photo' : 'Opens this photo, larger'
      }
      style={{ gap: spacing.xxs }}
    >
      {image}
    </Pressable>
  );
}
