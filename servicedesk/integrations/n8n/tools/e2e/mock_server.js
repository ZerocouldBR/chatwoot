// Mock do sd-ops (/sd-ops/api/v1) e da API do Chatwoot (/api/v1/accounts/1) para o e2e dos workflows.
// Só dados fictícios. Registra cada requisição em memória: GET /__log, POST /__reset.
const http = require('http');

let log = [];
const notif = new Map();   // dedupe_key -> registro (como ops.notification_logs, unique por tenant+chave)
// Formas iguais às do sd-ops (views.ticket_view / views.call_view, branch feat/integracao-55pbx 2201722d35)
const T = {
  id: 't1', protocol: 'B2B-2026-000123', protocol_numeric: '20260001237', status: 'resolvido', contact_id: 5,
  team_id: 7, channel: 'phone', origin: 'call', conversations: [99], calls: ['c1'], chatwoot_status: 'resolved',
};
const CALL = { id: 'c1', root_provider_call_id: '1760380000.1234', conversation_id: 99, recordings: [],
  tickets: [{ id: 't1', protocol: 'B2B-2026-000123', status: 'resolvido' }], callback: null };

function route(m, p, h, body) {
  // ---------------- sd-ops
  if (p.startsWith('/sd-ops/api/v1/')) {
    const r = p.slice('/sd-ops/api/v1'.length);
    if (m === 'GET' && r.startsWith('/tickets/')) {
      const id = decodeURIComponent(r.split('/')[2]);
      if (id.includes('999999')) return [404, { error: 'not_found', message: 'ticket inexistente' }];
      return [200, T];
    }
    if (m === 'GET' && r.startsWith('/calls/')) return [200, CALL];
    if (m === 'GET' && r === '/sla/at-risk') return [200, { items: [{ ticket_id: 't1', protocol: T.protocol, metric: 'first_response', due_at: '2026-10-14T12:00:00Z', breached: false }] }];
    if (m === 'GET' && (r === '/reports/summary' || r.startsWith('/metrics/'))) return [200, { recebidas: 70, atendidas: 60, tma_s: 163 }];
    if (m === 'POST' && r === '/notifications/log') {
      // igual ao sd-ops: 1ª vez 201; repetição 200 + Idempotent-Replay (o mesmo registro); sem chave 422
      const key = body.dedupe_key || h['idempotency-key'];
      if (!key) return [422, { error: 'dedupe_key_required', message: 'informe dedupe_key' }];
      if (notif.has(key)) return [200, { ...notif.get(key), ok: true, duplicate: true }, { 'Idempotent-Replay': 'true' }];
      const rec = { id: notif.size + 1, dedupe_key: key, status: body.status };
      notif.set(key, rec);
      return [201, { ok: true, duplicate: false, id: rec.id, dedupe_key: key }];
    }
    if (m === 'POST' && r === '/reconciliations') return [202, { skipped: 'PBX_API_KEY não configurada' }];
    if (m === 'POST' && /\/tickets\/[^/]+\/reopen$/.test(r)) return [200, { ...T, status: 'em_atendimento', followup_created: false }];
    if (m === 'POST') return [200, { ok: true, id: 'x1' }];
    return [404, { error: 'not_found' }];
  }
  // ---------------- Chatwoot
  const base = '/api/v1/accounts/1';
  if (p.startsWith(base)) {
    const r = p.slice(base.length);
    if (m === 'GET' && r === '/conversations/99') return [200, { id: 99, meta: {} }];
    if (m === 'GET' && r === '/teams') return [200, [{ id: 7, name: 'Suporte' }, { id: 8, name: 'Financeiro' }]];
    if (m === 'GET' && r.endsWith('/labels')) return [200, { payload: ['55pbx'] }];
    if (m === 'GET' && r === '/contacts/5') {
      return [200, { payload: { id: 5, name: 'Ana Teste', email: 'ana@exemplo.test', phone_number: '+5511900000000', custom_attributes: { sd_whatsapp_optin: true } } }];
    }
    if (m === 'POST' && r.endsWith('/contact_inboxes')) return [200, { id: 1, source_id: body.source_id }];
    if (m === 'POST' && r === '/conversations') return [200, { id: 321 }];
    if (m === 'POST') return [200, { id: 1 }];
    return [404, { error: 'not_found' }];
  }
  return [404, { error: 'rota desconhecida no mock' }];
}

http.createServer((req, res) => {
  let raw = '';
  req.on('data', c => { raw += c; });
  req.on('end', () => {
    const p = req.url.split('?')[0];
    if (p === '/__log') { res.writeHead(200, { 'content-type': 'application/json' }); return res.end(JSON.stringify(log)); }
    if (p === '/__reset') { log = []; res.writeHead(204); return res.end(); }   // o registro de envios persiste (como no sd-ops)
    let body = {};
    try { body = raw ? JSON.parse(raw) : {}; } catch (e) { body = { _raw: raw }; }
    const h = req.headers;
    log.push({
      m: req.method, p, q: req.url.split('?')[1] || '', body,
      h: { origin: h['x-sd-origin'], wf: h['x-sd-workflow'], idem: h['idempotency-key'],
        auth: h.authorization ? 'bearer' : (h.api_access_token ? 'api_access_token' : 'nenhuma') },
    });
    const [code, out, extra] = route(req.method, p, h, body);
    res.writeHead(code, { 'content-type': 'application/json', ...(extra || {}) });
    res.end(JSON.stringify(out));
  });
}).listen(8080, () => console.log('mock ouvindo em 8080'));
