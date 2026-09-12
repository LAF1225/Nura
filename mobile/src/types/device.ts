/**
 * A Nura robot paired to the account (PRD 0, section 17).
 *
 * Identity rules that later PRDs depend on:
 *  - `id` is an internal UUID issued by the backend. It is the stable identity.
 *  - `hardwareId` is provisioned on the device itself and is what BLE
 *    discovery reports; it is never used as the primary key.
 *  - `displayName` is user-facing and editable ("Bedroom Nura"). It must never
 *    be treated as identity, and it is not the user's own name.
 */
export interface Device {
  id: string;
  hardwareId: string;
  displayName: string;
  deviceType: string;
  firmwareVersion: string | null;
  lastSeenAt: string | null;
  createdAt: string;
  updatedAt: string;
}
