/**
 * A simulated Nura robot and backend, for exercising the provisioning flow
 * without a radio.
 *
 * The robot side follows docs/device/provisioning-protocol.md exactly: it runs
 * real SPAKE2 (role B) and really decrypts the Wi-Fi payload, so a test that
 * passes here has proven the app speaks the protocol. It lives under tests/
 * only -- the app never simulates a robot (PRD 2, section 72).
 */
import { randomBytes as nodeRandomBytes } from 'crypto';

import { utf8ToBytes } from '@noble/hashes/utils.js';

import type { BleTransport, ScanResult } from '../src/services/provisioning/bleTransport';
import {
  Command,
  PairingMessage,
  PairingResult,
  ProvisioningError,
  ProvisioningState,
  UUIDS,
  type ProvisioningErrorName,
  type ProvisioningStateName,
} from '../src/services/provisioning/protocol';
import {
  computePB,
  constantTimeEqual,
  keySchedule,
  passwordScalar,
  scalarFromRandomBytes,
  sharedPointForB,
} from '../src/services/provisioning/spake2';
import {
  decryptWifiConfig,
  deriveWifiKey,
  type WifiConfig,
} from '../src/services/provisioning/wifiPayload';
import type {
  DeviceStatus,
  ProvisioningSession,
  ProvisioningSessionStatus,
} from '../src/types/device';

export const randomBytes = (length: number) => new Uint8Array(nodeRandomBytes(length));

export const HARDWARE_ID = 'NURA-3C84279A1B2C';
export const PERIPHERAL_ID = 'AA:BB:CC:DD:1B:2C';

export type WifiBehaviour =
  | 'joins'
  | { fail: ProvisioningErrorName }
  | 'joinsThenDropsBle';

type Listener = (value: Uint8Array) => void;

const tick = () => new Promise((resolve) => setTimeout(resolve, 1));

export class FakeBackend {
  sessions = new Map<string, { hardwareId: string; claimedDeviceId: string | null }>();
  createCalls = 0;
  /** Whether the robot's heartbeat reaches the backend after it claims. */
  heartbeats = true;
  createError: unknown = null;
  private counter = 0;

  async createSession(hardwareId: string): Promise<ProvisioningSession> {
    this.createCalls += 1;
    if (this.createError) throw this.createError;
    this.counter += 1;
    const id = `session-${this.counter}`;
    this.sessions.set(id, { hardwareId, claimedDeviceId: null });
    return {
      id,
      hardwareId,
      provisioningToken: `npt_token_${this.counter}`,
      expiresAt: new Date(Date.now() + 600_000).toISOString(),
      deviceApiBaseUrl: 'http://192.168.1.20:8000',
    };
  }

  /** What the robot does over Wi-Fi: POST /devices/claim. */
  claim(token: string): boolean {
    const id = `session-${token.replace('npt_token_', '')}`;
    const session = this.sessions.get(id);
    if (!session) return false;
    session.claimedDeviceId = 'device-1';
    return true;
  }

  async fetchSession(sessionId: string): Promise<ProvisioningSessionStatus> {
    const session = this.sessions.get(sessionId);
    if (!session) throw new Error('unknown session');
    return {
      id: sessionId,
      hardwareId: session.hardwareId,
      state: session.claimedDeviceId ? 'claimed' : 'pending',
      expiresAt: new Date(Date.now() + 600_000).toISOString(),
      deviceId: session.claimedDeviceId,
    };
  }

  async fetchDeviceStatus(deviceId: string): Promise<DeviceStatus> {
    return {
      deviceId,
      connectionStatus: this.heartbeats ? 'online' : 'unknown',
      lastSeenAt: this.heartbeats ? new Date().toISOString() : null,
      checkedInSinceClaim: this.heartbeats,
      onlineThresholdSeconds: 90,
      provisioningStatus: 'claimed',
      firmwareVersion: '0.1.0',
      setupCompleted: false,
      introductionPending: false,
    };
  }
}

export class FakeRobot implements BleTransport {
  code = '482731';
  connectFailures = 0;
  wifiBehaviour: WifiBehaviour = 'joins';
  deviceInfo: Record<string, unknown> = {
    protocol: 1,
    hardware_id: HARDWARE_ID,
    model: 'Nura',
    firmware_version: '0.1.0',
    provisioned: false,
    registered: false,
  };
  scanResults: ScanResult[] = [
    { id: PERIPHERAL_ID, name: 'Nura-1B2C', rssi: -52, serviceUuids: [UUIDS.service] },
  ];

  // Observable facts for assertions.
  verified = false;
  configWritesBeforeVerification = 0;
  receivedConfigs: WifiConfig[] = [];
  commands: number[] = [];
  connectCalls = 0;

  private connected = false;
  private listeners = new Map<string, Listener>();
  private disconnectListeners = new Set<() => void>();
  private pending: { pA: Uint8Array; cA: Uint8Array; ke: Uint8Array } | null = null;
  private wifiKey: Uint8Array | null = null;
  private staged: WifiConfig | null = null;

  constructor(private readonly backend: FakeBackend) {}

  async adapterState() {
    return 'on' as const;
  }

  async requestEnable() {
    return true;
  }

  async scan(_seconds: number, onResult: (result: ScanResult) => void) {
    for (const result of this.scanResults) onResult(result);
  }

  async stopScan() {}

  async connect() {
    this.connectCalls += 1;
    if (this.connectFailures > 0) {
      this.connectFailures -= 1;
      throw new Error('GATT 133');
    }
    this.connected = true;
  }

  async disconnect() {
    if (!this.connected) return;
    this.dropConnection();
  }

  /** Simulates the link dropping on the robot's side. */
  dropConnection() {
    this.connected = false;
    this.verified = false;
    this.wifiKey = null;
    for (const listener of this.disconnectListeners) listener();
  }

  async read(_id: string, characteristic: string) {
    if (characteristic === UUIDS.deviceInfo) {
      return utf8ToBytes(JSON.stringify(this.deviceInfo));
    }
    throw new Error('not readable');
  }

  async subscribe(_id: string, characteristic: string, listener: Listener) {
    this.listeners.set(characteristic, listener);
    return () => this.listeners.delete(characteristic);
  }

  onDisconnect(_id: string, listener: () => void) {
    this.disconnectListeners.add(listener);
    return () => this.disconnectListeners.delete(listener);
  }

  private notify(characteristic: string, value: Uint8Array) {
    // Notifications arrive asynchronously, as they do from a real radio.
    setTimeout(() => this.listeners.get(characteristic)?.(value), 1);
  }

  private status(state: ProvisioningStateName, error: ProvisioningErrorName = 'NONE') {
    this.notify(
      UUIDS.status,
      Uint8Array.of(ProvisioningState[state], ProvisioningError[error])
    );
  }

  async write(_id: string, characteristic: string, value: Uint8Array) {
    if (!this.connected) throw new Error('not connected');
    if (characteristic === UUIDS.pairing) return this.onPairing(value);
    if (characteristic === UUIDS.wifiConfig) return this.onWifiConfig(value);
    if (characteristic === UUIDS.command) return this.onCommand(value);
    throw new Error('not writable');
  }

  private onPairing(value: Uint8Array) {
    if (value[0] === PairingMessage.PAKE_START) {
      const pA = value.slice(1);
      const w = passwordScalar(HARDWARE_ID, this.code);
      const y = scalarFromRandomBytes(randomBytes(48));
      const pB = computePB(w, y);
      const keys = keySchedule({
        idA: utf8ToBytes('nura-app'),
        idB: utf8ToBytes(HARDWARE_ID),
        pA,
        pB,
        K: sharedPointForB(w, y, pA),
        w,
        aad: utf8ToBytes('nura-provisioning-v1'),
      });
      this.pending = { pA, cA: keys.cA, ke: keys.ke };
      this.notify(UUIDS.pairing, Uint8Array.of(PairingMessage.PAKE_RESPONSE, ...pB, ...keys.cB));
      return;
    }
    if (value[0] === PairingMessage.PAKE_CONFIRM && this.pending) {
      const ok = constantTimeEqual(value.slice(1), this.pending.cA);
      if (ok) {
        this.verified = true;
        this.wifiKey = deriveWifiKey(this.pending.ke);
      }
      this.pending = null;
      this.notify(
        UUIDS.pairing,
        Uint8Array.of(
          PairingMessage.PAIRING_RESULT,
          ok ? PairingResult.VERIFIED : PairingResult.WRONG_CODE
        )
      );
    }
  }

  private onWifiConfig(value: Uint8Array) {
    if (!this.verified || !this.wifiKey) {
      this.configWritesBeforeVerification += 1;
      this.status('FAILED', 'NOT_VERIFIED');
      return;
    }
    try {
      this.staged = decryptWifiConfig(this.wifiKey, HARDWARE_ID, value);
      this.receivedConfigs.push(this.staged);
      this.status('RECEIVED_CREDENTIALS');
    } catch {
      this.status('FAILED', 'INVALID_PAYLOAD');
    }
  }

  private async onCommand(value: Uint8Array) {
    if (!this.verified) {
      this.status('FAILED', 'NOT_VERIFIED');
      return;
    }
    const command = value[0];
    this.commands.push(command ?? -1);
    if (command !== Command.CONNECT_WIFI || !this.staged) return;

    const staged = this.staged;
    const behaviour = this.wifiBehaviour;
    void (async () => {
      await tick();
      this.status('WIFI_CONNECTING');
      await tick();
      if (typeof behaviour === 'object') {
        this.status('FAILED', behaviour.fail);
        return;
      }
      this.status('WIFI_CONNECTED');
      if (behaviour === 'joinsThenDropsBle') this.dropConnection();
      await tick();
      this.status('REGISTERING');
      this.backend.claim(staged.provisioningToken);
      await tick();
      this.status('REGISTERED');
    })();
  }
}
