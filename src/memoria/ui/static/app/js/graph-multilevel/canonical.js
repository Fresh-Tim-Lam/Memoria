/**
 * Memoria 多层次图谱 B4 —— 规范序列化与 SHA-256（浏览器 + Node 通用，同步）。
 *
 * canonical 口径必须与 Python 侧 `memoria.graph.multilevel.admission.canonical_bytes`
 * 完全一致（否则 `frame_id` 无法跨端复算）：
 *   JSON.stringify(sortKeysDeep(obj)) + "\n" 的 UTF-8 字节
 *   Python: json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
 *
 * 为什么自带 SHA-256：浏览器 WebView 的 `crypto.subtle` 是异步 API，而
 * `frame_id` 必须在状态机转移（同步）中即时派生；Node 测试也需要同一实现。
 */
(function (global) {
  "use strict";

  function sortKeysDeep(value) {
    if (Array.isArray(value)) return value.map(sortKeysDeep);
    if (value && typeof value === "object") {
      const out = {};
      for (const key of Object.keys(value).sort()) out[key] = sortKeysDeep(value[key]);
      return out;
    }
    return value;
  }

  function canonicalJson(value) {
    return JSON.stringify(sortKeysDeep(value));
  }

  function utf8Bytes(text) {
    if (typeof TextEncoder !== "undefined") return new TextEncoder().encode(text);
    // 最小兜底（仅覆盖 BMP；frame_spec 只含 ASCII 标识符与数字）
    const bytes = [];
    for (let i = 0; i < text.length; i++) {
      const code = text.charCodeAt(i);
      if (code < 0x80) bytes.push(code);
      else if (code < 0x800) bytes.push(0xc0 | (code >> 6), 0x80 | (code & 63));
      else bytes.push(0xe0 | (code >> 12), 0x80 | ((code >> 6) & 63), 0x80 | (code & 63));
    }
    return Uint8Array.from(bytes);
  }

  // ── SHA-256（FIPS 180-4），同步实现 ─────────────────────────────────────
  const K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ];

  function rotr(x, n) {
    return (x >>> n) | (x << (32 - n));
  }

  function sha256Bytes(data) {
    const msg = data instanceof Uint8Array ? data : Uint8Array.from(data || []);
    const bitLen = msg.length * 8;
    const withPad = new Uint8Array(((msg.length + 8) >> 6 << 6) + 64);
    withPad.set(msg);
    withPad[msg.length] = 0x80;
    const dv = new DataView(withPad.buffer);
    dv.setUint32(withPad.length - 4, bitLen >>> 0, false);
    // JS number 仅 53 位；消息长度远小于 2^32 字节（本场景），高 32 位写 0 即可
    dv.setUint32(withPad.length - 8, Math.floor(bitLen / 0x100000000) >>> 0, false);

    const h = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    const w = new Array(64);
    for (let offset = 0; offset < withPad.length; offset += 64) {
      for (let i = 0; i < 16; i++) w[i] = dv.getUint32(offset + i * 4, false);
      for (let i = 16; i < 64; i++) {
        const s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3);
        const s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10);
        w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
      }
      let [a, b, c, d, e, f, g, hh] = h;
      for (let i = 0; i < 64; i++) {
        const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
        const ch = (e & f) ^ (~e & g);
        const t1 = (hh + S1 + ch + K[i] + w[i]) >>> 0;
        const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
        const maj = (a & b) ^ (a & c) ^ (b & c);
        const t2 = (S0 + maj) >>> 0;
        hh = g;
        g = f;
        f = e;
        e = (d + t1) >>> 0;
        d = c;
        c = b;
        b = a;
        a = (t1 + t2) >>> 0;
      }
      h[0] = (h[0] + a) >>> 0;
      h[1] = (h[1] + b) >>> 0;
      h[2] = (h[2] + c) >>> 0;
      h[3] = (h[3] + d) >>> 0;
      h[4] = (h[4] + e) >>> 0;
      h[5] = (h[5] + f) >>> 0;
      h[6] = (h[6] + g) >>> 0;
      h[7] = (h[7] + hh) >>> 0;
    }
    let hex = "";
    for (const word of h) hex += word.toString(16).padStart(8, "0");
    return hex;
  }

  function sha256Hex(text) {
    return sha256Bytes(utf8Bytes(String(text)));
  }

  function canonicalBytes(value) {
    return utf8Bytes(canonicalJson(value) + "\n");
  }

  function canonicalSha(value) {
    return sha256Bytes(canonicalBytes(value));
  }

  const api = { canonicalJson, canonicalBytes, canonicalSha, sha256Hex, utf8Bytes, sortKeysDeep };
  global.MemoriaGraphCanonical = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
