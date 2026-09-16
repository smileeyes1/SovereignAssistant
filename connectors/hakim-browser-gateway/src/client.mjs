import { buildCommand, decryptResult, validateConfig } from './protocol.mjs';

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function parseEvents(text) {
  return String(text || '')
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => {
      try { return JSON.parse(line); } catch { return null; }
    })
    .filter(Boolean);
}

export class HakimBrowserRelayClient {
  constructor(config, fetchImpl = globalThis.fetch) {
    if (typeof fetchImpl !== 'function') throw new Error('fetch_unavailable');
    this.config = validateConfig(config);
    this.fetch = fetchImpl;
    this.timeoutMs = Math.min(Math.max(Number(config.timeoutMs || 25000), 3000), 60000);
  }

  async command(op, payload = {}, requestId = undefined) {
    const now = Date.now();
    const built = buildCommand({
      op,
      payload,
      relayKey: this.config.relayKey,
      requestId,
      expiresAtMs: now + Math.min(this.timeoutMs + 5000, 65000),
    });
    const postUrl = `${this.config.relayBase}/${this.config.relayTopic}`;
    const posted = await this.fetch(postUrl, {
      method: 'POST',
      headers: { 'content-type': 'text/plain; charset=utf-8' },
      body: built.carrier,
      signal: AbortSignal.timeout(Math.min(this.timeoutMs, 15000)),
    });
    if (!posted.ok) throw new Error(`relay_post_http_${posted.status}`);
    return this.waitForResult(built.requestId, now);
  }

  async waitForResult(requestId, startedAtMs) {
    const deadline = startedAtMs + this.timeoutMs;
    let cursor = '2m';
    while (Date.now() < deadline) {
      const remaining = deadline - Date.now();
      const resultUrl = `${this.config.relayBase}/${this.config.resultTopic}/json?since=${encodeURIComponent(cursor)}&poll=1`;
      const response = await this.fetch(resultUrl, {
        method: 'GET',
        headers: { accept: 'application/x-ndjson, application/json' },
        signal: AbortSignal.timeout(Math.min(Math.max(remaining, 1000), 10000)),
      });
      if (!response.ok) throw new Error(`result_poll_http_${response.status}`);
      if (response.headers?.get?.('x-messages-truncated') === '1') {
        throw new Error('result_poll_truncated');
      }
      const events = parseEvents(await response.text());
      let newestId = null;
      for (const event of events) {
        const eventId = String(event.id || '').trim();
        if (eventId) newestId = eventId;
        if (event.event && event.event !== 'message') continue;
        const carrier = String(event.message || '').trim();
        if (!carrier.startsWith('HR1.')) continue;
        let decoded;
        try { decoded = decryptResult(carrier, this.config.relayKey); } catch { continue; }
        if (decoded.request_id === requestId) {
          return {
            connector_round_trip: 'PROVEN',
            request_id: requestId,
            status: decoded.status,
            received_at_ms: decoded.received_at_ms,
            result: decoded.result,
            field_verified: false,
          };
        }
      }
      if (newestId) cursor = newestId;
      await sleep(Math.min(650, Math.max(deadline - Date.now(), 0)));
    }
    throw new Error('phone_round_trip_timeout');
  }
}

export function configFromEnv(env = process.env) {
  return {
    relayBase: env.HAKIM_RELAY_BASE || 'https://ntfy.sh',
    relayTopic: env.HAKIM_RELAY_TOPIC,
    resultTopic: env.HAKIM_RESULT_TOPIC,
    relayKey: env.HAKIM_RELAY_KEY,
    timeoutMs: env.HAKIM_REQUEST_TIMEOUT_MS || 25000,
  };
}
