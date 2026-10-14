#!/usr/bin/env python3
"""Executa a lógica dos nós Code dos workflows com dados sintéticos (Node.js), sem n8n.

Simula $input, $('Nó').first()/all() e $json. Cobre: validação de envelope e anti-loop (todos os WF de evento),
filtro e identidade da reabertura (WF08), janela da reconciliação (WF09), política de WhatsApp (WF05),
decisão de reserva de atribuição (WF01), QA crítico (WF11) e deduplicação de alertas de SLA (WF10).
Uso: python3 tools/test_code_nodes.py   (sai com 1 se algum caso falhar)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WF_DIR = os.path.normpath(os.path.join(HERE, "..", "workflows"))

HARNESS = r"""
const CTX = %(ctx)s;
const $ = (n) => {
  if (!(n in CTX.nodes)) throw new Error('nó não simulado: ' + n);
  const items = CTX.nodes[n].map(j => ({ json: j }));
  return { first: () => items[0], all: () => items, isExecuted: true };
};
const __sd = CTX.static || {};
const $getWorkflowStaticData = () => __sd;
const $input = { first: () => ({ json: CTX.input[0] }), all: () => CTX.input.map(j => ({ json: j })) };
(async () => {
  try {
    const r = await (async function () { %(code)s })();
    console.log(JSON.stringify({ ok: true, out: (r || []).map(x => x.json), static: __sd }));
  } catch (e) { console.log(JSON.stringify({ ok: false, error: String(e.message || e) })); }
})();
"""


def load(wf):
    d = json.load(open(os.path.join(WF_DIR, wf + ".json"), encoding="utf-8"))
    return {n["name"]: n for n in d["nodes"]}


def run(node_bin, code, input_items, nodes, static=None):
    ctx = json.dumps({"input": input_items, "nodes": nodes, "static": static or {}}, ensure_ascii=False)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(HARNESS % {"ctx": ctx, "code": code})
        p = fh.name
    try:
        r = subprocess.run([node_bin, p], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(p)
    return json.loads(r.stdout.strip().splitlines()[-1])


def env(type_, payload=None, origin="sd-ops", caused_by=None, ts=None):
    return {"headers": {"x-sd-origin": origin, "x-sd-timestamp": str(int(ts or time.time()))},
            "body": {"id": "e1", "type": type_, "tenant_id": "dev55", "caused_by": caused_by,
                     "subject": {"call_id": "c1", "conversation_id": 10}, "payload": payload or {}}}


def main():
    node_bin = shutil.which("node")
    if not node_bin:
        print("Node.js não encontrado")
        return 1
    cases = []

    def case(desc, wf, node, inp, nodes, check, static=None):
        code = load(wf)[node]["parameters"]["jsCode"]
        r = run(node_bin, code, inp, nodes, static)
        try:
            ok = check(r)
        except Exception as e:  # noqa: BLE001
            ok = False
            r = {"exc": str(e), **r}
        cases.append((ok, "%s/%s: %s" % (wf, node, desc), r))

    one = lambda r: r["ok"] and len(r["out"]) == 1  # noqa: E731
    none = lambda r: r["ok"] and r["out"] == []  # noqa: E731
    err = lambda r: not r["ok"]  # noqa: E731

    # envelope e anti-loop
    case("evento aceito", "wf03", "valida_evento", [env("call.missed", {"outcome": "abandoned_queue"})], {},
         lambda r: one(r) and r["out"][0]["conversation_id"] == 10)
    case("tipo não aceito é ignorado", "wf03", "valida_evento", [env("call.ended")], {}, none)
    case("origem diferente de sd-ops gera erro", "wf03", "valida_evento", [env("call.missed", origin="n8n")], {}, err)
    case("causado pelo próprio WF (loop) é ignorado", "wf03", "valida_evento",
         [env("call.missed", caused_by="n8n:WF03")], {}, none)
    case("causado por outro WF segue", "wf03", "valida_evento", [env("call.missed", caused_by="n8n:WF04")], {}, one)
    case("evento antigo (replay > 15 min) é ignorado", "wf03", "valida_evento",
         [env("call.missed", ts=time.time() - 3600)], {}, none)
    case("ligação interna não dispara WF01", "wf01", "valida_evento", [env("call.started", {"direction": "interno"})], {}, none)
    case("WF05 só com status resolvido", "wf05", "valida_evento", [env("ticket.status_changed", {"to": "em_atendimento"})], {}, none)
    case("WF05 aceita resolvido", "wf05", "valida_evento", [env("ticket.status_changed", {"to": "resolvido", "ticket_id": "t1"})], {}, one)

    # WF01 reserva
    cfg01 = [{"fallback_enabled": True, "queue_team_map": json.dumps({"FILA_SUPORTE_1": "Suporte"})}]
    ev01 = [{"conversation_id": 10, "payload": {"queue": "3855-FILA_SUPORTE_1"}}]
    times = [{"id": 8, "name": "Financeiro"}, {"id": 7, "name": "Suporte"}]  # array dividido em itens pelo n8n
    case("sem agente/time: atribui time pela fila", "wf01", "decide_reserva", [{}],
         {"config": cfg01, "valida_evento": ev01, "busca_conversa": [{"meta": {}}], "lista_times": times},
         lambda r: one(r) and r["out"][0]["team_id"] == 7)
    case("já tem agente: não mexe", "wf01", "decide_reserva", [{}],
         {"config": cfg01, "valida_evento": ev01, "busca_conversa": [{"meta": {"assignee": {"id": 1}}}], "lista_times": times}, none)

    # WF08 reabertura
    def cw(content, mtype="incoming", sender_type="contact", ca=None):
        return [{"body": {"event": "message_created", "message_type": mtype, "content": content, "private": False,
                          "content_attributes": ca or {}, "sender": {"id": 5, "type": sender_type},
                          "conversation": {"id": 99, "meta": {"sender": {"id": 5}}}}}]
    case("extrai protocolo legível", "wf08", "filtra_mensagem", cw("meu protocolo é B2B-2026-000123 obrigado"), {},
         lambda r: one(r) and r["out"][0]["protocolo"] == "B2B-2026-000123")
    case("extrai protocolo numérico (URA)", "wf08", "filtra_mensagem", cw("protocolo 20260001237"), {},
         lambda r: one(r) and r["out"][0]["protocolo"] == "20260001237")
    case("mensagem de agente é ignorada (anti-loop)", "wf08", "filtra_mensagem",
         cw("B2B-2026-000123", mtype="outgoing", sender_type="user"), {}, none)
    case("mensagem marcada sd_origin é ignorada", "wf08", "filtra_mensagem", cw("B2B-2026-000123", ca={"sd_origin": "n8n:WF06"}), {}, none)
    m = [{"protocolo": "B2B-2026-000123", "conversation_id": 99, "contact_id": 5}]
    case("mesmo contato + resolvido = reabrir", "wf08", "decide", [{}],
         {"filtra_mensagem": m, "busca_ticket": [{"statusCode": 200, "body": {"id": "t1", "contact_id": 5, "status": "resolvido", "protocol": "B2B-2026-000123"}}]},
         lambda r: one(r) and r["out"][0]["acao"] == "reabrir")
    case("outro contato = só verificação de identidade", "wf08", "decide", [{}],
         {"filtra_mensagem": m, "busca_ticket": [{"statusCode": 200, "body": {"id": "t1", "contact_id": 6, "status": "resolvido"}}]},
         lambda r: one(r) and r["out"][0]["acao"] == "identidade")
    case("encerrado = reabrir (o sd-ops cria a continuação)", "wf08", "decide", [{}],
         {"filtra_mensagem": m, "busca_ticket": [{"statusCode": 200, "body": {"id": "t1", "contact_id": 5, "status": "encerrado"}}]},
         lambda r: one(r) and r["out"][0]["acao"] == "reabrir")
    case("aberto = só vincular", "wf08", "decide", [{}],
         {"filtra_mensagem": m, "busca_ticket": [{"statusCode": 200, "body": {"id": "t1", "contact_id": 5, "status": "em_atendimento"}}]},
         lambda r: one(r) and r["out"][0]["acao"] == "vincular")
    case("404 = não encontrado", "wf08", "decide", [{}], {"filtra_mensagem": m, "busca_ticket": [{"statusCode": 404, "body": {}}]},
         lambda r: one(r) and r["out"][0]["acao"] == "nao_encontrado")

    # WF09 janela
    case("janela D-1 em UTC (24 h - 1 s)", "wf09", "janela", [{}], {"config": [{"dias_atras": 1}], "webhook_manual": [{"body": {}}]},
         lambda r: one(r) and (lambda a, b: 86398 <= (b - a) <= 86400)(*[
             time.mktime(time.strptime(r["out"][0][k][:19], "%Y-%m-%dT%H:%M:%S")) for k in ("from", "to")]))

    # WF05 política
    cfg05 = [{"atributo_optin": "sd_whatsapp_optin", "template_nome": "pos_atendimento", "somente_origem_telefone": True,
              "hora_inicio": 0, "hora_fim": 24}]
    tk = [{"id": "t1", "protocol": "B2B-2026-000001", "channel": "phone", "status": "resolvido"}]
    case("sem opt-in não envia", "wf05", "politica_envio", [{}],
         {"config": cfg05, "consulta_ticket": tk, "consulta_contato": [{"payload": {"id": 5, "phone_number": "+5511900000000", "custom_attributes": {}}}]},
         lambda r: one(r) and r["out"][0]["enviar"] is False and "opt-in" in r["out"][0]["motivo"])
    case("com opt-in e telefone envia (fora do domingo)", "wf05", "politica_envio", [{}],
         {"config": cfg05, "consulta_ticket": tk, "consulta_contato": [{"payload": {"id": 5, "name": "Ana Teste", "phone_number": "+5511900000000",
                                                                                     "custom_attributes": {"sd_whatsapp_optin": True}}}]},
         lambda r: one(r) and (r["out"][0]["enviar"] is True or "domingo" not in r["out"][0]["motivo"]))

    case("lista de times embrulhada em payload também funciona", "wf01", "decide_reserva", [{}],
         {"config": cfg01, "valida_evento": ev01, "busca_conversa": [{"meta": {}}], "lista_times": [{"payload": [{"id": 7, "name": "Suporte"}]}]},
         lambda r: one(r) and r["out"][0]["team_id"] == 7)
    # WF10 lista em risco (array dividido em itens e resposta embrulhada)
    case("SLA em risco: array dividido em itens", "wf10", "um_por_ticket", [{}],
         {"tickets_em_risco": [{"ticket_id": "a", "metric": "first_response", "due_at": "x", "conversation_id": 1}, {"id": "b", "conversation_id": 2}]},
         lambda r: r["ok"] and [x["ticket_id"] for x in r["out"]] == ["a", "b"])
    case("SLA em risco: resposta {items: [...]}", "wf10", "um_por_ticket", [{}],
         {"tickets_em_risco": [{"items": [{"ticket_id": "a"}, {"ticket_id": "c"}]}]},
         lambda r: r["ok"] and [x["ticket_id"] for x in r["out"]] == ["a", "c"])

    # WF11 QA
    case("nota baixa é crítica", "wf11", "e_critico", [{}],
         {"config": [{"nota_minima": 60}], "valida_evento": [{"payload": {"score": 42, "evaluation_id": "q1"}, "call_id": "c1"}]}, one)
    case("nota boa sem alerta não dispara", "wf11", "e_critico", [{}],
         {"config": [{"nota_minima": 60}], "valida_evento": [{"payload": {"score": 88}, "call_id": "c1"}]}, none)

    # WF10 dedupe
    case("SLA: alerta só uma vez por ticket/métrica/prazo (static data)", "wf10", "so_novos",
         [{"ticket_id": "a", "metric": "m", "due_at": "1"}, {"ticket_id": "b", "metric": "m", "due_at": "1"}], {},
         lambda r: r["ok"] and [x["ticket_id"] for x in r["out"]] == ["b"],
         static={"enviados": {"sla:a:m:1": int(time.time() * 1000)}})
    case("WhatsApp: segundo envio do mesmo ticket é bloqueado", "wf05", "ja_enviado",
         [{"ticket_id": "t1"}], {}, none, static={"enviados": {"whatsapp_pos_atendimento:t1": int(time.time() * 1000)}})
    case("WhatsApp: primeiro envio passa e reserva a chave", "wf05", "ja_enviado",
         [{"ticket_id": "t9"}], {}, lambda r: one(r) and "whatsapp_pos_atendimento:t9" in r["static"]["enviados"])
    case("SLA: junta a conversa primária do ticket", "wf10", "com_conversa",
         [{"conversations": [99, 100]}, {"conversations": []}],
         {"so_novos": [{"ticket_id": "a"}, {"ticket_id": "b"}]},
         lambda r: r["ok"] and r["out"] == [{"ticket_id": "a", "conversation_id": 99}])

    falhas = 0
    for ok, desc, r in cases:
        print("%s  %s" % ("OK  " if ok else "FALHA", desc))
        if not ok:
            falhas += 1
            print("      ", json.dumps(r, ensure_ascii=False)[:300])
    print("casos: %d | falhas: %d" % (len(cases), falhas))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
