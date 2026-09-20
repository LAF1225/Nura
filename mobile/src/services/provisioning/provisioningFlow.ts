/**
 * The pairing and Wi-Fi provisioning flow (PRD 2, sections 14-36, 50-53).
 *
 * One instance drives one robot from "connect" to "online". Screens render its
 * state and call its methods; they never touch Bluetooth or cryptography
 * directly. Dependencies are injected so tests can run the whole flow against
 * a simulated robot and backend.
 *
 * Two rules this class exists to enforce:
 *
 *  - **No Wi-Fi details before verification.** The Wi-Fi key only exists
 *    after SPAKE2 has succeeded on this connection (PRD 2, section 15).
 *  - **No success without the backend.** Whatever the robot reports over BLE,
 *    `online` is reached only when the backend says the robot has checked in
 *    since its claim (PRD 2, section 36).
 */
import type {
  DeviceStatus,
  ProvisioningSession,
  ProvisioningSessionStatus,
} from '../../types/device';
import { createLogger } from '../../utils/logger';
import type { BleTransport, Unsubscribe } from './bleTransport';
import type { DiscoveredNura } from './discovery';
import {
  flowErrorForApi,
  flowErrorForRobot,
  isWifiRetryable,
  type FlowErrorKind,
} from './flowErrors';
import {
  CONNECT_TIMEOUT_MS,
  decodePairingNotification,
  decodeStatus,
  encodeCommand,
  encodePakeConfirm,
  encodePakeStart,
  MAX_FAILED_ATTEMPTS_PER_CONNECTION,
  NONCE_LENGTH,
  ONLINE_POLL_INTERVAL_MS,
  ONLINE_WAIT_TIMEOUT_MS,
  parseDeviceInfo,
  ProtocolError,
  RESPONSE_TIMEOUT_MS,
  UUIDS,
  type DeviceInfo,
  type PairingNotification,
  type RobotStatus,
} from './protocol';
import { startAppPake, WrongCodeError } from './spake2';
import { deriveWifiKey, encryptWifiConfig } from './wifiPayload';

const log = createLogger('provisioning');

export type CodeNotice = 'wrongCode' | 'codeExpired';

/** The visible stages of PRD 2 section 52, in order. */
export type ProgressStep = 'sendingWifi' | 'joiningWifi' | 'linking' | 'checking';

export type FlowState =
  | { phase: 'idle' }
  | { phase: 'connecting'; target: DiscoveredNura }
  | {
      phase: 'awaitingCode';
      info: DeviceInfo;
      notice: CodeNotice | null;
      attemptsLeft: number;
    }
  | { phase: 'verifying'; info: DeviceInfo }
  | { phase: 'awaitingWifi'; info: DeviceInfo; lastError: FlowErrorKind | null }
  | { phase: 'provisioning'; info: DeviceInfo; step: ProgressStep; bleConnected: boolean }
  | { phase: 'online'; info: DeviceInfo; deviceId: string }
  | {
      phase: 'failed';
      info: DeviceInfo | null;
      error: FlowErrorKind;
      /** True when the same verified connection can take new Wi-Fi details. */
      canRetryWifi: boolean;
      /** True when the robot may still come online and polling can resume. */
      canCheckAgain: boolean;
    };

export interface ProvisioningApi {
  createSession(hardwareId: string): Promise<ProvisioningSession>;
  fetchSession(sessionId: string): Promise<ProvisioningSessionStatus>;
  fetchDeviceStatus(deviceId: string): Promise<DeviceStatus>;
}

export interface FlowDependencies {
  transport: BleTransport;
  api: ProvisioningApi;
  randomBytes: (length: number) => Uint8Array;
  sleep?: (ms: number) => Promise<void>;
  now?: () => number;
  timing?: Partial<{
    connectTimeoutMs: number;
    responseTimeoutMs: number;
    onlinePollIntervalMs: number;
    onlineWaitTimeoutMs: number;
  }>;
}

export interface WifiDetails {
  ssid: string;
  password: string;
}

class TimeoutError extends Error {
  constructor(what: string) {
    super(`Timed out waiting for ${what}.`);
    this.name = 'TimeoutError';
  }
}

/** A single-slot mailbox for the next notification of one kind. */
class Mailbox<T> {
  private queue: T[] = [];
  private waiter: ((value: T) => void) | null = null;

  push(value: T): void {
    if (this.waiter) {
      const resolve = this.waiter;
      this.waiter = null;
      resolve(value);
    } else {
      this.queue.push(value);
    }
  }

  clear(): void {
    this.queue = [];
  }

  next(timeoutMs: number, what: string): Promise<T> {
    const queued = this.queue.shift();
    if (queued !== undefined) return Promise.resolve(queued);
    return new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.waiter = null;
        reject(new TimeoutError(what));
      }, timeoutMs);
      this.waiter = (value) => {
        clearTimeout(timer);
        resolve(value);
      };
    });
  }
}

export class ProvisioningFlow {
  private state: FlowState = { phase: 'idle' };
  private readonly listeners = new Set<(state: FlowState) => void>();

  private readonly transport: BleTransport;
  private readonly api: ProvisioningApi;
  private readonly randomBytes: (length: number) => Uint8Array;
  private readonly sleep: (ms: number) => Promise<void>;
  private readonly now: () => number;
  private readonly timing: Required<NonNullable<FlowDependencies['timing']>>;

  private peripheralId: string | null = null;
  private info: DeviceInfo | null = null;
  private bleConnected = false;
  private subscriptions: Unsubscribe[] = [];
  private readonly pairingMail = new Mailbox<PairingNotification>();
  private readonly statusMail = new Mailbox<RobotStatus>();
  private failedAttempts = 0;

  /** Exists only between successful verification and disconnect. */
  private wifiKey: Uint8Array | null = null;
  private session: ProvisioningSession | null = null;
  private credentialsSent = false;
  /** Incremented to abandon any in-flight wait or polling loop. */
  private generation = 0;

  constructor(deps: FlowDependencies) {
    this.transport = deps.transport;
    this.api = deps.api;
    this.randomBytes = deps.randomBytes;
    this.sleep =
      deps.sleep ?? ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
    this.now = deps.now ?? (() => Date.now());
    this.timing = {
      connectTimeoutMs: deps.timing?.connectTimeoutMs ?? CONNECT_TIMEOUT_MS,
      responseTimeoutMs: deps.timing?.responseTimeoutMs ?? RESPONSE_TIMEOUT_MS,
      onlinePollIntervalMs: deps.timing?.onlinePollIntervalMs ?? ONLINE_POLL_INTERVAL_MS,
      onlineWaitTimeoutMs: deps.timing?.onlineWaitTimeoutMs ?? ONLINE_WAIT_TIMEOUT_MS,
    };
  }

  // --- observation -----------------------------------------------------------

  getState(): FlowState {
    return this.state;
  }

  subscribe(listener: (state: FlowState) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private setState(next: FlowState): void {
    this.state = next;
    for (const listener of this.listeners) listener(next);
  }

  private fail(error: FlowErrorKind, options: { canCheckAgain?: boolean } = {}): void {
    this.setState({
      phase: 'failed',
      info: this.info,
      error,
      canRetryWifi: this.bleConnected && this.wifiKey !== null && isWifiRetryable(error),
      canCheckAgain: options.canCheckAgain ?? false,
    });
  }

  // --- connect ---------------------------------------------------------------

  async connect(target: DiscoveredNura): Promise<void> {
    await this.reset();
    const generation = this.generation;
    this.setState({ phase: 'connecting', target });

    // One limited automatic retry (PRD 2, section 51).
    let connected = false;
    for (let attempt = 0; attempt < 2 && !connected; attempt += 1) {
      try {
        await withTimeout(
          this.transport.connect(target.peripheralId),
          this.timing.connectTimeoutMs,
          'connection'
        );
        connected = true;
      } catch {
        log.warn('BLE connect attempt failed', { attempt });
        await this.transport.disconnect(target.peripheralId);
      }
      if (generation !== this.generation) return;
    }
    if (!connected) {
      this.fail('connectionFailed');
      return;
    }

    this.peripheralId = target.peripheralId;
    this.bleConnected = true;
    this.subscriptions.push(
      this.transport.onDisconnect(target.peripheralId, () => this.handleDisconnect())
    );

    try {
      this.subscriptions.push(
        await this.transport.subscribe(target.peripheralId, UUIDS.pairing, (value) => {
          try {
            this.pairingMail.push(decodePairingNotification(value));
          } catch {
            log.warn('ignored an unrecognised pairing notification');
          }
        }),
        await this.transport.subscribe(target.peripheralId, UUIDS.status, (value) => {
          try {
            this.handleStatus(decodeStatus(value));
          } catch {
            log.warn('ignored an unrecognised status notification');
          }
        })
      );
      this.info = parseDeviceInfo(
        await this.transport.read(target.peripheralId, UUIDS.deviceInfo)
      );
    } catch (error) {
      if (generation !== this.generation) return;
      await this.disconnectQuietly();
      this.fail(
        error instanceof ProtocolError ? 'incompatibleFirmware' : 'connectionFailed'
      );
      return;
    }
    if (generation !== this.generation) return;

    log.info('connected to Nura', { hardwareId: this.info.hardwareId });
    this.setState({
      phase: 'awaitingCode',
      info: this.info,
      notice: null,
      attemptsLeft: MAX_FAILED_ATTEMPTS_PER_CONNECTION,
    });
  }

  // --- verify ----------------------------------------------------------------

  /** Runs SPAKE2 with the code the user read off Nura's screen. */
  async submitCode(code: string): Promise<void> {
    const info = this.info;
    const id = this.peripheralId;
    if (this.state.phase !== 'awaitingCode' || !info || !id) return;
    const generation = this.generation;
    this.setState({ phase: 'verifying', info });
    this.pairingMail.clear();

    try {
      const pake = startAppPake(info.hardwareId, code, this.randomBytes);
      await this.transport.write(id, UUIDS.pairing, encodePakeStart(pake.pA));
      const reply = await this.pairingMail.next(
        this.timing.responseTimeoutMs,
        'PAKE response'
      );
      if (generation !== this.generation) return;

      if (reply.type === 'result') {
        this.handlePairingRefusal(reply.result, info);
        return;
      }

      let confirmation: { cA: Uint8Array; ke: Uint8Array };
      try {
        confirmation = pake.finish(reply.pB, reply.cB);
      } catch (error) {
        if (error instanceof WrongCodeError) {
          this.recordWrongCode(info);
          return;
        }
        throw error;
      }

      await this.transport.write(id, UUIDS.pairing, encodePakeConfirm(confirmation.cA));
      const result = await this.pairingMail.next(this.timing.responseTimeoutMs, 'result');
      if (generation !== this.generation) return;
      if (result.type !== 'result' || result.result !== 'VERIFIED') {
        this.handlePairingRefusal(
          result.type === 'result' ? result.result : 'MALFORMED',
          info
        );
        return;
      }

      this.wifiKey = deriveWifiKey(confirmation.ke);
      confirmation.ke.fill(0);
      log.info('Nura verified');
    } catch {
      if (generation !== this.generation) return;
      this.fail(this.bleConnected ? 'connectionFailed' : 'disconnected');
      return;
    }

    await this.prepareSession();
  }

  private recordWrongCode(info: DeviceInfo): void {
    this.failedAttempts += 1;
    const attemptsLeft = MAX_FAILED_ATTEMPTS_PER_CONNECTION - this.failedAttempts;
    if (attemptsLeft <= 0) {
      // The robot ends the connection at its limit; don't make the user wait for it.
      void this.disconnectQuietly();
      this.fail('tooManyAttempts');
      return;
    }
    this.setState({ phase: 'awaitingCode', info, notice: 'wrongCode', attemptsLeft });
  }

  private handlePairingRefusal(result: string, info: DeviceInfo): void {
    switch (result) {
      case 'WRONG_CODE':
        this.recordWrongCode(info);
        return;
      case 'CODE_EXPIRED':
        this.setState({
          phase: 'awaitingCode',
          info,
          notice: 'codeExpired',
          attemptsLeft: MAX_FAILED_ATTEMPTS_PER_CONNECTION - this.failedAttempts,
        });
        return;
      case 'TOO_MANY_ATTEMPTS':
        void this.disconnectQuietly();
        this.fail('tooManyAttempts');
        return;
      case 'NOT_PAIRING':
        void this.disconnectQuietly();
        this.fail('notInPairingMode');
        return;
      default:
        this.fail('unknown');
    }
  }

  /** Gets a provisioning token. Re-callable after a backend error. */
  async prepareSession(): Promise<void> {
    const info = this.info;
    if (!info || !this.wifiKey) return;
    const generation = this.generation;
    this.setState({ phase: 'verifying', info });
    try {
      this.session = await this.api.createSession(info.hardwareId);
    } catch (error) {
      if (generation !== this.generation) return;
      this.fail(flowErrorForApi(error));
      return;
    }
    if (generation !== this.generation) return;
    this.setState({ phase: 'awaitingWifi', info, lastError: null });
  }

  // --- Wi-Fi -----------------------------------------------------------------

  async submitWifi(details: WifiDetails): Promise<void> {
    const info = this.info;
    const id = this.peripheralId;
    if (this.state.phase !== 'awaitingWifi' || !info || !id || !this.wifiKey) return;
    const generation = ++this.generation;
    const key = this.wifiKey;

    this.setState({
      phase: 'provisioning',
      info,
      step: 'sendingWifi',
      bleConnected: true,
    });

    try {
      // A fresh token whenever an earlier attempt reached the robot: it may
      // have been consumed by a claim.
      if (
        !this.session ||
        this.credentialsSent ||
        this.sessionExpiresSoon(this.session)
      ) {
        this.session = await this.api.createSession(info.hardwareId);
      }
      this.credentialsSent = false;
    } catch (error) {
      if (generation !== this.generation) return;
      this.fail(flowErrorForApi(error));
      return;
    }
    const session = this.session;

    try {
      const payload = encryptWifiConfig(
        key,
        info.hardwareId,
        {
          ssid: details.ssid,
          password: details.password,
          provisioningToken: session.provisioningToken,
          apiBaseUrl: session.deviceApiBaseUrl,
        },
        this.randomBytes(NONCE_LENGTH)
      );
      this.statusMail.clear();
      await this.transport.write(id, UUIDS.wifiConfig, payload);
      payload.fill(0);

      const received = await this.nextStatusMatching(
        (status) => status.state === 'RECEIVED_CREDENTIALS' || status.state === 'FAILED',
        generation
      );
      if (generation !== this.generation) return;
      if (received.state === 'FAILED') {
        this.fail(flowErrorForRobot(received.error));
        return;
      }

      await this.transport.write(id, UUIDS.command, encodeCommand('CONNECT_WIFI'));
      this.credentialsSent = true;
    } catch {
      if (generation !== this.generation) return;
      this.fail(this.bleConnected ? 'sendFailed' : 'disconnected');
      return;
    }

    this.setStep('joiningWifi');
    await this.waitUntilOnline(session.id, generation);
  }

  /**
   * The "Try again" button, resolved to the least disruptive retry available:
   *
   *  - `wifi`: the verified connection is alive, so go back to the Wi-Fi form;
   *  - `session`: verification worked but the backend call failed, so ask again;
   *  - `restart`: nothing to resume -- the user has to find Nura again.
   */
  async tryAgain(): Promise<'wifi' | 'session' | 'restart'> {
    if (this.state.phase !== 'failed') return 'restart';
    if (this.state.canRetryWifi) {
      this.editWifi();
      return 'wifi';
    }
    if (this.bleConnected && this.wifiKey && !this.credentialsSent) {
      await this.prepareSession();
      return 'session';
    }
    return 'restart';
  }

  /** Back to the Wi-Fi form over the same verified connection. */
  editWifi(): void {
    if (this.state.phase !== 'failed' || !this.state.canRetryWifi || !this.info) return;
    this.generation += 1;
    this.setState({
      phase: 'awaitingWifi',
      info: this.info,
      lastError: this.state.error,
    });
  }

  /** Resume polling after `robotWentOffline`: the robot may just have been slow. */
  async checkAgain(): Promise<void> {
    if (this.state.phase !== 'failed' || !this.state.canCheckAgain) return;
    if (!this.info || !this.session) return;
    const generation = ++this.generation;
    this.setState({
      phase: 'provisioning',
      info: this.info,
      step: 'checking',
      bleConnected: this.bleConnected,
    });
    await this.waitUntilOnline(this.session.id, generation);
  }

  private sessionExpiresSoon(session: ProvisioningSession): boolean {
    return Date.parse(session.expiresAt) - this.now() < 60_000;
  }

  private setStep(step: ProgressStep): void {
    if (this.state.phase !== 'provisioning') return;
    const order: ProgressStep[] = ['sendingWifi', 'joiningWifi', 'linking', 'checking'];
    // Steps only move forward; a late notification never rewinds the display.
    if (order.indexOf(step) <= order.indexOf(this.state.step)) return;
    this.setState({ ...this.state, step });
  }

  private handleStatus(status: RobotStatus): void {
    this.statusMail.push(status);
    if (this.state.phase !== 'provisioning' || !this.credentialsSent) return;

    switch (status.state) {
      case 'WIFI_CONNECTING':
        this.setStep('joiningWifi');
        break;
      case 'WIFI_CONNECTED':
      case 'REGISTERING':
        this.setStep('linking');
        break;
      case 'REGISTERED':
        this.setStep('checking');
        break;
      case 'FAILED':
        this.generation += 1;
        this.fail(flowErrorForRobot(status.error));
        break;
      default:
        break;
    }
  }

  private async nextStatusMatching(
    predicate: (status: RobotStatus) => boolean,
    generation: number
  ): Promise<RobotStatus> {
    const deadline = this.now() + this.timing.responseTimeoutMs;
    for (;;) {
      const remaining = deadline - this.now();
      if (remaining <= 0) throw new TimeoutError('status');
      const status = await this.statusMail.next(remaining, 'status');
      if (generation !== this.generation || predicate(status)) return status;
    }
  }

  /**
   * Polls the backend until it has heard from the robot (PRD 2, section 36).
   *
   * BLE status only moves the progress display. Losing BLE here is not a
   * failure: the robot may already be on Wi-Fi (PRD 2, section 53).
   */
  private async waitUntilOnline(sessionId: string, generation: number): Promise<void> {
    const deadline = this.now() + this.timing.onlineWaitTimeoutMs;
    let lastError: unknown = null;

    while (generation === this.generation) {
      try {
        const session = await this.api.fetchSession(sessionId);
        if (generation !== this.generation) return;
        lastError = null;

        if (session.state === 'claimed' && session.deviceId) {
          this.setStep('checking');
          const status = await this.api.fetchDeviceStatus(session.deviceId);
          if (generation !== this.generation) return;
          if (status.checkedInSinceClaim && status.connectionStatus === 'online') {
            await this.finish(session.deviceId);
            return;
          }
        } else if (session.state === 'expired') {
          this.fail('registrationFailed');
          return;
        }
      } catch (error) {
        lastError = error;
      }

      if (this.now() >= deadline) {
        if (generation !== this.generation) return;
        this.fail(
          lastError && flowErrorForApi(lastError) === 'backendUnreachable'
            ? 'backendUnreachable'
            : 'robotWentOffline',
          { canCheckAgain: true }
        );
        return;
      }
      await this.sleep(this.timing.onlinePollIntervalMs);
    }
  }

  private async finish(deviceId: string): Promise<void> {
    const info = this.info;
    const id = this.peripheralId;
    if (!info) return;
    // Setup is done: tell Nura to stop advertising, then let go (PRD 2, section 54).
    if (id && this.bleConnected) {
      await this.transport.write(id, UUIDS.command, encodeCommand('FINISH')).catch(() => {
        log.warn('FINISH could not be sent; Nura will stop advertising on its own');
      });
    }
    await this.disconnectQuietly();
    this.forgetSecrets();
    log.info('Nura is online', { deviceId });
    this.setState({ phase: 'online', info, deviceId });
  }

  // --- lifecycle -------------------------------------------------------------

  private handleDisconnect(): void {
    this.bleConnected = false;
    // The session key belonged to that connection.
    this.wifiKey?.fill(0);
    this.wifiKey = null;

    switch (this.state.phase) {
      case 'connecting':
      case 'awaitingCode':
      case 'verifying':
      case 'awaitingWifi':
        this.generation += 1;
        this.fail('disconnected');
        break;
      case 'provisioning':
        if (this.credentialsSent) {
          this.setState({ ...this.state, bleConnected: false });
        } else {
          this.generation += 1;
          this.fail('disconnected');
        }
        break;
      case 'failed':
        this.setState({ ...this.state, canRetryWifi: false });
        break;
      default:
        break;
    }
  }

  private forgetSecrets(): void {
    this.wifiKey?.fill(0);
    this.wifiKey = null;
    this.session = null;
  }

  private async disconnectQuietly(): Promise<void> {
    for (const unsubscribe of this.subscriptions) unsubscribe();
    this.subscriptions = [];
    const id = this.peripheralId;
    this.bleConnected = false;
    if (id) await this.transport.disconnect(id);
  }

  private async reset(): Promise<void> {
    this.generation += 1;
    await this.disconnectQuietly();
    this.forgetSecrets();
    this.peripheralId = null;
    this.info = null;
    this.failedAttempts = 0;
    this.credentialsSent = false;
    this.pairingMail.clear();
    this.statusMail.clear();
  }

  /** Abandons the flow and releases the robot. */
  async cancel(): Promise<void> {
    await this.reset();
    this.setState({ phase: 'idle' });
  }
}

function withTimeout<T>(promise: Promise<T>, ms: number, what: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new TimeoutError(what)), ms);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error: unknown) => {
        clearTimeout(timer);
        reject(error instanceof Error ? error : new Error(String(error)));
      }
    );
  });
}
