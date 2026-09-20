/**
 * The provisioning flow end to end, against a simulated robot and backend
 * (PRD 2, section 67).
 */
import { ApiError } from '../src/services/api/errors';
import {
  ProvisioningFlow,
  type FlowState,
} from '../src/services/provisioning/provisioningFlow';
import { FakeBackend, FakeRobot, PERIPHERAL_ID, randomBytes } from './fakeRobot';

const TARGET = { peripheralId: PERIPHERAL_ID, shortId: '1B2C', rssi: -52 };
const WIFI = { ssid: 'Home Network', password: 'correct horse battery' };

function setup() {
  const backend = new FakeBackend();
  const robot = new FakeRobot(backend);
  const flow = new ProvisioningFlow({
    transport: robot,
    api: backend,
    randomBytes,
    timing: {
      connectTimeoutMs: 200,
      responseTimeoutMs: 500,
      onlinePollIntervalMs: 5,
      onlineWaitTimeoutMs: 300,
    },
  });
  const phases: FlowState['phase'][] = [];
  flow.subscribe((state) => phases.push(state.phase));
  return { backend, robot, flow, phases };
}

async function verified(code = '482731') {
  const context = setup();
  await context.flow.connect(TARGET);
  await context.flow.submitCode(code);
  return context;
}

describe('connecting', () => {
  it('reads device info and asks for the code', async () => {
    const { flow } = setup();
    await flow.connect(TARGET);

    const state = flow.getState();
    expect(state.phase).toBe('awaitingCode');
    if (state.phase === 'awaitingCode') {
      expect(state.info.hardwareId).toBe('NURA-3C84279A1B2C');
      expect(state.info.firmwareVersion).toBe('0.1.0');
      expect(state.info.provisioned).toBe(false);
    }
  });

  it('retries a failed connection once, and only once', async () => {
    const { flow, robot } = setup();
    robot.connectFailures = 1;
    await flow.connect(TARGET);
    expect(flow.getState().phase).toBe('awaitingCode');
    expect(robot.connectCalls).toBe(2);

    const second = setup();
    second.robot.connectFailures = 5;
    await second.flow.connect(TARGET);
    expect(second.flow.getState()).toMatchObject({
      phase: 'failed',
      error: 'connectionFailed',
    });
    expect(second.robot.connectCalls).toBe(2);
  });

  it('refuses a robot speaking an unknown protocol version', async () => {
    const { flow, robot } = setup();
    robot.deviceInfo = { ...robot.deviceInfo, protocol: 99 };
    await flow.connect(TARGET);
    expect(flow.getState()).toMatchObject({
      phase: 'failed',
      error: 'incompatibleFirmware',
    });
  });
});

describe('verification', () => {
  it('unlocks Wi-Fi setup after the correct code', async () => {
    const { flow, robot, backend } = await verified();
    expect(robot.verified).toBe(true);
    expect(flow.getState().phase).toBe('awaitingWifi');
    // The backend session is created only after verification.
    expect(backend.createCalls).toBe(1);
  });

  it('reports a wrong code and lets the user try again', async () => {
    const { flow, robot } = await verified('000000');
    expect(robot.verified).toBe(false);
    expect(flow.getState()).toMatchObject({
      phase: 'awaitingCode',
      notice: 'wrongCode',
      attemptsLeft: 2,
    });

    await flow.submitCode('482731');
    expect(flow.getState().phase).toBe('awaitingWifi');
  });

  it('stops after three wrong codes', async () => {
    const { flow } = await verified('000000');
    await flow.submitCode('111111');
    await flow.submitCode('222222');
    expect(flow.getState()).toMatchObject({ phase: 'failed', error: 'tooManyAttempts' });
  });

  it('never sends Wi-Fi details before verification succeeds', async () => {
    const { flow, robot } = await verified('000000');
    // Not in the Wi-Fi phase, so the request is ignored outright.
    await flow.submitWifi(WIFI);
    expect(robot.configWritesBeforeVerification).toBe(0);
    expect(robot.receivedConfigs).toHaveLength(0);
  });

  it('stops before Wi-Fi when the robot belongs to another account', async () => {
    const context = setup();
    context.backend.createError = new ApiError('conflict', '409', {
      status: 409,
      code: 'already_claimed',
    });
    await context.flow.connect(TARGET);
    await context.flow.submitCode('482731');

    expect(context.flow.getState()).toMatchObject({
      phase: 'failed',
      error: 'alreadyClaimed',
    });
    expect(context.robot.receivedConfigs).toHaveLength(0);
  });
});

describe('Wi-Fi provisioning', () => {
  it('goes online only once the backend has heard from the robot', async () => {
    const { flow, robot, phases } = await verified();
    await flow.submitWifi(WIFI);

    expect(flow.getState()).toMatchObject({ phase: 'online', deviceId: 'device-1' });
    expect(robot.receivedConfigs).toEqual([
      {
        ssid: 'Home Network',
        password: 'correct horse battery',
        provisioningToken: 'npt_token_1',
        apiBaseUrl: 'http://192.168.1.20:8000',
      },
    ]);
    // FINISH tells the robot to stop advertising.
    expect(robot.commands).toEqual([0x01, 0x04]);
    expect(phases).toContain('provisioning');
  });

  it('does not report success when the robot claims but never checks in', async () => {
    const { flow, backend } = await verified();
    backend.heartbeats = false;
    await flow.submitWifi(WIFI);

    // Robot said REGISTERED over BLE, but the backend never saw a heartbeat.
    expect(flow.getState()).toMatchObject({
      phase: 'failed',
      error: 'robotWentOffline',
      canCheckAgain: true,
    });

    backend.heartbeats = true;
    await flow.checkAgain();
    expect(flow.getState().phase).toBe('online');
  });

  it('turns a wrong password into a recoverable error on the same connection', async () => {
    const { flow, robot, backend } = await verified();
    robot.wifiBehaviour = { fail: 'WIFI_AUTH_FAILED' };
    await flow.submitWifi(WIFI);
    // Give the robot's failure notification time to land.
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(flow.getState()).toMatchObject({
      phase: 'failed',
      error: 'wifiAuthFailed',
      canRetryWifi: true,
    });

    flow.editWifi();
    expect(flow.getState()).toMatchObject({
      phase: 'awaitingWifi',
      lastError: 'wifiAuthFailed',
    });

    robot.wifiBehaviour = 'joins';
    await flow.submitWifi({ ssid: WIFI.ssid, password: 'the right one!' });
    expect(flow.getState().phase).toBe('online');
    expect(robot.receivedConfigs.at(-1)?.password).toBe('the right one!');
    // No restart of the robot was needed, and a fresh token was used.
    expect(backend.createCalls).toBe(2);
  });

  it.each([
    ['WIFI_NOT_FOUND', 'wifiNotFound'],
    ['WIFI_TIMEOUT', 'wifiTimeout'],
    ['WIFI_UNSUPPORTED', 'wifiUnsupported'],
    ['BACKEND_UNREACHABLE', 'robotCannotReachBackend'],
    ['ALREADY_CLAIMED', 'alreadyClaimed'],
  ] as const)('maps robot error %s to %s', async (robotError, expected) => {
    const { flow, robot } = await verified();
    robot.wifiBehaviour = { fail: robotError };
    await flow.submitWifi(WIFI);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(flow.getState()).toMatchObject({ phase: 'failed', error: expected });
  });

  it('keeps checking the backend when BLE drops after Wi-Fi details were sent', async () => {
    const { flow, robot } = await verified();
    robot.wifiBehaviour = 'joinsThenDropsBle';
    await flow.submitWifi(WIFI);

    // Not a failure: the robot joined Wi-Fi and the backend confirms it.
    expect(flow.getState().phase).toBe('online');
  });

  it('fails cleanly when BLE drops before Wi-Fi details are sent', async () => {
    const { flow, robot } = await verified();
    robot.dropConnection();
    expect(flow.getState()).toMatchObject({
      phase: 'failed',
      error: 'disconnected',
      canRetryWifi: false,
    });
  });

  it('reports the backend as unreachable when the phone is offline', async () => {
    const context = setup();
    context.backend.createError = new ApiError('offline', 'offline');
    await context.flow.connect(TARGET);
    await context.flow.submitCode('482731');
    expect(context.flow.getState()).toMatchObject({
      phase: 'failed',
      error: 'backendUnreachable',
    });

    context.backend.createError = null;
    await context.flow.prepareSession();
    expect(context.flow.getState().phase).toBe('awaitingWifi');
  });
});
