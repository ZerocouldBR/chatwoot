#!/usr/bin/env python3
"""Gera os workflows n8n WF00-WF12 do ServiceDesk (JSON de importação).

Uso:  python3 tools/build_workflows.py            (grava em workflows/)
      python3 tools/build_workflows.py --check    (só compara com o que está gravado)

Regras (ver README.md):
- nenhum segredo no JSON: credenciais só por referência (id REPLACE_*), URLs base num nó "config";
- toda chamada ao sd-ops leva X-SD-Origin: n8n, X-SD-Workflow e Idempotency-Key;
- toda escrita no Chatwoot leva content_attributes.sd_origin (mensagens) ou merge=true (atributos);
- nós e versões compatíveis com a instância do cliente (versões já usadas na exportação de 219 workflows).
Python 3.9+ sem dependências.
"""
import json
import os
import re
import sys
import uuid

NS = uuid.UUID("5d0c1b7e-6a43-4f7e-9c55-2b1d0e7a1f00")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "workflows"))

CRED_SDOPS = {"httpHeaderAuth": {"id": "REPLACE_CRED_SDOPS_SERVICE_TOKEN", "name": "SD-OPS: token de serviço do n8n (Authorization: Bearer)"}}
CRED_CHATWOOT = {"httpHeaderAuth": {"id": "REPLACE_CRED_CHATWOOT_N8N", "name": "ServiceDesk/Chatwoot: api_access_token da Integração n8n"}}
CRED_HOOK = {"httpHeaderAuth": {"id": "REPLACE_CRED_SDOPS_WEBHOOK_TOKEN", "name": "SD-OPS -> n8n: X-SD-Webhook-Token"}}

CONFIG_BASE = [
    ("sdops_base_url", "string", "https://SERVICEDESK.EXEMPLO/sd-ops/api/v1"),
    ("chatwoot_base_url", "string", "https://SERVICEDESK.EXEMPLO"),
    ("chatwoot_account_id", "number", 1),
    ("ops_alert_conversation_id", "number", 0),
    ("console_base_url", "string", "https://SERVICEDESK.EXEMPLO/sd-console"),
]

SDOPS_PATHS = {}  # (wf) -> set de "MÉTODO caminho" (para o README e a conferência com o OpenAPI do A2)


def nid(wf, name):
    return str(uuid.uuid5(NS, "%s:%s" % (wf, name)))


class WF:
    def __init__(self, code, title, description):
        self.wfc = code
        self.name = "SD %s - %s" % (code, title)
        self.description = description
        self.nodes = []
        self.conn = {}
        self.x = 0

    # ------------------------------------------------------------ base
    def add(self, name, type_, ver, params, pos, creds=None, **extra):
        node = {"parameters": params, "id": nid(self.wfc, name), "name": name, "type": type_,
                "typeVersion": ver, "position": list(pos)}
        if creds:
            node["credentials"] = creds
        node.update(extra)
        self.nodes.append(node)
        return name

    def link(self, a, b, out=0):
        outs = self.conn.setdefault(a, {"main": []})["main"]
        while len(outs) <= out:
            outs.append([])
        outs[out].append({"node": b, "type": "main", "index": 0})

    def chain(self, *names):
        for a, b in zip(names, names[1:]):
            self.link(a, b)

    # ------------------------------------------------------------ nós prontos
    def sd_webhook(self, path, pos):
        return self.add("webhook_sd_ops", "n8n-nodes-base.webhook", 2,
                        {"httpMethod": "POST", "path": path, "authentication": "headerAuth", "options": {}},
                        pos, CRED_HOOK, webhookId=nid(self.wfc, "webhook:" + path))

    def config(self, extra, pos, name="config"):
        assigns = []
        for i, (k, t, v) in enumerate(CONFIG_BASE + list(extra)):
            assigns.append({"id": nid(self.wfc, "cfg:%s:%d" % (k, i)), "name": k, "type": t, "value": v})
        return self.add(name, "n8n-nodes-base.set", 3.4,
                        {"assignments": {"assignments": assigns}, "options": {}}, pos)

    def code(self, name, js, pos):
        return self.add(name, "n8n-nodes-base.code", 2, {"jsCode": js.strip() + "\n"}, pos)

    def noop(self, name, pos):
        return self.add(name, "n8n-nodes-base.noOp", 1, {}, pos)

    def wait_minutes(self, name, minutes, pos):
        return self.add(name, "n8n-nodes-base.wait", 1.1, {"amount": minutes, "unit": "minutes"}, pos,
                        webhookId=nid(self.wfc, "wait:" + name))

    def schedule_cron(self, name, cron, pos):
        return self.add(name, "n8n-nodes-base.scheduleTrigger", 1.2,
                        {"rule": {"interval": [{"field": "cronExpression", "expression": cron}]}}, pos)

    def if_true(self, name, expr, pos):
        cond = {"id": nid(self.wfc, "if:" + name), "leftValue": expr, "rightValue": "",
                "operator": {"type": "boolean", "operation": "true", "singleValue": True}}
        return self.add(name, "n8n-nodes-base.if", 2.2, {
            "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                           "conditions": [cond], "combinator": "and"},
            "options": {}}, pos)

    def switch(self, name, expr, keys, pos):
        rules = []
        for k in keys:
            rules.append({"conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                "conditions": [{"id": nid(self.wfc, "sw:%s:%s" % (name, k)), "leftValue": expr, "rightValue": k,
                                "operator": {"type": "string", "operation": "equals"}}],
                "combinator": "and"}, "renameOutput": True, "outputKey": k})
        return self.add(name, "n8n-nodes-base.switch", 3.2, {"rules": {"values": rules}, "options": {}}, pos)

    def _http(self, name, method, url, body, pos, creds, headers, never_error=False, timeout=15000, query=None):
        p = {"method": method, "url": url, "authentication": "genericCredentialType",
             "genericAuthType": "httpHeaderAuth", "sendHeaders": True,
             "headerParameters": {"parameters": [{"name": k, "value": v} for k, v in headers]},
             "options": {"timeout": timeout}}
        if method == "GET":
            del p["method"]  # GET é o padrão do nó
        if query:
            p["sendQuery"] = True
            p["queryParameters"] = {"parameters": [{"name": k, "value": v} for k, v in query]}
        if body is not None:
            p["sendBody"] = True
            p["specifyBody"] = "json"
            p["jsonBody"] = body
        if never_error:
            p["options"]["response"] = {"response": {"neverError": True, "fullResponse": True}}
        return self.add(name, "n8n-nodes-base.httpRequest", 4.2, p, pos, creds,
                        retryOnFail=True, maxTries=3, waitBetweenTries=2000)

    def sdops(self, name, method, path, body, pos, never_error=False, timeout=15000, query=None):
        SDOPS_PATHS.setdefault(self.wfc, set()).add("%s %s" % (method, re.sub(r"\{\{[^}]*\}\}", "{id}", path.split("?")[0])))
        url = "={{ $('config').first().json.sdops_base_url }}" + path_expr(path)
        headers = [("X-SD-Origin", "n8n"), ("X-SD-Workflow", self.wfc),
                   ("Idempotency-Key", "={{ $execution.id }}:%s:{{ $itemIndex }}" % name)]
        return self._http(name, method, url, body, pos, CRED_SDOPS, headers, never_error, timeout, query)

    def chatwoot(self, name, method, path, body, pos, never_error=False):
        url = ("={{ $('config').first().json.chatwoot_base_url }}/api/v1/accounts/"
               "{{ $('config').first().json.chatwoot_account_id }}" + path_expr(path))
        return self._http(name, method, url, body, pos, CRED_CHATWOOT, [("X-SD-Origin", "n8n")], never_error)

    def private_note(self, name, conv_expr, text_expr, pos):
        """Nota privada no Chatwoot com marca de origem (anti-loop) e source_id idempotente."""
        body = ("={{ JSON.stringify({ content: %s, message_type: 'outgoing', private: true, "
                "source_id: 'n8n:%s:' + $execution.id + ':%s:' + $itemIndex, "
                "content_attributes: { sd_origin: 'n8n:%s' } }) }}") % (text_expr, self.wfc, name, self.wfc)
        return self.chatwoot(name, "POST", "/conversations/{{ %s }}/messages" % conv_expr, body, pos)

    def ops_alert(self, name, text_expr, pos):
        return self.private_note(name, "$('config').first().json.ops_alert_conversation_id", text_expr, pos)

    def to_json(self):
        return {
            "name": self.name,
            "nodes": self.nodes,
            "connections": self.conn,
            "active": False,
            "settings": {"executionOrder": "v1", "timezone": "America/Sao_Paulo",
                         "saveDataErrorExecution": "all", "saveDataSuccessExecution": "none"},
            "pinData": {},
            "meta": {"templateCredsSetupCompleted": False, "servicedesk": {
                "workflow": self.wfc, "description": self.description,
                "generator": "servicedesk/integrations/n8n/tools/build_workflows.py", "format_version": 1}},
        }


def path_expr(path):
    """'/tickets/{{ x }}' já vem com expressão; só garante a barra."""
    return path if path.startswith("/") else "/" + path


# ---------------------------------------------------------------- código JS comum
def js_valida(wf, aceitos, extra_filter=""):
    return """
// %(wf)s: valida o envelope do sd-ops (WEBHOOK_CONTRACTS.md §8.2/§8.3) e aplica o anti-loop.
// O token do header X-SD-Webhook-Token já foi conferido pelo nó Webhook (credencial Header Auth).
const WF = '%(wf)s';
const ACEITOS = %(aceitos)s;
const entrada = $input.first().json;
const h = entrada.headers || {};
const ev = entrada.body || {};
if ((h['x-sd-origin'] || '') !== 'sd-ops') {
  throw new Error('Origem inesperada no header X-SD-Origin: ' + (h['x-sd-origin'] || '(vazio)'));
}
if (!ev.id || !ev.type) throw new Error('Envelope sem id/type');
if (!ACEITOS.includes(ev.type)) return [];           // outro tipo: ignora sem erro
const ts = parseInt(h['x-sd-timestamp'] || '0', 10);
if (ts && Math.abs(Date.now() / 1000 - ts) > 900) return [];  // fora da janela (reenvio antigo)
if (String(ev.caused_by || '').startsWith('n8n:' + WF)) return [];  // causado por este workflow
const p = ev.payload || {};
const s = ev.subject || {};
const out = {
  event_id: ev.id, type: ev.type, tenant_id: ev.tenant_id, correlation_id: ev.correlation_id || null,
  payload: p,
  call_id: p.call_id || s.call_id || null,
  ticket_id: p.ticket_id || s.ticket_id || null,
  conversation_id: p.conversation_id || s.conversation_id || null,
};
%(extra)s
return [{ json: out }];
""" % {"wf": wf, "aceitos": json.dumps(aceitos), "extra": extra_filter}


def js_dedupe(chave_expr, dias=30):
    """Alerta INTERNO no máximo 1 vez por chave (static data do workflow; hoje só o WF10, aviso de SLA em risco).
    Envios ao CLIENTE (WF05/WF06/WF07) não usam isto: a garantia "1 vez por ticket" é do sd-ops
    (POST /notifications/log idempotente por dedupe_key, 200 + Idempotent-Replay na repetição)."""
    return """
const sd = $getWorkflowStaticData('global');
sd.enviados = sd.enviados || {};
const agora = Date.now();
for (const [k, t] of Object.entries(sd.enviados)) if (agora - t > %d * 86400000) delete sd.enviados[k];
const out = [];
for (const it of $input.all()) {
  const chave = %s;
  if (sd.enviados[chave]) continue;          // já enviado/alertado: não repete
  sd.enviados[chave] = agora;                // reserva antes do envio (no máximo uma vez)
  out.push({ json: { ...it.json, chave } });
}
return out;
""" % (dias, chave_expr)


# ---------------------------------------------------------------- WF00
def wf00():
    w = WF("WF00", "Erros dos workflows (alerta)",
           "Workflow de erro: publica no ticket interno de operações uma nota com o workflow, o nó e a mensagem. "
           "Configure-o como 'Error workflow' nas Settings dos WF01-WF12.")
    t = w.add("erro_trigger", "n8n-nodes-base.errorTrigger", 1, {}, (0, 0))
    c = w.config([], (220, 0))
    f = w.code("formata_erro", """
const e = $('erro_trigger').first().json;
const wf = (e.workflow && e.workflow.name) || '?';
const ex = e.execution || {};
const msg = ((ex.error && ex.error.message) || 'sem mensagem').slice(0, 500);
// sem dados pessoais: só nomes técnicos e mensagem de erro (que não deve conter payload)
return [{ json: { texto: '[n8n] Falha em ' + wf + ' / nó ' + (ex.lastNodeExecuted || '?') +
  ' / execução ' + (ex.id || '?') + ': ' + msg } }];
""", (440, 0))
    n = w.ops_alert("alerta_operacoes", "$json.texto", (660, 0))
    w.chain(t, c, f, n)
    return w


# ---------------------------------------------------------------- WF01
def wf01():
    w = WF("WF01", "Ligação recebida (atribuição de reserva e aviso)",
           "call.started -> confere a conversa criada pelo sd-ops; se ficou sem agente e sem time, atribui o time "
           "pela fila (mapa configurável) e registra nota. Contato, ticket e conversa são do sd-ops (transacional).")
    a = w.sd_webhook("sd/wf01-ligacao-recebida", (0, 0))
    v = w.code("valida_evento", js_valida("WF01", ["call.started"],
               "if (p.direction === 'interno') return [];"), (220, 0))
    c = w.config([("fallback_enabled", "boolean", True),
                  ("queue_team_map", "string",
                   '{"FILA_SUPORTE_1":"Suporte","CHECKOUT_N2":"Suporte","FILA_FINANCEIRO_1":"Financeiro","FILA_NOVOS_NEGOCIOS":"Novos Negócios","TARIFAS_E_DISPONIBILIDADE":"Treinamento","FILA_INTEGRACOES":"Treinamento"}')],
                 (440, 0))
    i = w.if_true("tem_conversa", "={{ !!$('valida_evento').first().json.conversation_id }}", (660, 0))
    sem = w.noop("sem_conversa_ainda", (880, 160))
    g = w.chatwoot("busca_conversa", "GET", "/conversations/{{ $('valida_evento').first().json.conversation_id }}",
                   None, (880, -40))
    t = w.chatwoot("lista_times", "GET", "/teams", None, (1100, -40))
    d = w.code("decide_reserva", """
// Só age se o sd-ops não conseguiu atribuir (sem agente e sem time) e a reserva estiver ligada.
const cfg = $('config').first().json;
const ev = $('valida_evento').first().json;
const conv = $('busca_conversa').first().json;
const meta = conv.meta || {};
if (!cfg.fallback_enabled) return [];
if (meta.assignee || meta.team || conv.team_id) return [];
let mapa = {};
try { mapa = JSON.parse(cfg.queue_team_map || '{}'); } catch (e) { throw new Error('queue_team_map inválido'); }
const fila = String(ev.payload.queue || '').replace(/^\\d+\\s*-\\s*/, '');
const nomeTime = mapa[fila];
if (!nomeTime) return [];
// O nó HTTP do n8n divide resposta em array em vários itens: juntar todos (e aceitar {payload: [...]}).
const lista = $('lista_times').all().map(i => i.json).flatMap(j => Array.isArray(j.payload) ? j.payload : [j]);
const t = lista.find(x => String(x.name).toLowerCase() === nomeTime.toLowerCase());
if (!t) return [];
return [{ json: { conversation_id: ev.conversation_id, team_id: t.id, time: t.name, fila } }];
""", (1320, -40))
    at = w.chatwoot("atribui_time", "POST", "/conversations/{{ $json.conversation_id }}/assignments",
                    "={{ JSON.stringify({ team_id: $json.team_id }) }}", (1540, -40))
    n = w.private_note("nota_atribuicao", "$('decide_reserva').first().json.conversation_id",
                       "'Atribuído ao time ' + $('decide_reserva').first().json.time + ' pela fila ' + "
                       "$('decide_reserva').first().json.fila + ' (WF01, reserva: o sd-ops não tinha agente/time).'",
                       (1760, -40))
    w.chain(a, v, c, i)
    w.link(i, g, 0)
    w.link(i, sem, 1)
    w.chain(g, t, d, at, n)
    return w


# ---------------------------------------------------------------- WF02
def wf02():
    w = WF("WF02", "Encerramento da ligação (gravação, transcrição e QA)",
           "call.ended/recording.stored/recording.failed -> acompanha o pipeline: se a gravação não chegar ao "
           "storage em 60 min, alerta; falha permanente vira nota no ticket. Download, transcrição e QA são "
           "feitos pelo sd-ops e pelo qa-pipeline (A3), nunca no n8n.")
    a = w.sd_webhook("sd/wf02-encerramento", (0, 0))
    v = w.code("valida_evento", js_valida("WF02", ["call.ended", "recording.stored", "recording.failed"]), (220, 0))
    c = w.config([("espera_gravacao_min", "number", 60)], (440, 0))
    s = w.switch("por_tipo", "={{ $('valida_evento').first().json.type }}",
                 ["call.ended", "recording.stored", "recording.failed"], (660, 0))
    # call.ended
    i = w.if_true("espera_gravacao", "={{ !!$('valida_evento').first().json.payload.has_recording_url }}", (880, -200))
    wt = w.wait_minutes("aguarda_60min", 60, (1100, -220))
    g = w.sdops("consulta_chamada", "GET", "/calls/{{ $('valida_evento').first().json.call_id }}", None, (1320, -220))
    k = w.code("gravacao_chegou", """
const call = $('consulta_chamada').first().json;
const recs = call.recordings || [];
const ok = recs.some(r => ['stored', 'ok', 'done'].includes(String(r.status || r.state)));
if (ok) return [];
return [{ json: { texto: '[WF02] Gravação da chamada ' + (call.id || '?') + ' (provedor ' +
  (call.provider_call_id || '?') + ') ainda não está no storage 60 min após o fim. Ver /sd-ops health e acesso a vsa19.55pbx.com.' } }];
""", (1540, -220))
    al = w.ops_alert("alerta_gravacao_atrasada", "$json.texto", (1760, -220))
    sem = w.noop("sem_gravacao_esperada", (1100, -60))
    # recording.stored
    st = w.noop("qa_consome_do_stream", (880, 0))
    # recording.failed
    g2 = w.sdops("consulta_chamada_falha", "GET", "/calls/{{ $('valida_evento').first().json.call_id }}", None, (880, 200))
    k2 = w.code("prepara_nota_falha", """
const ev = $('valida_evento').first().json;
const call = $('consulta_chamada_falha').first().json;
const conv = call.conversation_id || (call.conversations || [])[0] || ev.conversation_id;
const texto = 'Gravação indisponível para esta ligação (' + (ev.payload.reason || 'motivo não informado') +
  '). Transcrição e QA não serão gerados automaticamente.';
return [{ json: { conversation_id: conv, texto } }];
""", (1100, 200))
    i2 = w.if_true("tem_conversa", "={{ !!$json.conversation_id }}", (1320, 200))
    n2 = w.private_note("nota_gravacao_falhou", "$json.conversation_id", "$json.texto", (1540, 180))
    al2 = w.ops_alert("alerta_gravacao_falhou", "'[WF02] ' + $('prepara_nota_falha').first().json.texto", (1540, 340))
    w.chain(a, v, c, s)
    w.link(s, i, 0)
    w.link(s, st, 1)
    w.link(s, g2, 2)
    w.link(i, wt, 0)
    w.link(i, sem, 1)
    w.chain(wt, g, k, al)
    w.chain(g2, k2, i2)
    w.link(i2, n2, 0)
    w.link(i2, al2, 1)
    return w


# ---------------------------------------------------------------- WF03
def wf03():
    w = WF("WF03", "Ligação perdida (callback, prioridade e aviso)",
           "call.missed -> o sd-ops já criou a tarefa de retorno (callback_task_id) e o ticket conforme a política; "
           "o workflow sobe a prioridade da conversa, marca a etiqueta de retorno e avisa o time.")
    a = w.sd_webhook("sd/wf03-perdida", (0, 0))
    v = w.code("valida_evento", js_valida("WF03", ["call.missed"]), (220, 0))
    c = w.config([("prioridade_perdida", "string", "high"), ("etiqueta_retorno", "string", "retorno_pendente")], (440, 0))
    i = w.if_true("tem_conversa", "={{ !!$('valida_evento').first().json.conversation_id }}", (660, 0))
    pr = w.chatwoot("prioridade", "POST", "/conversations/{{ $('valida_evento').first().json.conversation_id }}/toggle_priority",
                    "={{ JSON.stringify({ priority: $('config').first().json.prioridade_perdida }) }}", (880, -60))
    gl = w.chatwoot("etiquetas_atuais", "GET", "/conversations/{{ $('valida_evento').first().json.conversation_id }}/labels",
                    None, (1100, -60))
    ml = w.code("junta_etiquetas", """
// POST /labels sobrescreve a lista: junta as atuais com a de retorno.
const atuais = ($('etiquetas_atuais').first().json.payload) || [];
const nova = $('config').first().json.etiqueta_retorno;
return [{ json: { labels: Array.from(new Set(atuais.concat([nova]))) } }];
""", (1320, -60))
    pl = w.chatwoot("grava_etiquetas", "POST", "/conversations/{{ $('valida_evento').first().json.conversation_id }}/labels",
                    "={{ JSON.stringify({ labels: $json.labels }) }}", (1540, -60))
    n = w.private_note("nota_retorno", "$('valida_evento').first().json.conversation_id",
                       "'Ligação perdida (' + $('valida_evento').first().json.payload.outcome + '). Tarefa de retorno ' + "
                       "($('valida_evento').first().json.payload.callback_task_id || '-') + ' criada. Ligue de volta pelo CTI.'",
                       (1760, -60))
    al = w.ops_alert("alerta_sem_conversa",
                     "'[WF03] Ligação perdida sem conversa vinculada (chamada ' + $('valida_evento').first().json.call_id + "
                     "', retorno ' + ($('valida_evento').first().json.payload.callback_task_id || '-') + ').'", (880, 160))
    w.chain(a, v, c, i)
    w.link(i, pr, 0)
    w.link(i, al, 1)
    w.chain(pr, gl, ml, pl, n)
    return w


# ---------------------------------------------------------------- WF04
def wf04():
    w = WF("WF04", "Escalonamento (supervisor, prioridade, aviso)",
           "ticket.escalated -> prioridade urgente na conversa, supervisores do time como participantes e nota interna. "
           "O SLA é recalculado pelo sd-ops.")
    a = w.sd_webhook("sd/wf04-escalonamento", (0, 0))
    v = w.code("valida_evento", js_valida("WF04", ["ticket.escalated"]), (220, 0))
    c = w.config([("supervisores_por_time", "string", '{"*": []}')], (440, 0))
    g = w.sdops("consulta_ticket", "GET", "/tickets/{{ $('valida_evento').first().json.ticket_id }}", None, (660, 0))
    d = w.code("prepara", """
const ev = $('valida_evento').first().json;
const t = $('consulta_ticket').first().json;
let mapa = {};
try { mapa = JSON.parse($('config').first().json.supervisores_por_time || '{}'); } catch (e) { throw new Error('supervisores_por_time inválido'); }
const conv = ev.conversation_id || (t.conversations || [])[0] || null;   // sd-ops: conversations = [ids], a 1ª é a primária
const sup = (mapa[String(t.team_id || ev.payload.team_id)] || mapa['*'] || []).map(Number).filter(Boolean);
return [{ json: { conversation_id: conv, supervisores: sup, protocolo: t.protocol || ev.payload.protocol,
  nivel: t.escalation_level || '', motivo: ev.payload.reason || '' } }];
""", (880, 0))
    i = w.if_true("tem_conversa", "={{ !!$json.conversation_id }}", (1100, 0))
    pr = w.chatwoot("prioridade_urgente", "POST", "/conversations/{{ $('prepara').first().json.conversation_id }}/toggle_priority",
                    "={{ JSON.stringify({ priority: 'urgent' }) }}", (1320, -60))
    i2 = w.if_true("tem_supervisor", "={{ $('prepara').first().json.supervisores.length > 0 }}", (1540, -60))
    pa = w.chatwoot("adiciona_supervisores", "POST", "/conversations/{{ $('prepara').first().json.conversation_id }}/participants",
                    "={{ JSON.stringify({ user_ids: $('prepara').first().json.supervisores }) }}", (1760, -120))
    n = w.private_note("nota_escalonamento", "$('prepara').first().json.conversation_id",
                       "'Ticket ' + $('prepara').first().json.protocolo + ' escalonado (nível ' + $('prepara').first().json.nivel + "
                       "'). Motivo: ' + ($('prepara').first().json.motivo || 'não informado') + '.'", (1980, -60))
    al = w.ops_alert("alerta_sem_conversa", "'[WF04] Ticket ' + $('prepara').first().json.protocolo + ' escalonado sem conversa vinculada.'",
                     (1320, 160))
    w.chain(a, v, c, g, d, i)
    w.link(i, pr, 0)
    w.link(i, al, 1)
    w.link(pr, i2)
    w.link(i2, pa, 0)
    w.link(i2, n, 1)
    w.link(pa, n)
    return w


# ---------------------------------------------------------------- WF05 / WF07 (WhatsApp por template)
JS_POLITICA_WHATSAPP = """
// Política de envio (LGPD + Meta): opt-in explícito no contato, telefone E.164, horário permitido,
// template aprovado (fora da janela de 24 h só template). Sem opt-in: não envia.
const cfg = $('config').first().json;
const t = $('consulta_ticket').first().json;
const ct = $('consulta_contato').first().json.payload || $('consulta_contato').first().json;
const attrs = ct.custom_attributes || {};
const motivo = [];
if (attrs[cfg.atributo_optin] !== true && String(attrs[cfg.atributo_optin]).toLowerCase() !== 'true') motivo.push('sem opt-in');
if (!/^\\+\\d{10,15}$/.test(ct.phone_number || '')) motivo.push('sem telefone E.164');
if (!cfg.template_nome) motivo.push('template não configurado');
if (cfg.somente_origem_telefone && String(t.channel) !== 'phone') motivo.push('ticket não é de telefonia');
const agora = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Sao_Paulo' }));
const hora = agora.getHours(), dia = agora.getDay();
if (dia === 0 || hora < cfg.hora_inicio || hora >= cfg.hora_fim) motivo.push('fora do horário permitido');
return [{ json: { enviar: motivo.length === 0, motivo: motivo.join(', '), ticket_id: t.id, protocolo: t.protocol,
  contact_id: ct.id, telefone_digitos: String(ct.phone_number || '').replace(/\\D/g, ''),
  primeiro_nome: String(ct.name || '').split(' ')[0] } }];
"""


KEY_WA = ("'%s:' + $('politica_envio').first().json.ticket_id + ($('config').first().json.dry_run ? ':simulado' : '')")


def _whatsapp_wf(code, title, desc, path, kind, filtro_extra, espera_min, template_padrao):
    w = WF(code, title, desc)
    a = w.sd_webhook(path, (0, 0))
    v = w.code("valida_evento", js_valida(code, ["ticket.status_changed"],
               "if (p.to !== 'resolvido') return [];" + filtro_extra), (220, 0))
    c = w.config([("dry_run", "boolean", True),
                  ("whatsapp_inbox_id", "number", 0),
                  ("template_nome", "string", template_padrao),
                  ("template_idioma", "string", "pt_BR"),
                  ("template_categoria", "string", "UTILITY"),
                  ("atributo_optin", "string", "sd_whatsapp_optin"),
                  ("somente_origem_telefone", "boolean", True),
                  ("hora_inicio", "number", 8), ("hora_fim", "number", 20)], (440, 0))
    prev = c
    x = 660
    if espera_min:
        wt = w.wait_minutes("aguarda", espera_min, (x, 0))
        w.link(prev, wt)
        prev, x = wt, x + 220
    g = w.sdops("consulta_ticket", "GET", "/tickets/{{ $('valida_evento').first().json.ticket_id }}", None, (x, 0))
    w.link(prev, g)
    x += 220
    ainda = w.code("ainda_resolvido", """
// Reaberto ou cancelado enquanto esperava: não envia.
const t = $('consulta_ticket').first().json;
return ['resolvido', 'encerrado'].includes(t.status) ? [{ json: t }] : [];
""", (x, 0))
    w.link(g, ainda)
    x += 220
    ct = w.chatwoot("consulta_contato", "GET", "/contacts/{{ $('consulta_ticket').first().json.contact_id }}", None, (x, 0))
    w.link(ainda, ct)
    x += 220
    pol = w.code("politica_envio", JS_POLITICA_WHATSAPP, (x, 0))
    w.link(ct, pol)
    x += 220
    i = w.if_true("pode_enviar", "={{ $json.enviar }}", (x, 0))
    w.link(pol, i)
    nao = w.noop("nao_envia_registra_motivo", (x + 220, 180))
    w.link(i, nao, 1)
    x += 220
    # reserva no sd-ops ANTES do envio: dedupe_key única por ticket (idempotente e permanente no sd-ops; a 2ª vez
    # volta 200 + Idempotent-Replay e o envio não acontece). dry_run usa outra chave (":simulado") para não
    # bloquear o envio real depois que o dry_run for desligado.
    chave = KEY_WA % kind
    log = w.sdops("registra_envio", "POST", "/notifications/log",
                  "={{ JSON.stringify({ channel: 'whatsapp', ticket_id: $('politica_envio').first().json.ticket_id, "
                  "dedupe_key: %s, "
                  "template: $('config').first().json.template_nome, status: $('config').first().json.dry_run ? 'simulado' : 'enviando', "
                  "detail: { tipo: '%s', workflow: '%s' } }) }}" % (chave, kind, code),
                  (x, -40), never_error=True)
    for hp in w.nodes[-1]["parameters"]["headerParameters"]["parameters"]:
        if hp["name"] == "Idempotency-Key":
            hp["value"] = "={{ %s }}" % chave
    w.link(i, log, 0)
    x += 220
    dup = w.if_true("primeiro_envio", "={{ $json.statusCode < 300 && String(($json.headers || {})['idempotent-replay']) !== 'true' "
                    "&& !$('config').first().json.dry_run }}", (x, -40))
    w.link(log, dup)
    seco = w.noop("dry_run_ou_duplicado", (x + 220, 120))
    w.link(dup, seco, 1)
    x += 220
    ci = w.chatwoot("contact_inbox_whatsapp", "POST", "/contacts/{{ $('politica_envio').first().json.contact_id }}/contact_inboxes",
                    "={{ JSON.stringify({ inbox_id: $('config').first().json.whatsapp_inbox_id, "
                    "source_id: $('politica_envio').first().json.telefone_digitos }) }}", (x, -60))
    w.link(dup, ci, 0)
    x += 220
    cv = w.chatwoot("conversa_whatsapp", "POST", "/conversations",
                    "={{ JSON.stringify({ source_id: $json.source_id, inbox_id: $('config').first().json.whatsapp_inbox_id, "
                    "contact_id: $('politica_envio').first().json.contact_id, "
                    "custom_attributes: { sd_protocolo: $('politica_envio').first().json.protocolo } }) }}", (x, -60))
    w.link(ci, cv)
    x += 220
    msg = w.chatwoot("envia_template", "POST", "/conversations/{{ $json.id }}/messages",
                     "={{ JSON.stringify({ content: 'Protocolo ' + $('politica_envio').first().json.protocolo, "
                     "message_type: 'outgoing', content_attributes: { sd_origin: 'n8n:%s' }, "
                     "template_params: { name: $('config').first().json.template_nome, "
                     "category: $('config').first().json.template_categoria, language: $('config').first().json.template_idioma, "
                     "processed_params: { '1': $('politica_envio').first().json.primeiro_nome, "
                     "'2': $('politica_envio').first().json.protocolo } } }) }}" % code, (x, -60))
    w.link(cv, msg)
    x += 220
    lk = w.sdops("vincula_conversa", "POST", "/tickets/{{ $('politica_envio').first().json.ticket_id }}/links",
                 "={{ JSON.stringify({ conversation_id: $('conversa_whatsapp').first().json.id }) }}", (x, -60))
    w.link(msg, lk)
    w.chain(a, v, c)
    return w


def wf05():
    return _whatsapp_wf("WF05", "WhatsApp pós-atendimento (template, opt-in, horário)",
                        "ticket.status_changed -> resolvido de ticket de telefonia: envia template aprovado no WhatsApp "
                        "só com opt-in, em horário permitido, uma vez por ticket. Começa em dry_run=true.",
                        "sd/wf05-whatsapp-pos-atendimento", "whatsapp_pos_atendimento", "", 0, "")


def wf07():
    return _whatsapp_wf("WF07", "CSAT pelo canal permitido",
                        "ticket.status_changed -> resolvido: espera 2 h (não pergunta se reabrir), e envia pesquisa CSAT por "
                        "template de WhatsApp para tickets de telefonia sem pesquisa da 55PBX. E-mail/chat usam o CSAT nativo do "
                        "Chatwoot (nada a fazer aqui). Uma vez por ticket. Começa em dry_run=true.",
                        "sd/wf07-csat", "csat", "", 120, "")


# ---------------------------------------------------------------- WF06
def wf06():
    w = WF("WF06", "E-mail de protocolo na abertura",
           "ticket.created -> se o contato tem e-mail: responde na própria conversa de e-mail (mesma thread) ou abre "
           "conversa na inbox de e-mail configurada e vincula ao ticket. Uma vez por ticket. Começa em dry_run=true.")
    a = w.sd_webhook("sd/wf06-email-protocolo", (0, 0))
    v = w.code("valida_evento", js_valida("WF06", ["ticket.created"]), (220, 0))
    c = w.config([("dry_run", "boolean", True), ("email_inbox_id", "number", 0),
                  ("texto", "string", "Recebemos sua solicitação. Seu protocolo é {protocolo}. "
                                      "Responda este e-mail para complementar o atendimento.")], (440, 0))
    g = w.sdops("consulta_ticket", "GET", "/tickets/{{ $('valida_evento').first().json.ticket_id }}", None, (660, 0))
    ct = w.chatwoot("consulta_contato", "GET", "/contacts/{{ $('consulta_ticket').first().json.contact_id }}", None, (880, 0))
    d = w.code("decide", """
const cfg = $('config').first().json;
const t = $('consulta_ticket').first().json;
const ct = $('consulta_contato').first().json.payload || $('consulta_contato').first().json;
if (!ct.email) return [];                       // sem e-mail: nada a fazer
const convPrimaria = (t.conversations || [])[0] || null;     // sd-ops: conversations = [ids], a 1ª é a primária
const rota = (String(t.channel) === 'email' && convPrimaria) ? 'mesma_thread' : 'nova_conversa';
return [{ json: { rota, ticket_id: t.id, protocolo: t.protocol, contact_id: ct.id, email: ct.email,
  conversation_id: convPrimaria, texto: cfg.texto.replace('{protocolo}', t.protocol) } }];
""", (1100, 0))
    # 1 e-mail por ticket garantido pelo sd-ops (dedupe_key em /notifications/log), sem static data no n8n
    chave = "'email_protocolo:' + $('decide').first().json.ticket_id + ($('config').first().json.dry_run ? ':simulado' : '')"
    log = w.sdops("registra_envio", "POST", "/notifications/log",
                  "={{ JSON.stringify({ channel: 'email', ticket_id: $json.ticket_id, dedupe_key: %s, template: 'protocolo', "
                  "status: $('config').first().json.dry_run ? 'simulado' : 'enviando', detail: { tipo: 'email_protocolo', workflow: 'WF06' } }) }}" % chave,
                  (1540, 0), never_error=True)
    for hp in w.nodes[-1]["parameters"]["headerParameters"]["parameters"]:
        if hp["name"] == "Idempotency-Key":
            hp["value"] = "={{ %s }}" % chave
    ok = w.if_true("primeiro_envio", "={{ $json.statusCode < 300 && String(($json.headers || {})['idempotent-replay']) !== 'true' "
                   "&& !$('config').first().json.dry_run }}", (1760, 0))
    seco = w.noop("dry_run_ou_duplicado", (1980, 180))
    s = w.switch("rota", "={{ $('decide').first().json.rota }}", ["mesma_thread", "nova_conversa"], (1980, -40))
    r1 = w.chatwoot("responde_thread", "POST", "/conversations/{{ $('decide').first().json.conversation_id }}/messages",
                    "={{ JSON.stringify({ content: $('decide').first().json.texto, message_type: 'outgoing', private: false, "
                    "content_attributes: { sd_origin: 'n8n:WF06' } }) }}", (2200, -140))
    ci = w.chatwoot("contact_inbox_email", "POST", "/contacts/{{ $('decide').first().json.contact_id }}/contact_inboxes",
                    "={{ JSON.stringify({ inbox_id: $('config').first().json.email_inbox_id, source_id: $('decide').first().json.email }) }}",
                    (2200, 40))
    cv = w.chatwoot("conversa_email", "POST", "/conversations",
                    "={{ JSON.stringify({ source_id: $json.source_id, inbox_id: $('config').first().json.email_inbox_id, "
                    "contact_id: $('decide').first().json.contact_id, additional_attributes: { mail_subject: "
                    "'Protocolo ' + $('decide').first().json.protocolo }, custom_attributes: { sd_protocolo: $('decide').first().json.protocolo } }) }}",
                    (2420, 40))
    m = w.chatwoot("envia_email", "POST", "/conversations/{{ $json.id }}/messages",
                   "={{ JSON.stringify({ content: $('decide').first().json.texto, message_type: 'outgoing', private: false, "
                   "content_attributes: { sd_origin: 'n8n:WF06' } }) }}", (2640, 40))
    lk = w.sdops("vincula_conversa", "POST", "/tickets/{{ $('decide').first().json.ticket_id }}/links",
                 "={{ JSON.stringify({ conversation_id: $('conversa_email').first().json.id }) }}", (2860, 40))
    w.chain(a, v, c, g, ct, d, log, ok)
    w.link(ok, s, 0)
    w.link(ok, seco, 1)
    w.link(s, r1, 0)
    w.link(s, ci, 1)
    w.chain(ci, cv, m, lk)
    return w


# ---------------------------------------------------------------- WF08
def wf08():
    w = WF("WF08", "Reabertura pelo protocolo citado pelo cliente",
           "Webhook do Chatwoot (message_created): mensagem do cliente que cita um protocolo -> verifica a identidade "
           "(mesmo contato) -> reabre (resolvido) ou pede ao sd-ops o ticket de continuação (encerrado/cancelado) e "
           "vincula a conversa; ticket aberto: só vincula. "
           "Protocolo de outro contato: só nota interna para o agente verificar.")
    a = w.add("webhook_chatwoot", "n8n-nodes-base.webhook", 2,
              {"httpMethod": "POST", "path": "sd/wf08-chatwoot-REPLACE_SEGREDO_LONGO", "options": {}}, (0, 0),
              webhookId=nid("WF08", "webhook_chatwoot"))
    f = w.code("filtra_mensagem", """
// Chatwoot não envia header customizado: a URL contém um segredo longo (troque REPLACE_SEGREDO_LONGO)
// e o sd-ops/Traefik pode restringir a origem. Anti-loop: só mensagens de CONTATO, nunca de agente/integração.
const b = $input.first().json.body || {};
if (b.event !== 'message_created') return [];
if (b.message_type !== 'incoming' && b.message_type !== 0) return [];
if (b.private) return [];
const ca = b.content_attributes || {};
if (ca.sd_origin) return [];
const sender = b.sender || {};
if (sender.type && sender.type !== 'contact') return [];
const txt = String(b.content || '');
const m = txt.match(/\\b([A-Z][A-Z0-9]{1,5}-\\d{4}-\\d{6})\\b/) || txt.match(/\\b(20\\d{9})\\b/);
if (!m) return [];
const conv = b.conversation || {};
const contactId = (conv.meta && conv.meta.sender && conv.meta.sender.id) || sender.id || null;
return [{ json: { protocolo: m[1], conversation_id: conv.id || conv.display_id, contact_id: contactId } }];
""", (220, 0))
    c = w.config([], (440, 0))
    g = w.sdops("busca_ticket", "GET", "/tickets/{{ encodeURIComponent($('filtra_mensagem').first().json.protocolo) }}",
                None, (660, 0), never_error=True)
    d = w.code("decide", """
const m = $('filtra_mensagem').first().json;
const r = $('busca_ticket').first().json;
if (r.statusCode === 404) return [{ json: { acao: 'nao_encontrado', ...m } }];
if (r.statusCode >= 300) throw new Error('sd-ops respondeu ' + r.statusCode + ' ao buscar o protocolo');
const t = r.body || {};
const mesmoContato = String(t.contact_id) === String(m.contact_id);
const base = { ...m, ticket_id: t.id, estado: t.status, protocolo_ticket: t.protocol };
if (!mesmoContato) return [{ json: { acao: 'identidade', ...base } }];   // nunca relaciona sem identidade
// sd-ops /reopen: resolvido -> em_atendimento; encerrado/cancelado -> cria ticket de continuação (followup)
if (['resolvido', 'encerrado', 'cancelado'].includes(base.estado)) return [{ json: { acao: 'reabrir', ...base } }];
return [{ json: { acao: 'vincular', ...base } }];
""", (880, 0))
    s = w.switch("acao", "={{ $json.acao }}", ["reabrir", "vincular", "identidade", "nao_encontrado"], (1100, 0))
    re = w.sdops("reabre", "POST", "/tickets/{{ $('decide').first().json.ticket_id }}/reopen",
                 "={{ JSON.stringify({ to: 'em_atendimento', reason: 'Cliente citou o protocolo em nova mensagem (conversa ' + "
                 "$('decide').first().json.conversation_id + ')' }) }}", (1320, -200))
    alvo = w.code("ticket_alvo", """
// Depois do /reopen o sd-ops devolve o ticket (o de continuação, se criou um: followup_created).
const d = $('decide').first().json;
const r = $('reabre').isExecuted ? $('reabre').first().json : {};
return [{ json: { ticket_id: (r && r.id) || d.ticket_id, conversation_id: d.conversation_id } }];
""", (1540, -200))
    lk = w.sdops("vincula", "POST", "/tickets/{{ $json.ticket_id }}/links",
                 "={{ JSON.stringify({ conversation_id: $json.conversation_id }) }}", (1760, -120))
    n1 = w.private_note("nota_identidade", "$('decide').first().json.conversation_id",
                        "'O cliente citou o protocolo ' + $('decide').first().json.protocolo + ', que pertence a OUTRO contato. "
                        "Verifique a identidade antes de relacionar (nada foi alterado).'", (1320, 160))
    n2 = w.private_note("nota_nao_encontrado", "$('decide').first().json.conversation_id",
                        "'O cliente citou o protocolo ' + $('decide').first().json.protocolo + ', que não foi encontrado.'", (1320, 320))
    w.chain(a, f, c, g, d, s)
    w.link(s, re, 0)
    w.link(s, alvo, 1)
    w.link(s, n1, 2)
    w.link(s, n2, 3)
    w.chain(re, alvo, lk)
    return w


# ---------------------------------------------------------------- WF09
def wf09():
    w = WF("WF09", "Reconciliação diária com os relatórios 55PBX",
           "03:00 (e sob demanda) -> pede ao sd-ops a reconciliação do dia anterior pelo Report02; divergências e "
           "erros viram alerta. Quem escreve é o sd-ops.")
    s = w.schedule_cron("todo_dia_03h", "0 3 * * *", (0, -80))
    m = w.add("webhook_manual", "n8n-nodes-base.webhook", 2,
              {"httpMethod": "POST", "path": "sd/wf09-reconciliar", "authentication": "headerAuth", "options": {}},
              (0, 80), CRED_HOOK, webhookId=nid("WF09", "webhook_manual"))
    c = w.config([("dias_atras", "number", 1), ("alerta_novas_acima", "number", 20)], (220, 0))
    j = w.code("janela", """
// Dia(s) anterior(es) em horário de Brasília (UTC-3, sem horário de verão), convertido para UTC.
const body = ($('webhook_manual').isExecuted ? ($('webhook_manual').first().json.body || {}) : {});
if (body.from && body.to) return [{ json: { from: body.from, to: body.to } }];
const dias = $('config').first().json.dias_atras || 1;
const agoraBRT = new Date(Date.now() - 3 * 3600 * 1000);
const fimBRT = Date.UTC(agoraBRT.getUTCFullYear(), agoraBRT.getUTCMonth(), agoraBRT.getUTCDate());
const ini = new Date(fimBRT - dias * 86400000 + 3 * 3600000);
const fim = new Date(fimBRT + 3 * 3600000 - 1000);
return [{ json: { from: ini.toISOString(), to: fim.toISOString() } }];
""", (440, 0))
    r = w.sdops("reconcilia", "POST", "/reconciliations", "={{ JSON.stringify({ from: $json.from, to: $json.to }) }}",
                (660, 0), never_error=True, timeout=600000)
    k = w.code("resume", """
const r = $('reconcilia').first().json;
// sd-ops: 202 {rows, new} | 202 {skipped: motivo} | 502 {error, rows, new}
const b = r.body || {};
const erro = r.statusCode >= 300 || !!b.error;
const pulou = !!b.skipped;
const per = $('janela').first().json.from + ' a ' + $('janela').first().json.to;
const texto = '[WF09] Reconciliação ' + per + ': ' + (erro ? ('FALHOU (HTTP ' + r.statusCode + ') ' + (b.error || '')) :
  pulou ? ('NÃO EXECUTADA: ' + b.skipped) : ('linhas do Report02 ' + (b.rows || 0) + ', novas (não vistas em tempo real) ' + (b.new || 0)));
// "novas" > 0 = ligações que o tempo real não entregou: alerta só acima do limite configurado
return [{ json: { alertar: erro || pulou || Number(b.new || 0) > $('config').first().json.alerta_novas_acima, texto } }];
""", (880, 0))
    i = w.if_true("precisa_alertar", "={{ $json.alertar }}", (1100, 0))
    al = w.ops_alert("alerta_reconciliacao", "$json.texto", (1320, -40))
    ok = w.noop("sem_alerta", (1320, 120))
    w.link(s, c)
    w.link(m, c)
    w.chain(c, j, r, k, i)
    w.link(i, al, 0)
    w.link(i, ok, 1)
    return w


# ---------------------------------------------------------------- WF10
def wf10():
    w = WF("WF10", "Alertas de SLA",
           "A cada 15 min consulta tickets com SLA vencendo em 60 min e avisa uma vez por prazo (static data); "
           "sla.breached (evento) "
           "sobe a prioridade e avisa operações. O cálculo do SLA é do sd-ops.")
    s = w.schedule_cron("a_cada_15min", "*/15 * * * *", (0, -120))
    c = w.config([("janela_min", "number", 60), ("etiqueta_risco", "string", "sla_em_risco")], (220, -120))
    g = w.sdops("tickets_em_risco", "GET", "/sla/at-risk", None, (440, -120),
                query=[("within", "={{ $('config').first().json.janela_min }}")])
    sp = w.code("um_por_ticket", """
// Resposta em array vira vários itens no n8n; resposta embrulhada ({items|data: [...]}) vira um item.
const lista = $('tickets_em_risco').all().map(i => i.json).flatMap(j => Array.isArray(j.items) ? j.items : (Array.isArray(j.data) ? j.data : [j]));
return lista.filter(t => t && (t.ticket_id || t.id) && !t.breached).map(t => ({ json: {
  ticket_id: t.ticket_id || t.id, protocolo: t.protocol || t.protocolo || '', metric: t.metric || '',
  due_at: t.due_at || '' } }));
""", (660, -120))
    dd = w.code("so_novos", js_dedupe("'sla:' + it.json.ticket_id + ':' + it.json.metric + ':' + it.json.due_at", 7), (880, -120))
    gt = w.sdops("consulta_ticket", "GET", "/tickets/{{ $json.ticket_id }}", None, (1100, -120))
    cj = w.code("com_conversa", """
// O /sla/at-risk não traz a conversa: usa a primária do ticket (conversations[0]); pareia por índice.
const base = $('so_novos').all();
return $input.all().map((it, i) => ({ json: { ...base[i].json, conversation_id: (it.json.conversations || [])[0] || null } }))
  .filter(x => x.json.conversation_id);
""", (1320, -120))
    n = w.private_note("nota_sla_risco", "$json.conversation_id",
                       "'SLA em risco: ' + $json.metric + ' vence em ' + $json.due_at + ' (ticket ' + $json.protocolo + ').'",
                       (1540, -120))
    # evento sla.breached
    a = w.sd_webhook("sd/wf10-sla", (0, 160))
    v = w.code("valida_evento", js_valida("WF10", ["sla.breached"]), (220, 160))
    c2 = w.config([], (440, 160), name="config_evento")  # ramo de evento: refs reescritas em fix_config_refs
    i = w.if_true("tem_conversa", "={{ !!$('valida_evento').first().json.conversation_id }}", (660, 160))
    pr = w.chatwoot("prioridade_urgente", "POST", "/conversations/{{ $('valida_evento').first().json.conversation_id }}/toggle_priority",
                    "={{ JSON.stringify({ priority: 'urgent' }) }}", (880, 120))
    n2 = w.private_note("nota_sla_violado", "$('valida_evento').first().json.conversation_id",
                        "'SLA VIOLADO: ' + $('valida_evento').first().json.payload.metric + ' (prazo ' + "
                        "$('valida_evento').first().json.payload.due_at + ').'", (1100, 120))
    al = w.ops_alert("alerta_sla_violado", "'[WF10] SLA violado no ticket ' + ($('valida_evento').first().json.payload.protocol || "
                     "$('valida_evento').first().json.ticket_id) + ': ' + $('valida_evento').first().json.payload.metric", (1320, 200))
    w.chain(s, c, g, sp, dd, gt, cj, n)
    w.chain(a, v, c2, i)
    w.link(i, pr, 0)
    w.link(i, al, 1)
    w.chain(pr, n2, al)
    return w


# ---------------------------------------------------------------- WF11
def wf11():
    w = WF("WF11", "QA crítico (revisão do supervisor)",
           "qa.completed (publicado pelo qa-pipeline do A3) com nota abaixo do mínimo ou alerta crítico -> supervisor "
           "como participante, nota interna com o link do console de QA e registro no ticket. A nota da IA é "
           "recomendação; a decisão é humana.")
    a = w.sd_webhook("sd/wf11-qa-critico", (0, 0))
    v = w.code("valida_evento", js_valida("WF11", ["qa.completed"]), (220, 0))
    c = w.config([("nota_minima", "number", 60), ("supervisores_por_time", "string", '{"*": []}')], (440, 0))
    k = w.code("e_critico", """
const ev = $('valida_evento').first().json;
const p = ev.payload || {};
const min = $('config').first().json.nota_minima;
const alertas = p.critical_alerts || p.alerts || [];
const nota = (p.score === null || p.score === undefined) ? null : Number(p.score);
if (!(alertas.length > 0 || (nota !== null && nota < min))) return [];
return [{ json: { evaluation_id: p.evaluation_id || p.id, nota, alertas: alertas.map(a => a.type || a).slice(0, 5),
  call_id: ev.call_id, ticket_id: ev.ticket_id, conversation_id: ev.conversation_id } }];
""", (660, 0))
    g = w.sdops("consulta_chamada", "GET", "/calls/{{ $json.call_id }}", None, (880, 0), never_error=True)
    d = w.code("prepara", """
const q = $('e_critico').first().json;
const r = $('consulta_chamada').first().json;
const call = (r && r.body) || {};
let mapa = {};
try { mapa = JSON.parse($('config').first().json.supervisores_por_time || '{}'); } catch (e) { mapa = {}; }
const conv = q.conversation_id || call.conversation_id || null;
const ticket = q.ticket_id || ((call.tickets || [])[0] || {}).id || null;
const sup = (mapa[String(call.team_id)] || mapa['*'] || []).map(Number).filter(Boolean);
const link = $('config').first().json.console_base_url + '/qa/avaliacoes/' + q.evaluation_id;
const texto = 'QA crítico: nota ' + (q.nota === null ? 'n/d' : q.nota) + (q.alertas.length ? ('; alertas: ' + q.alertas.join(', ')) : '') +
  '. Revisão do supervisor necessária: ' + link + ' (a nota da IA é recomendação).';
return [{ json: { conversation_id: conv, ticket_id: ticket, supervisores: sup, texto } }];
""", (1100, 0))
    i = w.if_true("tem_conversa", "={{ !!$json.conversation_id }}", (1320, 0))
    i2 = w.if_true("tem_supervisor", "={{ $('prepara').first().json.supervisores.length > 0 }}", (1540, -80))
    pa = w.chatwoot("adiciona_supervisores", "POST", "/conversations/{{ $('prepara').first().json.conversation_id }}/participants",
                    "={{ JSON.stringify({ user_ids: $('prepara').first().json.supervisores }) }}", (1760, -160))
    n = w.private_note("nota_qa", "$('prepara').first().json.conversation_id", "$('prepara').first().json.texto", (1980, -80))
    i3 = w.if_true("tem_ticket", "={{ !!$('prepara').first().json.ticket_id }}", (2200, -80))
    tn = w.sdops("registra_no_ticket", "POST", "/tickets/{{ $('prepara').first().json.ticket_id }}/notes",
                 "={{ JSON.stringify({ kind: 'nota_interna', body: $('prepara').first().json.texto, post_to_chatwoot: false }) }}",
                 (2420, -120))
    al = w.ops_alert("alerta_qa", "'[WF11] ' + $('prepara').first().json.texto", (1540, 140))
    w.chain(a, v, c, k, g, d, i)
    w.link(i, i2, 0)
    w.link(i, al, 1)
    w.link(i2, pa, 0)
    w.link(i2, n, 1)
    w.chain(pa, n, i3)
    w.link(i3, tn, 0)
    return w


# ---------------------------------------------------------------- WF12
def wf12():
    w = WF("WF12", "Relatório gerencial semanal",
           "Segunda 08:00 -> resumo dos últimos 7 dias (tickets, telefonia, SLA, QA) publicado como nota no ticket "
           "interno de operações. Números e fórmulas vêm do sd-ops (WEBHOOK_CONTRACTS.md §8.7).")
    s = w.schedule_cron("segunda_08h", "0 8 * * 1", (0, 0))
    c = w.config([("dias", "number", 7)], (220, 0))
    p = w.code("periodo", """
const dias = $('config').first().json.dias || 7;
const to = new Date(); const from = new Date(to.getTime() - dias * 86400000);
return [{ json: { from: from.toISOString(), to: to.toISOString() } }];
""", (440, 0))
    r1 = w.sdops("resumo", "GET", "/reports/summary", None, (660, 0),
                 query=[("from", "={{ $('periodo').first().json.from }}"), ("to", "={{ $('periodo').first().json.to }}")])
    r2 = w.sdops("telefonia", "GET", "/metrics/telephony", None, (880, 0),
                 query=[("from", "={{ $('periodo').first().json.from }}"), ("to", "={{ $('periodo').first().json.to }}")])
    r3 = w.sdops("tickets", "GET", "/metrics/tickets", None, (1100, 0),
                 query=[("from", "={{ $('periodo').first().json.from }}"), ("to", "={{ $('periodo').first().json.to }}")])
    f = w.code("formata", """
// Só números agregados (sem dados pessoais).
const fmt = (o, pref) => Object.entries(o || {}).filter(([k, v]) => typeof v !== 'object')
  .map(([k, v]) => '- ' + pref + k + ': ' + v).join('\\n');
const per = $('periodo').first().json;
const texto = '[WF12] Relatório ' + per.from.slice(0, 10) + ' a ' + per.to.slice(0, 10) + '\\n' +
  'Resumo\\n' + fmt($('resumo').first().json, '') + '\\nTelefonia\\n' + fmt($('telefonia').first().json, '') +
  '\\nTickets\\n' + fmt($('tickets').first().json, '');
return [{ json: { texto: texto.slice(0, 9000) } }];
""", (1320, 0))
    n = w.ops_alert("publica_relatorio", "$json.texto", (1540, 0))
    w.chain(s, c, p, r1, r2, r3, f, n)
    return w


BUILDERS = [wf00, wf01, wf02, wf03, wf04, wf05, wf06, wf07, wf08, wf09, wf10, wf11, wf12]


def fix_config_refs(w):
    """No WF10 o ramo de evento usa 'config_evento'; os nós desse ramo que leem $('config') continuam válidos
    porque 'config' existe no mesmo workflow, mas só é executado no ramo agendado. Para não depender de nó
    não executado, reescreve as referências do ramo de evento para 'config_evento'."""
    if w.wfc != "WF10":
        return
    ramo = {"prioridade_urgente", "nota_sla_violado", "alerta_sla_violado", "tem_conversa", "valida_evento"}
    for n in w.nodes:
        if n["name"] in ramo:
            s = json.dumps(n["parameters"])
            s = s.replace("$('config')", "$('config_evento')")
            n["parameters"] = json.loads(s)


def build():
    out = {}
    for b in BUILDERS:
        w = b()
        fix_config_refs(w)
        out["%s.json" % w.wfc.lower()] = w.to_json()
    return out


def main():
    check = "--check" in sys.argv
    files = build()
    os.makedirs(OUT, exist_ok=True)
    diff = []
    for fn, data in sorted(files.items()):
        txt = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        path = os.path.join(OUT, fn)
        if check:
            cur = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
            if cur != txt:
                diff.append(fn)
        else:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(txt)
    inv = {k: sorted(v) for k, v in sorted(SDOPS_PATHS.items())}
    inv_txt = json.dumps(inv, ensure_ascii=False, indent=2) + "\n"
    inv_path = os.path.join(OUT, "..", "sdops_endpoints_used.json")
    if check:
        if not os.path.exists(inv_path) or open(inv_path, encoding="utf-8").read() != inv_txt:
            diff.append("sdops_endpoints_used.json")
        if diff:
            print("DESATUALIZADO:", ", ".join(diff))
            return 1
        print("OK: %d workflows idênticos ao gerador" % len(files))
        return 0
    with open(inv_path, "w", encoding="utf-8") as fh:
        fh.write(inv_txt)
    print("gerados %d workflows em %s" % (len(files), OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
