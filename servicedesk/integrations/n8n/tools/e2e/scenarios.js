// Cenários e2e: envia eventos ao n8n (webhooks de produção dos workflows publicados) e confere,
// no log do mock, as chamadas feitas ao sd-ops e ao Chatwoot. Dados fictícios.
const N8N = process.env.N8N_URL || 'http://sd-n8n:5678';
const MOCK = process.env.MOCK_URL || 'http://sd-mock:8080';
const TOKEN = process.env.HOOK_TOKEN || 'token-de-teste-e2e';
const sleep = ms => new Promise(r => setTimeout(r, ms));

function env(type, payload, extra = {}) {
  return { id: 'ev-' + Math.random().toString(16).slice(2), type, version: 1, tenant_id: 'dev55',
    occurred_at: new Date().toISOString(), source: 'sd-ops', correlation_id: 'corr-1', caused_by: null,
    subject: { call_id: 'c1', ticket_id: 't1', conversation_id: 99 }, payload, ...extra };
}

async function post(path, body, headers = {}) {
  const r = await fetch(N8N + '/webhook/' + path, { method: 'POST', body: JSON.stringify(body),
    headers: { 'content-type': 'application/json', 'x-sd-webhook-token': TOKEN, 'x-sd-origin': 'sd-ops',
      'x-sd-timestamp': String(Math.floor(Date.now() / 1000)), ...headers } });
  return r.status;
}

async function calls() { return (await fetch(MOCK + '/__log')).json(); }
async function reset() { await fetch(MOCK + '/__reset', { method: 'POST' }); }

const results = [];
async function scenario(name, fn, check, waitMs = 4000) {
  await reset();
  let status;
  try { status = await fn(); } catch (e) { status = 'erro: ' + e.message; }
  await sleep(waitMs);
  const log = await calls();
  let ok = false, why = '';
  try { const r = check(log, status); ok = r === true; why = r === true ? '' : String(r); } catch (e) { why = e.message; }
  results.push({ ok, name, status, why, calls: log.map(c => c.m + ' ' + c.p) });
}
const has = (log, m, re) => log.some(c => c.m === m && re.test(c.p));
const find = (log, m, re) => log.find(c => c.m === m && re.test(c.p));

(async () => {
  await scenario('WF03 perdida: prioridade alta, etiqueta mesclada, nota com sd_origin',
    () => post('sd/wf03-perdida', env('call.missed', { outcome: 'abandoned_queue', callback_task_id: 'cb1', call_id: 'c1', conversation_id: 99 })),
    log => {
      const pr = find(log, 'POST', /\/conversations\/99\/toggle_priority$/);
      const lb = find(log, 'POST', /\/conversations\/99\/labels$/);
      const nt = find(log, 'POST', /\/conversations\/99\/messages$/);
      if (!pr || pr.body.priority !== 'high') return 'sem toggle_priority high';
      if (!lb || !lb.body.labels.includes('55pbx') || !lb.body.labels.includes('retorno_pendente')) return 'etiquetas não mescladas';
      if (!nt || !nt.body.private || nt.body.content_attributes.sd_origin !== 'n8n:WF03') return 'nota sem private/sd_origin';
      if (log.some(c => c.h.origin !== 'n8n')) return 'chamada sem X-SD-Origin n8n';
      return true;
    });

  await scenario('WF03 anti-loop: evento causado pelo próprio WF03 não gera chamadas',
    () => post('sd/wf03-perdida', env('call.missed', { outcome: 'missed', conversation_id: 99 }, { caused_by: 'n8n:WF03' })),
    log => log.length === 0 || 'houve ' + log.length + ' chamadas');

  await scenario('WF03 sem token: n8n recusa (403) e nada é chamado',
    () => post('sd/wf03-perdida', env('call.missed', { conversation_id: 99 }), { 'x-sd-webhook-token': 'errado' }),
    (log, st) => (st === 403 && log.length === 0) || ('status ' + st + ', chamadas ' + log.length));

  await scenario('WF01 reserva: sem agente/time atribui o time da fila',
    () => post('sd/wf01-ligacao-recebida', env('call.started', { direction: 'receptivo', queue: '3855-FILA_SUPORTE_1', conversation_id: 99 })),
    log => {
      const a = find(log, 'POST', /\/conversations\/99\/assignments$/);
      if (!a || a.body.team_id !== 7) return 'sem atribuição ao time 7';
      return has(log, 'POST', /\/conversations\/99\/messages$/) || 'sem nota';
    });

  await scenario('WF02 gravação falhou: consulta a chamada e registra nota',
    () => post('sd/wf02-encerramento', env('recording.failed', { recording_id: 'r1', call_id: 'c1', reason: 'http_403' })),
    log => (has(log, 'GET', /\/sd-ops\/api\/v1\/calls\/c1$/) && has(log, 'POST', /\/conversations\/99\/messages$/)) || 'faltou GET call ou nota');

  await scenario('WF04 escalonamento: urgente, supervisor participante, nota',
    () => post('sd/wf04-escalonamento', env('ticket.escalated', { ticket_id: 't1', protocol: 'B2B-2026-000123', reason: 'cliente VIP' })),
    log => {
      const pr = find(log, 'POST', /toggle_priority$/);
      const pa = find(log, 'POST', /\/participants$/);
      if (!pr || pr.body.priority !== 'urgent') return 'sem urgent';
      if (!pa || JSON.stringify(pa.body.user_ids) !== '[3]') return 'sem participante 3';
      return has(log, 'POST', /\/conversations\/99\/messages$/) || 'sem nota';
    });

  await scenario('WF05 WhatsApp: opt-in -> reserva idempotente no sd-ops, contact_inbox, conversa, template, vínculo',
    () => post('sd/wf05-whatsapp-pos-atendimento', env('ticket.status_changed', { ticket_id: 't1', from: 'em_atendimento', to: 'resolvido' })),
    log => {
      const lg = find(log, 'POST', /\/notifications\/log$/);
      const msg = find(log, 'POST', /\/conversations\/321\/messages$/);
      if (!lg || lg.h.idem !== 'whatsapp_pos_atendimento:t1') return 'Idempotency-Key fixa ausente: ' + (lg && lg.h.idem);
      if (lg.body.dedupe_key !== 'whatsapp_pos_atendimento:t1') return 'dedupe_key ausente: ' + lg.body.dedupe_key;
      if (!msg || !msg.body.template_params || msg.body.template_params.processed_params['2'] !== 'B2B-2026-000123') return 'template ausente';
      return has(log, 'POST', /\/sd-ops\/api\/v1\/tickets\/t1\/links$/) || 'sem vínculo';
    }, 6000);

  await scenario('WF05 repetido: o sd-ops responde Idempotent-Replay e nada é enviado de novo (sem static data)',
    () => post('sd/wf05-whatsapp-pos-atendimento', env('ticket.status_changed', { ticket_id: 't1', to: 'resolvido' })),
    log => (has(log, 'POST', /\/notifications\/log$/) && !has(log, 'POST', /\/messages$/) &&
            !has(log, 'POST', /\/contact_inboxes$/)) || 'reenviou ou não consultou o sd-ops', 6000);

  await scenario('WF06 e-mail de protocolo (origem telefone): nova conversa de e-mail e vínculo',
    () => post('sd/wf06-email-protocolo', env('ticket.created', { ticket_id: 't1', protocol: 'B2B-2026-000123' })),
    log => {
      const m = find(log, 'POST', /\/conversations\/321\/messages$/);
      if (!m || !/B2B-2026-000123/.test(m.body.content) || m.body.private !== false) return 'e-mail sem protocolo';
      return has(log, 'POST', /\/sd-ops\/api\/v1\/tickets\/t1\/links$/) || 'sem vínculo';
    }, 6000);

  const cw = (content, type = 'incoming', senderType = 'contact') => ({ event: 'message_created', message_type: type, private: false,
    content, content_attributes: {}, sender: { id: 5, type: senderType }, conversation: { id: 99, meta: { sender: { id: 5 } } } });
  const SEG = process.env.WF08_SECRET || 'REPLACE_SEGREDO_LONGO';
  await scenario('WF08 cliente cita protocolo resolvido: reabre e vincula',
    () => fetch(N8N + '/webhook/sd/wf08-chatwoot-' + SEG, { method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify(cw('Olá, sobre o protocolo B2B-2026-000123 o problema voltou')) }).then(r => r.status),
    log => {
      const r = find(log, 'POST', /\/tickets\/t1\/reopen$/);
      if (!r || r.body.to !== 'em_atendimento') return 'reopen sem to=em_atendimento';
      const l = find(log, 'POST', /\/tickets\/t1\/links$/);
      return (l && l.body.conversation_id === 99) ? true : 'não vinculou a conversa 99';
    });

  await scenario('WF08 mensagem de agente citando protocolo: ignorada',
    () => fetch(N8N + '/webhook/sd/wf08-chatwoot-' + SEG, { method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify(cw('Seu protocolo é B2B-2026-000123', 'outgoing', 'user')) }).then(r => r.status),
    log => log.length === 0 || 'houve chamadas');

  await scenario('WF09 reconciliação manual: pede ao sd-ops e alerta quando não executou (sem chave)',
    () => post('sd/wf09-reconciliar', {}),
    log => {
      const r = find(log, 'POST', /\/reconciliations$/);
      if (!r || !r.body.from || !r.body.to) return 'sem janela';
      const a = find(log, 'POST', /\/conversations\/0\/messages$/);
      return (a && /NÃO EXECUTADA/.test(a.body.content)) ? true : 'sem alerta';
    }, 6000);

  await scenario('WF10 SLA violado: urgente, nota e alerta de operações',
    () => post('sd/wf10-sla', env('sla.breached', { ticket_id: 't1', protocol: 'B2B-2026-000123', metric: 'first_response', due_at: '2026-10-13T12:00:00Z', conversation_id: 99 })),
    log => (has(log, 'POST', /toggle_priority$/) && has(log, 'POST', /\/conversations\/99\/messages$/) && has(log, 'POST', /\/conversations\/0\/messages$/)) || 'faltou etapa');

  await scenario('WF11 QA crítico: nota com link do console e registro no ticket',
    () => post('sd/wf11-qa-critico', env('qa.completed', { evaluation_id: 'q1', score: 40, call_id: 'c1', critical_alerts: [{ type: 'reclamacao' }] })),
    log => {
      const n = find(log, 'POST', /\/conversations\/99\/messages$/);
      if (!n || !/qa\/avaliacoes\/q1/.test(n.body.content)) return 'nota sem link';
      const t = find(log, 'POST', /\/sd-ops\/api\/v1\/tickets\/t1\/notes$/);
      return (t && t.body.kind === 'nota_interna' && !!t.body.body) ? true : 'nota no ticket fora do contrato (kind/body)';
    });

  await scenario('WF11 QA bom: nada acontece',
    () => post('sd/wf11-qa-critico', env('qa.completed', { evaluation_id: 'q2', score: 92, call_id: 'c1' })),
    log => log.length === 0 || 'houve chamadas');

  let falhas = 0;
  for (const r of results) {
    console.log((r.ok ? 'OK    ' : 'FALHA ') + r.name + (r.ok ? '' : '  -> ' + r.why + ' | status ' + r.status + ' | ' + r.calls.join(', ')));
    if (!r.ok) falhas++;
  }
  console.log('cenários: ' + results.length + ' | falhas: ' + falhas);
  process.exit(falhas ? 1 : 0);
})();
