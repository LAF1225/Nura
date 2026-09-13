/**
 * SPAKE2 against RFC 9382 Appendix B, and the Nura-specific pieces around it.
 *
 * The vectors below are copied verbatim from the RFC. If these pass, the
 * group arithmetic, transcript encoding, key schedule and MACs all match the
 * standard -- the firmware runs the same vectors on the board
 * (firmware/xiao_esp32s3/test/test_spake2).
 */
import { bytesToHex, hexToBytes, utf8ToBytes } from '@noble/hashes/utils.js';

import {
  computePA,
  computePB,
  constantTimeEqual,
  keySchedule,
  passwordScalar,
  scalarFromRandomBytes,
  sharedPointForA,
  sharedPointForB,
  startAppPake,
  WrongCodeError,
} from '../src/services/provisioning/spake2';

interface Vector {
  A: string;
  B: string;
  w: string;
  x: string;
  pA: string;
  y: string;
  pB: string;
  K: string;
  TT: string;
  hashTT: string;
  Ke: string;
  Ka: string;
  KcA: string;
  KcB: string;
  cA: string;
  cB: string;
}

const join = (...parts: string[]) => parts.join('');

const VECTORS: Vector[] = [
  {
    A: 'server',
    B: 'client',
    w: '2ee57912099d31560b3a44b1184b9b4866e904c49d12ac5042c97dca461b1a5f',
    x: '43dd0fd7215bdcb482879fca3220c6a968e66d70b1356cac18bb26c84a78d729',
    pA: join(
      '04a56fa807caaa53a4d28dbb9853b9815c61a411118a6fe516a8798434751470',
      'f9010153ac33d0d5f2047ffdb1a3e42c9b4e6be662766e1eeb4116988ede5f912c'
    ),
    y: 'dcb60106f276b02606d8ef0a328c02e4b629f84f89786af5befb0bc75b6e66be',
    pB: join(
      '0406557e482bd03097ad0cbaa5df82115460d951e3451962f1eaf4367a420676',
      'd09857ccbc522686c83d1852abfa8ed6e4a1155cf8f1543ceca528afb591a1e0b7'
    ),
    K: join(
      '0412af7e89717850671913e6b469ace67bd90a4df8ce45c2af19010175e37eed',
      '69f75897996d539356e2fa6a406d528501f907e04d97515fbe83db277b715d3325'
    ),
    TT: join(
      '06000000000000007365727665720600000000000000636c69656e744100000',
      '00000000004a56fa807caaa53a4d28dbb9853b9815c61a411118a6fe516a8798434751',
      '470f9010153ac33d0d5f2047ffdb1a3e42c9b4e6be662766e1eeb4116988ede5f912c4',
      '1000000000000000406557e482bd03097ad0cbaa5df82115460d951e3451962f1eaf43',
      '67a420676d09857ccbc522686c83d1852abfa8ed6e4a1155cf8f1543ceca528afb591a',
      '1e0b741000000000000000412af7e89717850671913e6b469ace67bd90a4df8ce45c2a',
      'f19010175e37eed69f75897996d539356e2fa6a406d528501f907e04d97515fbe83db2',
      '77b715d332520000000000000002ee57912099d31560b3a44b1184b9b4866e904c49d1',
      '2ac5042c97dca461b1a5f'
    ),
    hashTT: '0e0672dc86f8e45565d338b0540abe6915bdf72e2b35b5c9e5663168e960a91b',
    Ke: '0e0672dc86f8e45565d338b0540abe69',
    Ka: '15bdf72e2b35b5c9e5663168e960a91b',
    KcA: '00c12546835755c86d8c0db7851ae86f',
    KcB: 'a9fa3406c3b781b93d804485430ca27a',
    cA: '58ad4aa88e0b60d5061eb6b5dd93e80d9c4f00d127c65b3b35b1b5281fee38f0',
    cB: 'd3e2e547f1ae04f2dbdbf0fc4b79f8ecff2dff314b5d32fe9fcef2fb26dc459b',
  },
  {
    A: '',
    B: 'client',
    w: '0548d8729f730589e579b0475a582c1608138ddf7054b73b5381c7e883e2efae',
    x: '403abbe3b1b4b9ba17e3032849759d723939a27a27b9d921c500edde18ed654b',
    pA: join(
      '04a897b769e681c62ac1c2357319a3d363f610839c4477720d24cbe32f5fd8',
      '5f44fb92ba966578c1b712be6962498834078262caa5b441ecfa9d4a9485720e918a'
    ),
    y: '903023b6598908936ea7c929bd761af6039577a9c3f9581064187c3049d87065',
    pB: join(
      '04e0f816fd1c35e22065d5556215c097e799390d16661c386e0ecc84593974',
      'a61b881a8c82327687d0501862970c64565560cb5671f696048050ca66ca5f8cc7fc'
    ),
    K: join(
      '048f83ec9f6e4f87cc6f9dc740bdc2769725f923364f01c84148c049a39a735e',
      'bda82eac03e00112fd6a5710682767cff5361f7e819e53d8d3c3a2922e0d837aa6'
    ),
    TT: join(
      '00000000000000000600000000000000636c69656e74410000000000000004a',
      '897b769e681c62ac1c2357319a3d363f610839c4477720d24cbe32f5fd85f44fb92ba9',
      '66578c1b712be6962498834078262caa5b441ecfa9d4a9485720e918a4100000000000',
      '00004e0f816fd1c35e22065d5556215c097e799390d16661c386e0ecc84593974a61b8',
      '81a8c82327687d0501862970c64565560cb5671f696048050ca66ca5f8cc7fc4100000',
      '000000000048f83ec9f6e4f87cc6f9dc740bdc2769725f923364f01c84148c049a39a7',
      '35ebda82eac03e00112fd6a5710682767cff5361f7e819e53d8d3c3a2922e0d837aa62',
      '0000000000000000548d8729f730589e579b0475a582c1608138ddf7054b73b5381c7e',
      '883e2efae'
    ),
    hashTT: '642f05c473c2cd79909f9a841e2f30a70bf89b18180af97353ba198789c2b963',
    Ke: '642f05c473c2cd79909f9a841e2f30a7',
    Ka: '0bf89b18180af97353ba198789c2b963',
    KcA: 'c6be376fc7cd1301fd0a13adf3e7bffd',
    KcB: 'b7243f4ae60440a49b3f8cab3c1fba07',
    cA: '47d29e6666af1b7dd450d571233085d7a9866e4d49d2645e2df975489521232b',
    cB: '3313c5cefc361d27fb16847a91c2a73b766ffa90a4839122a9b70a2f6bd1d6df',
  },
  {
    A: 'server',
    B: '',
    w: '626e0cdc7b14c9db3e52a0b1b3a768c98e37852d5db30febe0497b14eae8c254',
    x: '07adb3db6bc623d3399726bfdbfd3d15a58ea776ab8a308b00392621291f9633',
    pA: join(
      '04f88fb71c99bfffaea370966b7eb99cd4be0ff1a7d335caac4211c4afd855e2',
      'e15a873b298503ad8ba1d9cbb9a392d2ba309b48bfd7879aefd0f2cea6009763b0'
    ),
    y: 'b6a4fc8dbb629d4ba51d6f91ed1532cf87adec98f25dd153a75accafafedec16',
    pB: join(
      '040c269d6be017dccb15182ac6bfcd9e2a14de019dd587eaf4bdfd353f031101',
      'e7cca177f8eb362a6e83e7d5e729c0732e1b528879c086f39ba0f31a9661bd34db'
    ),
    K: join(
      '0445ee233b8ecb51ebd6e7da3f307e88a1616bae2166121221fdc0dadb986afa',
      'f3ec8a988dc9c626fa3b99f58a7ca7c9b844bb3e8dd9554aafc5b53813504c1cbe'
    ),
    TT: join(
      '06000000000000007365727665720000000000000000410000000000000004f',
      '88fb71c99bfffaea370966b7eb99cd4be0ff1a7d335caac4211c4afd855e2e15a873b2',
      '98503ad8ba1d9cbb9a392d2ba309b48bfd7879aefd0f2cea6009763b04100000000000',
      '000040c269d6be017dccb15182ac6bfcd9e2a14de019dd587eaf4bdfd353f031101e7c',
      'ca177f8eb362a6e83e7d5e729c0732e1b528879c086f39ba0f31a9661bd34db4100000',
      '0000000000445ee233b8ecb51ebd6e7da3f307e88a1616bae2166121221fdc0dadb986',
      'afaf3ec8a988dc9c626fa3b99f58a7ca7c9b844bb3e8dd9554aafc5b53813504c1cbe2',
      '000000000000000626e0cdc7b14c9db3e52a0b1b3a768c98e37852d5db30febe0497b1',
      '4eae8c254'
    ),
    hashTT: '005184ff460da2ce59062c87733c299c3521297d736598fc0a1127600efa1afb',
    Ke: '005184ff460da2ce59062c87733c299c',
    Ka: '3521297d736598fc0a1127600efa1afb',
    KcA: 'f3da53604f0aeecea5a33be7bddf6edf',
    KcB: '9e3f86848736f159bd92b6e107ec6799',
    cA: 'bc9f9bbe99f26d0b2260e6456e05a86196a3307ec6663a18bf6ac825736533b2',
    cB: 'c2370e1bf813b086dff0d834e74425a06e6390f48f5411900276dcccc5a297ec',
  },
  {
    A: '',
    B: '',
    w: '7bf46c454b4c1b25799527d896508afd5fc62ef4ec59db1efb49113063d70cca',
    x: '8cef65df64bb2d0f83540c53632de911b5b24b3eab6cc74a97609fd659e95473',
    pA: join(
      '04a65b367a3f613cf9f0654b1b28a1e3a8a40387956c8ba6063e8658563890f4',
      '6ca1ef6a676598889fc28de2950ab8120b79a5ef1ea4c9f44bc98f585634b46d66'
    ),
    y: 'd7a66f64074a84652d8d623a92e20c9675c61cb5b4f6a0063e4648a2fdc02d53',
    pB: join(
      '04589f13218822710d98d8b2123a079041052d9941b9cf88c6617ddb2fcc0494',
      '662eea8ba6b64692dc318250030c6af045cb738bc81ba35b043c3dcb46adf6f58d'
    ),
    K: join(
      '041a3c03d51b452537ca2a1fea6110353c6d5ed483c4f0f86f4492ca3f378d40',
      'a994b4477f93c64d928edbbcd3e85a7c709b7ea73ee97986ce3d1438e135543772'
    ),
    TT: join(
      '00000000000000000000000000000000410000000000000004a65b367a3f613',
      'cf9f0654b1b28a1e3a8a40387956c8ba6063e8658563890f46ca1ef6a676598889fc28',
      'de2950ab8120b79a5ef1ea4c9f44bc98f585634b46d66410000000000000004589f132',
      '18822710d98d8b2123a079041052d9941b9cf88c6617ddb2fcc0494662eea8ba6b6469',
      '2dc318250030c6af045cb738bc81ba35b043c3dcb46adf6f58d4100000000000000041',
      'a3c03d51b452537ca2a1fea6110353c6d5ed483c4f0f86f4492ca3f378d40a994b4477',
      'f93c64d928edbbcd3e85a7c709b7ea73ee97986ce3d1438e1355437722000000000000',
      '0007bf46c454b4c1b25799527d896508afd5fc62ef4ec59db1efb49113063d70cca'
    ),
    hashTT: 'fc6374762ba5cf11f4b2caa08b2cd1b9907ae0e26e8d6234318d91583cd74c86',
    Ke: 'fc6374762ba5cf11f4b2caa08b2cd1b9',
    Ka: '907ae0e26e8d6234318d91583cd74c86',
    KcA: '5dbd2f477166b7fb6d61febbd77a5563',
    KcB: '7689b4654407a5faeffdc8f18359d8a3',
    cA: 'dfb4db8d48ae5a675963ea5e6c19d98d4ea028d8e898dad96ea19a80ade95dca',
    cB: 'd0f0609d1613138d354f7e95f19fb556bf52d751947241e8c7118df5ef0ae175',
  },
];

describe('SPAKE2 matches RFC 9382 Appendix B', () => {
  it.each(VECTORS)('A=$A B=$B', (vector) => {
    const w = BigInt(`0x${vector.w}`);
    const x = BigInt(`0x${vector.x}`);
    const y = BigInt(`0x${vector.y}`);

    const pA = computePA(w, x);
    const pB = computePB(w, y);
    expect(bytesToHex(pA)).toBe(vector.pA);
    expect(bytesToHex(pB)).toBe(vector.pB);

    const kA = sharedPointForA(w, x, pB);
    const kB = sharedPointForB(w, y, pA);
    expect(bytesToHex(kA)).toBe(vector.K);
    expect(bytesToHex(kB)).toBe(vector.K);

    const keys = keySchedule({
      idA: utf8ToBytes(vector.A),
      idB: utf8ToBytes(vector.B),
      pA,
      pB,
      K: kA,
      w,
      aad: new Uint8Array(0),
    });
    expect(bytesToHex(keys.tt)).toBe(vector.TT);
    expect(bytesToHex(keys.ke)).toBe(vector.Ke);
    expect(bytesToHex(keys.ka)).toBe(vector.Ka);
    expect(bytesToHex(keys.kcA)).toBe(vector.KcA);
    expect(bytesToHex(keys.kcB)).toBe(vector.KcB);
    expect(bytesToHex(keys.cA)).toBe(vector.cA);
    expect(bytesToHex(keys.cB)).toBe(vector.cB);
  });
});

describe('Nura verification exchange', () => {
  const HARDWARE_ID = 'NURA-3C84279A1B2C';
  let counter = 0;
  // Deterministic "randomness" is fine for tests; the app uses expo-crypto.
  const random = (length: number) =>
    Uint8Array.from({ length }, (_, index) => (index * 31 + (counter += 7)) & 0xff);

  /** Plays the robot's half, exactly as the firmware does. */
  function robotRespond(code: string, pA: Uint8Array) {
    const w = passwordScalar(HARDWARE_ID, code);
    const y = scalarFromRandomBytes(random(48));
    const pB = computePB(w, y);
    const K = sharedPointForB(w, y, pA);
    const keys = keySchedule({
      idA: utf8ToBytes('nura-app'),
      idB: utf8ToBytes(HARDWARE_ID),
      pA,
      pB,
      K,
      w,
      aad: utf8ToBytes('nura-provisioning-v1'),
    });
    return { pB, cB: keys.cB, cA: keys.cA, ke: keys.ke };
  }

  it('agrees on a session key when the code matches', () => {
    const app = startAppPake(HARDWARE_ID, '482731', random);
    const robot = robotRespond('482731', app.pA);

    const result = app.finish(robot.pB, robot.cB);

    expect(constantTimeEqual(result.cA, robot.cA)).toBe(true);
    expect(bytesToHex(result.ke)).toBe(bytesToHex(robot.ke));
  });

  it('detects a wrong code before sending anything useful', () => {
    const app = startAppPake(HARDWARE_ID, '482731', random);
    const robot = robotRespond('482732', app.pA);

    expect(() => app.finish(robot.pB, robot.cB)).toThrow(WrongCodeError);
  });

  it('binds the code to the robot it was shown on', () => {
    // Same code, different robot: the password scalar differs.
    expect(passwordScalar(HARDWARE_ID, '482731')).not.toBe(
      passwordScalar('NURA-3C84279AFFFF', '482731')
    );
  });

  it('refuses a point that is not on the curve', () => {
    const app = startAppPake(HARDWARE_ID, '482731', random);
    const bogus = new Uint8Array(65);
    bogus[0] = 0x04;
    bogus[64] = 1;
    expect(() => app.finish(bogus, new Uint8Array(32))).toThrow(/curve|infinity/);
  });

  it('never produces a zero scalar', () => {
    expect(scalarFromRandomBytes(new Uint8Array(48))).toBe(1n);
    expect(scalarFromRandomBytes(hexToBytes('ff'.repeat(48)))).toBeGreaterThan(0n);
  });
});
