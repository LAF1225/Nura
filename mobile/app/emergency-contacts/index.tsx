/**
 * The emergency-contact chain (PRD 9, sections 43, 44, 45, 47, 89 and 93).
 *
 * Reordered with explicit Move up and Move down rather than drag-and-drop.
 * Section 89 allows either and says to prefer explicit controls when
 * drag-and-drop is unstable or inaccessible; for this product it is both -- a
 * long press and a steady drag is exactly what section 77's accessibility rules
 * are about, and a reorder that half-worked would leave somebody's chain in an
 * order they did not choose.
 *
 * The order sent is the list as displayed, not a set of numbers the client keeps
 * consistent: the server renumbers and its answer is written straight into the
 * cache, so the list never jumps back to the old order for a frame.
 *
 * **The sentence about what Nura does not do is not decoration.** Section 47 is
 * explicit that PRD 9 builds the chain and PRD 10 walks it. Somebody entering
 * three phone numbers has every reason to assume otherwise unless told.
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { AppText, AsyncState, Button, Card, Screen } from '../../src/components';
import { EmergencyContactRow } from '../../src/features/caregivers/components/CaregiverCards';
import {
  CONTACTS_EMPTY,
  CONTACTS_INTRO,
  CONTACTS_NOT_YET,
} from '../../src/features/caregivers/copy';
import {
  useEmergencyContacts,
  useReorderContacts,
} from '../../src/features/caregivers/hooks';
import { spacing } from '../../src/theme/tokens';

export default function EmergencyContactsScreen() {
  const router = useRouter();
  const contacts = useEmergencyContacts();
  const reorder = useReorderContacts();
  const rows = contacts.data?.contacts ?? [];

  function move(index: number, delta: number) {
    const target = index + delta;
    if (target < 0 || target >= rows.length) return;
    // The ids in the order the list is about to show them. The server renumbers
    // from this, so nothing here has to keep priorities consistent.
    const order = rows.map((contact) => contact.id);
    const moved = order[index];
    if (moved === undefined) return;
    order.splice(index, 1);
    order.splice(target, 0, moved);
    reorder.mutate(order);
  }

  return (
    <Screen
      onRefresh={() => void contacts.refetch()}
      refreshing={contacts.isRefetching && !contacts.isLoading}
    >
      <View style={{ gap: spacing.md }}>
        <AppText variant="body" tone="secondary">
          {CONTACTS_INTRO}
        </AppText>

        <Card>
          <AppText variant="body">{CONTACTS_NOT_YET}</AppText>
        </Card>

        <AsyncState
          status={contacts.isError ? 'error' : 'success'}
          error={contacts.error}
          isEmpty={rows.length === 0}
          emptyMessage={CONTACTS_EMPTY}
          loadingLabel="Loading contacts"
          onRetry={() => void contacts.refetch()}
        >
          <View style={{ gap: spacing.md }}>
            {rows.map((contact, index) => (
              <EmergencyContactRow
                key={contact.id}
                contact={contact}
                isFirst={index === 0}
                isLast={index === rows.length - 1}
                onMoveUp={() => move(index, -1)}
                onMoveDown={() => move(index, 1)}
                onPress={() => router.push(`/emergency-contacts/${contact.id}`)}
              />
            ))}
          </View>
        </AsyncState>

        <Button
          label="Add a contact"
          onPress={() => router.push('/emergency-contacts/new')}
          accessibilityHint="Opens the contact form"
        />
      </View>
    </Screen>
  );
}
