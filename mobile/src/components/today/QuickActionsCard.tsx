/**
 * Shortcuts to things a page or two away (PRD 3, section 22).
 *
 * Off by default, and short on purpose. "Check in" is not here: the check-in
 * card is on the same screen, and a shortcut to something already visible is
 * clutter. Nothing to do with symptoms, medication, monitoring or medical
 * advice appears until those features exist.
 */
import { useRouter } from 'expo-router';

import { spacing } from '../../theme/tokens';
import type { TodayDevice } from '../../types/today';
import { AppText } from '../AppText';
import { ListGroup, ListRow } from '../List';

interface QuickActionsCardProps {
  device: TodayDevice | null;
}

export function QuickActionsCard({ device }: QuickActionsCardProps) {
  const router = useRouter();

  return (
    <>
      <AppText variant="bodyStrong" style={{ marginBottom: spacing.xs }}>
        Quick actions
      </AppText>
      <ListGroup>
        {device === null ? (
          <ListRow
            label="Connect Nura"
            description="Set up your robot when it’s ready"
            leadingIcon="hardware-chip-outline"
            showChevron
            onPress={() => router.push('/connect-device')}
          />
        ) : (
          <ListRow
            label="Nura status"
            description={device.displayName}
            leadingIcon="hardware-chip-outline"
            showChevron
            onPress={() =>
              router.push({
                pathname: '/devices/[id]',
                params: { id: device.deviceId },
              })
            }
          />
        )}
        <ListRow
          label="Customize Today"
          description="Choose which cards appear"
          leadingIcon="options-outline"
          showChevron
          onPress={() => router.push('/customize-today')}
        />
      </ListGroup>
    </>
  );
}
