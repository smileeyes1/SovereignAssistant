import { HakimBrowserRelayClient, configFromEnv } from '../src/client.mjs';
import { authorizeBearer, BROWSER_OPS, normalizeBrowserPayload, validateConfig } from '../src/protocol.mjs';

function reply(res, status, body) {
  res.statusCode = status;
  res.setHeader('content-type', 'application/json; charset=utf-8');
  res.setHeader('cache-control', 'no-store');
  res.end(JSON.stringify(body));
}

function parsedBody(req) {
  if (req.body && typeof req.body === 'object' && !Buffer.isBuffer(req.body)) return req.body;
  const raw = typeof req.body === 'string' ? req.body : Buffer.isBuffer(req.body) ? req.body.toString('utf8') : '';
  if (Buffer.byteLength(raw, 'utf8') > 65536) throw new Error('request_too_large');
  return raw ? JSON.parse(raw) : {};
}

function serviceConfig() {
  const connectorToken = process.env.HAKIM_CONNECTOR_TOKEN || '';
  if (connectorToken.length < 32) throw new Error('connector_token_not_configured');
  const relay = validateConfig(configFromEnv(process.env));
  return { connectorToken, relay };
}

export default async function handler(req, res) {
  let cfg;
  try { cfg = serviceConfig(); }
  catch { return reply(res, 503, { ok: false, error: 'connector_not_configured', field_verified: false }); }

  if (!authorizeBearer(req.headers?.authorization, cfg.connectorToken)) {
    return reply(res, 401, { ok: false, error: 'unauthorized' });
  }

  if (req.method === 'GET') {
    return reply(res, 200, {
      ok: true,
      service: 'HAKIM_BROWSER_CONNECTOR',
      configured: true,
      scope: 'OWNED_BROWSER_ONLY',
      phone_round_trip: 'NOT_TESTED_BY_BASIC_HEALTH',
      field_verified: false,
    });
  }

  if (req.method !== 'POST') return reply(res, 405, { ok: false, error: 'method_not_allowed' });

  let body;
  try { body = parsedBody(req); }
  catch (e) { return reply(res, 400, { ok: false, error: e.message === 'request_too_large' ? e.message : 'invalid_json' }); }

  const op = String(body.op || '');
  if (!BROWSER_OPS.has(op)) return reply(res, 400, { ok: false, error: 'operation_not_allowed' });
  let payload;
  try { payload = normalizeBrowserPayload(op, body.payload || {}); }
  catch (e) { return reply(res, 400, { ok: false, error: e.message }); }

  try {
    const client = new HakimBrowserRelayClient(cfg.relay);
    const result = await client.command(op, payload, body.request_id || undefined);
    return reply(res, 200, {
      ok: true,
      scope: 'OWNED_BROWSER_ONLY',
      mutation_requires_phone_approval: op === 'action',
      ...result,
    });
  } catch (e) {
    const message = String(e?.message || 'connector_error');
    const status = message === 'phone_round_trip_timeout' ? 504 :
      message.startsWith('relay_') || message.startsWith('result_poll_') ? 502 : 400;
    return reply(res, status, { ok: false, error: message, field_verified: false });
  }
}
