/**
 * Byte helpers that do not depend on `TextDecoder`, which Hermes does not
 * reliably provide.
 */

/** Decodes UTF-8, replacing malformed sequences with U+FFFD. */
export function utf8Decode(bytes: Uint8Array): string {
  let output = '';
  let index = 0;
  while (index < bytes.length) {
    const first = bytes[index] ?? 0;
    let codePoint = 0xfffd;
    let length = 1;

    if (first < 0x80) {
      codePoint = first;
    } else if (first >= 0xc2 && first < 0xe0) {
      length = 2;
    } else if (first >= 0xe0 && first < 0xf0) {
      length = 3;
    } else if (first >= 0xf0 && first < 0xf5) {
      length = 4;
    }

    if (length > 1) {
      const continuation = bytes.slice(index + 1, index + length);
      const valid =
        continuation.length === length - 1 &&
        continuation.every((byte) => (byte & 0xc0) === 0x80);
      if (valid) {
        codePoint = first & (0xff >> (length + 1));
        for (const byte of continuation) codePoint = (codePoint << 6) | (byte & 0x3f);
        const tooSmall = [0, 0, 0x80, 0x800, 0x10000][length] ?? 0;
        if (codePoint < tooSmall || codePoint > 0x10ffff) codePoint = 0xfffd;
      } else {
        codePoint = 0xfffd;
        length = 1;
      }
    }

    output += String.fromCodePoint(codePoint);
    index += length;
  }
  return output;
}

export function toByteArray(values: number[]): Uint8Array {
  return Uint8Array.from(values);
}

export function toNumberArray(bytes: Uint8Array): number[] {
  return Array.from(bytes);
}
