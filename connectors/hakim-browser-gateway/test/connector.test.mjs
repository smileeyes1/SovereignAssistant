import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { HakimBrowserRelayClient } from '../src/client.mjs';
import {
  authorizeBearer,
  buildCommand,
  decryptCommandForTest,
  decryptResult,
  encryptResultForTest,
  normalizeBrowserPayload,
  validateConfig,
} from '../src/protocol.mjs';

const relayKey = 'A'.repeat(48);
const relayTopic = 'hakim_command_topic_123456789';
const resultTopic = 'hakim_result_topic_1234567890';
const config = { relayBase: 'https://ntfy.sh', relayTopic, resultTopic, relayKey, timeoutMs: 4000 };

test('HC1 envelope matches Android canonical signature and ciphertext contract', () => {
  const requestId = 'connector-test-0001';
  const expiresAtMs = Date.now() + 30000;
  const built = buildCommand({ op: 'action', payload: { action: 'browser_reload' }, relayKey, requestId, expiresAtMs });
  assert.match(built.carrier, /^HC1\./);
  const env = decryptCommandForTest(built.carrier, relayKey);
  assert.equal(env.request_id, requestId);
  assert.equal(env.op, 'action');
  const canonical = `${env.request_id}\n${env.op}\n${env.expires_at_ms}\n${env.payload_b64}`;
  const expected = createHmac('sha256', relayKey).update(canonical, 'utf8').digest('hex');
  assert.equal(env.signature, expected);
  assert.deepEqual(JSON.parse(Buffer.from(env.payload_b64, 'base64url').toString('utf8')), { action: 'browser_reload' });
});

test('HR1 result decrypts and remains bound to request id', () => {
  const raw = { request_id: 'connector-test-0002', status: 'ok', received_at_ms: Date.now(), result: { ok: true } };
  const carrier = encryptResultForTest(raw, relayKey);
  assert.match(carrier, /^HR1\./);
  assert.deepEqual(decryptResult(carrier, relayKey), raw);
  assert.throws(() => decryptResult(carrier, 'B'.repeat(48)));
});

test('browser connector fails closed outside owned-browser scope', () => {
  assert.throws(() => buildCommand({ op: 'launch', relayKey }), /operation_not_allowed/);
  assert.throws(() => normalizeBrowserPayload('action', { action: 'device_tap', x: 1, y: 1 }), /browser_action_not_allowed/);
  assert.deepEqual(normalizeBrowserPayload('status', { ignored: true }), {});
});

test('connector authentication and relay config are fail closed', () => {
  const token = 't'.repeat(48);
  assert.equal(authorizeBearer(`Bearer ${token}`, token), true);
  assert.equal(authorizeBearer('Bearer wrong', token), false);
  assert.throws(() => validateConfig({ ...config, relayBase: 'http://ntfy.sh' }), /https/);
  assert.throws(() => validateConfig({ ...config, resultTopic: relayTopic }), /distinct/);
});

test('relay client proves a matching encrypted round trip', async () => {
  let outbound;
  const fakeFetch = async (url, options = {}) => {
    if (options.method === 'POST') {
      outbound = decryptCommandForTest(String(options.body), relayKey);
      return new Response('ok', { status: 200 });
    }
    const result = {
      request_id: outbound.request_id,
      status: 'ok',
      received_at_ms: Date.now(),
      result: { ok: true, safe_core: true, browser: { attached: true } },
    };
    const line = JSON.stringify({ event: 'message', message: encryptResultForTest(result, relayKey) });
    return new Response(line + '\n', { status: 200 });
  };
  const client = new HakimBrowserRelayClient(config, fakeFetch);
  const response = await client.command('status', {});
  assert.equal(response.connector_round_trip, 'PROVEN');
  assert.equal(response.request_id, outbound.request_id);
  assert.equal(response.result.safe_core, true);
  assert.equal(response.field_verified, false);
});

test('OpenAPI surface contains no shell, launch, notification or device-wide operation', async () => {
  const api = JSON.parse(await readFile(new URL('../openapi.json', import.meta.url), 'utf8'));
  const body = JSON.stringify(api);
  for (const forbidden of ['shell', 'launch', 'notifications', 'device/action', 'device/screenshot']) {
    assert.equal(body.includes(forbidden), false, `forbidden surface leaked: ${forbidden}`);
  }
  const op = api.paths['/api/connector'].post.requestBody.content['application/json'].schema.properties.op;
  assert.deepEqual(op.enum, ['status', 'ui', 'screenshot', 'action']);
});
