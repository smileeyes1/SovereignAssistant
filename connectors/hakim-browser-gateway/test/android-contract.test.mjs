import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const relayUrl = new URL(
  '../../../android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimDirectRelay.kt',
  import.meta.url,
);

test('gateway protocol remains locked to Android HC1/HR1 contract', async () => {
  const kotlin = await readFile(relayUrl, 'utf8');
  for (const invariant of [
    'private const val CARRIER_PREFIX = "HC1."',
    'private const val CARRIER_AAD = "HAKIM-CARRIER-v1"',
    'private const val RESULT_PREFIX = "HR1."',
    'private const val RESULT_AAD = "HAKIM-RESULT-v1"',
    'private const val GCM_NONCE_BYTES = 12',
    'private const val GCM_TAG_BITS = 128',
    'private const val MAX_PAYLOAD_B64 = 32768',
  ]) assert.equal(kotlin.includes(invariant), true, `Android protocol drift: ${invariant}`);

  assert.equal(kotlin.includes('"status"->localRequest(context,"GET","/v1/status"'), true);
  assert.equal(kotlin.includes('"ui"->localRequest(context,"GET","/v1/ui"'), true);
  assert.equal(kotlin.includes('"screenshot"->localRequest(context,"GET","/v1/screenshot"'), true);
  assert.equal(kotlin.includes('"action"->localRequest(context,"POST","/v1/action"'), true);
});
