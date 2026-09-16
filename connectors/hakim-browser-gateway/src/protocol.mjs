import {
  createCipheriv,
  createDecipheriv,
  createHash,
  createHmac,
  randomBytes,
  randomUUID,
  timingSafeEqual,
} from 'node:crypto';

export const COMMAND_AAD = 'HAKIM-CARRIER-v1';
export const RESULT_AAD = 'HAKIM-RESULT-v1';
export const COMMAND_PREFIX = 'HC1.';
export const RESULT_PREFIX = 'HR1.';
export const MAX_PAYLOAD_B64 = 32768;
export const REQUEST_ID_RE = /^[A-Za-z0-9._:-]{8,128}$/;
export const TOPIC_RE = /^[A-Za-z0-9_-]{20,120}$/;
export const RELAY_KEY_RE = /^[A-Za-z0-9_-]{40,100}$/;
export const BROWSER_OPS = new Set(['status', 'ui', 'screenshot', 'action']);
export const BROWSER_ACTIONS = new Set([
  'browser_open', 'open_url', 'browser_back', 'browser_forward',
  'browser_reload', 'click_text', 'click_css', 'set_text',
  'tap', 'swipe', 'scroll_by',
]);

const enc = new TextEncoder();

function b64url(buf) {
  return Buffer.from(buf).toString('base64url');
}

function fromB64url(value) {
  return Buffer.from(value, 'base64url');
}

function derivedKey(aad, relayKey) {
  return createHash('sha256').update(`${aad}\u0000${relayKey}`, 'utf8').digest();
}

function aesGcmEncrypt(raw, relayKey, aad, prefix) {
  const nonce = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', derivedKey(aad, relayKey), nonce);
  cipher.setAAD(enc.encode(aad));
  const ciphertext = Buffer.concat([cipher.update(raw, 'utf8'), cipher.final()]);
  const packed = Buffer.concat([nonce, ciphertext, cipher.getAuthTag()]);
  return prefix + b64url(packed);
}

function aesGcmDecrypt(carrier, relayKey, aad, prefix) {
  if (typeof carrier !== 'string' || !carrier.startsWith(prefix)) {
    throw new Error('invalid_carrier_prefix');
  }
  const packed = fromB64url(carrier.slice(prefix.length));
  if (packed.length < 28) throw new Error('invalid_carrier_length');
  const nonce = packed.subarray(0, 12);
  const tag = packed.subarray(packed.length - 16);
  const ciphertext = packed.subarray(12, packed.length - 16);
  const decipher = createDecipheriv('aes-256-gcm', derivedKey(aad, relayKey), nonce);
  decipher.setAAD(enc.encode(aad));
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(ciphertext), decipher.final()]).toString('utf8');
}

export function validateConfig({ relayBase, relayTopic, resultTopic, relayKey }) {
  const base = String(relayBase || 'https://ntfy.sh').replace(/\/+$/, '');
  const url = new URL(base);
  if (url.protocol !== 'https:') throw new Error('relay_base_must_use_https');
  if (!TOPIC_RE.test(String(relayTopic || ''))) throw new Error('invalid_relay_topic');
  if (!TOPIC_RE.test(String(resultTopic || ''))) throw new Error('invalid_result_topic');
  if (relayTopic === resultTopic) throw new Error('relay_topics_must_be_distinct');
  if (!RELAY_KEY_RE.test(String(relayKey || ''))) throw new Error('invalid_relay_key');
  return { relayBase: base, relayTopic, resultTopic, relayKey };
}

export function authorizeBearer(headerValue, expectedToken) {
  if (!expectedToken || expectedToken.length < 32) return false;
  const raw = String(headerValue || '');
  if (!raw.startsWith('Bearer ')) return false;
  const supplied = Buffer.from(raw.slice(7), 'utf8');
  const expected = Buffer.from(expectedToken, 'utf8');
  return supplied.length === expected.length && timingSafeEqual(supplied, expected);
}

export function normalizeBrowserPayload(op, payload = {}) {
  if (!BROWSER_OPS.has(op)) throw new Error('operation_not_allowed');
  if (op !== 'action') return {};
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) throw new Error('invalid_action_payload');
  const action = String(payload.action || '');
  if (!BROWSER_ACTIONS.has(action)) throw new Error('browser_action_not_allowed');
  const raw = JSON.stringify(payload);
  if (Buffer.byteLength(raw, 'utf8') > 24576) throw new Error('action_payload_too_large');
  return payload;
}

export function buildCommand({
  op,
  payload = {},
  relayKey,
  requestId = randomUUID(),
  expiresAtMs = Date.now() + 30000,
}) {
  if (!BROWSER_OPS.has(op)) throw new Error('operation_not_allowed');
  if (!REQUEST_ID_RE.test(requestId)) throw new Error('invalid_request_id');
  if (!RELAY_KEY_RE.test(String(relayKey || ''))) throw new Error('invalid_relay_key');
  if (!Number.isInteger(expiresAtMs) || expiresAtMs <= Date.now()) throw new Error('invalid_expiry');
  const safePayload = normalizeBrowserPayload(op, payload);
  const payloadB64 = b64url(Buffer.from(JSON.stringify(safePayload), 'utf8'));
  if (payloadB64.length > MAX_PAYLOAD_B64) throw new Error('payload_too_large');
  const canonical = `${requestId}\n${op}\n${expiresAtMs}\n${payloadB64}`;
  const signature = createHmac('sha256', relayKey).update(canonical, 'utf8').digest('hex');
  const envelope = { request_id: requestId, op, expires_at_ms: expiresAtMs, payload_b64: payloadB64, signature };
  const carrier = aesGcmEncrypt(JSON.stringify(envelope), relayKey, COMMAND_AAD, COMMAND_PREFIX);
  return { requestId, expiresAtMs, envelope, carrier };
}

export function decryptResult(carrier, relayKey) {
  const raw = aesGcmDecrypt(carrier, relayKey, RESULT_AAD, RESULT_PREFIX);
  const parsed = JSON.parse(raw);
  if (!REQUEST_ID_RE.test(String(parsed.request_id || ''))) throw new Error('invalid_result_request_id');
  return parsed;
}

export function encryptResultForTest(result, relayKey) {
  return aesGcmEncrypt(JSON.stringify(result), relayKey, RESULT_AAD, RESULT_PREFIX);
}

export function decryptCommandForTest(carrier, relayKey) {
  return JSON.parse(aesGcmDecrypt(carrier, relayKey, COMMAND_AAD, COMMAND_PREFIX));
}
