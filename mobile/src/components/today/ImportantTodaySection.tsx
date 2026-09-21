/**
 * Important Today (PRD 3, sections 21, 57 and 60).
 *
 * The place medication reminders, appointments and follow-ups will surface.
 * None of those modules exists, so the list is empty and the section says so
 * in plain words. It does not invent a task to look busy, and it does not say
 * "No data" -- nothing needing attention is good news, not an absence
 * (PRD 3, section 57).
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { spacing } from '../../theme/tokens';
import type { TodayItem } from '../../types/today';
import { AppText } from '../AppText';
import { Card } from '../Card';
import { ListGroup, ListRow } from '../List';

interface ImportantTodaySectionProps {
  items: TodayItem[];
}

export function ImportantTodaySection({ items }: ImportantTodaySectionProps) {
  const router = useRouter();

  return (
    <View style={{ gap: spacing.xs }}>
      <AppText variant="bodyStrong">Today</AppText>

      {items.length === 0 ? (
        <Card>
          <AppText variant="body" tone="secondary">
            Nothing needs your attention right now.
          </AppText>
        </Card>
      ) : (
        <ListGroup>
          {items.map((item) => (
            <ListRow
              key={item.id}
              label={item.title}
              description={item.subtitle}
              showChevron={Boolean(item.actionRoute)}
              onPress={
                item.actionRoute
                  ? // Cast: routes come from the server, so expo-router's typed
                    // routes cannot check them at build time. Only items the
                    // server sends reach here, and it sends none yet.
                    () => router.push(item.actionRoute as never)
                  : undefined
              }
            />
          ))}
        </ListGroup>
      )}
    </View>
  );
}
