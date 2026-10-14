#!/usr/bin/env python3
"""Monta o workflow do e2e da API de compatibilidade com o Zendesk (M7) com NÓS REAIS da exportação do n8n.

Os nós Zendesk/HTTP/Code são copiados sem nenhuma alteração de parâmetros dos workflows ativos do cliente; só mudam:
  - a credencial (zendeskApi -> "ServiceDesk (compat Zendesk)", httpHeaderAuth do Sunshine -> "ServiceDesk Sunshine")
  - os valores de configuração que os nós leem ($('start').json.subdomain etc.), que no cliente vêm do banco do n8n:
    subdomínio = "<host do ServiceDesk>/b2b-reservas"
Os nós de entrada ($('start'), $('config'), ...) viram nós Set com esses valores. Um nó Code final confere a resposta.

Uso: build_workflow.py <dir dos workflows exportados> <seed.json (saída do seed)> <subdominio> > workflow.json
"""
import copy
import glob
import json
import os
import sys

EXPORT_DIR, SEED_FILE, SUBDOMAIN = sys.argv[1], sys.argv[2], sys.argv[3]
seed = json.load(open(SEED_FILE))
AI = 36212918767515
TICKET = seed['email_ticket']
CHAT = seed['chat_ticket']
UUID = seed['chat_conversation_uuid']
SUNCO = seed['sunco_user_id']

# (workflow, nó) na ordem de execução
REAL_NODES = [
    ('Tratamento Inicial', 'puxa_ticket'),
    ('Tratamento Inicial', 'puxa_comentarios_anexos'),
    ('Tratamento Inicial', 'puxa_CCs'),
    ('Monitor Intervenção Humana - Cancelamento e TNA - Prod', 'puxa_membros_suporte'),
    ('Monitor Intervenção Humana - Cancelamento e TNA - Prod', 'busca_tickets_cema'),
    ('Monitor Intervenção Humana - Cancelamento e TNA - Prod', 'puxa_audits'),
    ('Monitor Intervenção Humana - Cancelamento e TNA - Prod', 'puxa_autores'),
    ('CC Agent', 'email_notifications_get_invalid'),
    ('Reatribuição de Tickets', 'puxa_agentes_suporte'),
    ('Restaura Tabulação Pós Sem Retorno', 'puxa_autor_comentario'),
    ('Alerta e Escala Falha de Consulta', 'marca_no_ai'),
    ('Despacha tickets ociosos que não puderam ser atendidos', 'puxa_users_grupo_suporte'),
    ('Recebe Mensagens Zendesk', 'puxa_conversation_log'),
    ('Recebe Mensagens Zendesk', 'extrai_sunco_user_id'),
    ('Recebe Mensagens Zendesk', 'puxa_conversation_id'),
    ('Recebe Mensagens Zendesk', 'puxa_mensagem_sunshine'),
    ('Despacha Inatividade Chat - Cema', 'envia_aviso'),
    ('Fluxo Principal - Agente IA - TNA - Produção', 'sinaliza_digitando'),
    ('Recebe Mensagens Zendesk', 'reatribui_cema'),
    ('Cataloga Tickets Zendesk', 'atualiza_ticket_'),
]

# Nós de entrada que os nós reais referenciam, com os valores que no cliente vêm do banco/config do n8n.
INPUTS = {
    'start': {'subdomain': SUBDOMAIN, 'subdominio': SUBDOMAIN, 'ticket_id': TICKET, 'ai_agent_id': AI, 'group_id': 20487412043675,
              'comment_author_id': 21000000000001, 'conversation_id': UUID},
    'recebe_webhook': {'body': {'ticket_id': TICKET, 'canal': 'email'}},
    'puxa_variaveis_gerais': {'subdominio': SUBDOMAIN, 'ai_agent_id': AI, 'group_id': 20487412043675, 'sunshine_app_id': 'app-b2b'},
    'config': {'subdomain': SUBDOMAIN, 'ai_agent_id': AI, 'janela': '2020-01-01', 'group_id_suporte': 20487412043675, 'autores_ignorados': []},
    'loop_tickets': {'ticket_id': TICKET},
    'monta_ids_autores': {'ids': f'{AI},21000000000001'},
    'busca_config': {'subdominio': SUBDOMAIN},
    'webhook_chat_messages': {'body': {'ticket_id': CHAT}},
    'puxa_config_zendesk': {'subdominio': SUBDOMAIN, 'sunshine_app_id': 'app-b2b'},
    'puxa_infos_ticket_banco': {'conversation_id': UUID},
    'puxa_config': {'subdominio': SUBDOMAIN, 'sunshine_app_id': 'app-b2b', 'ai_agent_avatar_url': 'https://example.com/cema.png'},
    'loop': {'conversation_id': UUID},
    'decide': {'texto': 'e2e M7: ainda está por aí?'},
    'puxa_config_digitando': {'subdominio': SUBDOMAIN, 'sunshine_app_id': 'app-b2b', 'ai_agent_avatar_url': 'https://example.com/cema.png'},
    'filtra_e_limpa_dados': {'ticketId': CHAT},
    'monta_payloads': {'zendesk_ticket_id': TICKET, 'zendesk_ticket_payload': {'ticket': {
        'status': 'solved', 'custom_fields': [{'id': 21537600796443, 'value': 'cancelamento_interno'}],
        'comment': {'body': 'e2e M7: tabulação automática (nota interna).', 'public': False}}}},
}

CREDENTIALS = {
    'zendeskApi': {'id': 'sdZendeskCompat01', 'name': 'ServiceDesk (compat Zendesk)'},
    'httpHeaderAuth': {'id': 'sdSunshineCompat1', 'name': 'ServiceDesk Sunshine'},
}

VERIFY = r"""
const j = (n) => { try { return $(n).first().json; } catch (e) { return { __erro: String(e) }; } };
const all = (n) => { try { return $(n).all().map(i => i.json); } catch (e) { return []; } };
const checks = {
  ticket: j('puxa_ticket').id === %(ticket)d && !!(j('puxa_ticket').via?.source?.to?.address),
  comentarios: (j('puxa_comentarios_anexos').comments || []).length >= 2 && Array.isArray(j('puxa_comentarios_anexos').users),
  ccs: (j('puxa_CCs').users || []).some(u => u.email === 'agencia.e2e@agencia-exemplo.example'),
  membros: (j('puxa_membros_suporte').group_memberships || []).length === 2,
  busca: all('busca_tickets_cema').flatMap(p => p.results || []).some(r => r.id === %(ticket)d),
  audits: all('puxa_audits').flatMap(p => p.audits || []).some(a => (a.events || []).some(e => e.field_name === 'assignee_id')),
  autores: (j('puxa_autores').users || []).map(u => u.role).sort().join(',') === 'admin,agent',
  email_notifications: Array.isArray(j('email_notifications_get_invalid').email_notifications),
  disponibilidade: (j('puxa_agentes_suporte').data || []).length === 2,
  autor_comentario: j('puxa_autor_comentario').user?.role === 'agent',
  tags: (j('marca_no_ai').tags || []).includes('no_ai'),
  users_grupo: (j('puxa_users_grupo_suporte').users || []).length === 2,
  conversation_log: (j('puxa_conversation_log').events || []).length >= 1,
  sunco_user_id: j('extrai_sunco_user_id').sunco_user_id === '%(sunco)s',
  conversa_sunshine: (j('puxa_conversation_id').conversations || [])[0]?.id === '%(uuid)s',
  mensagens_sunshine: (j('puxa_mensagem_sunshine').messages || []).length >= 1,
  envia_aviso: !!(j('envia_aviso').messages || [])[0]?.id,
  reatribui_cema: j('reatribui_cema').assignee_id === %(ai)d,
  cataloga: j('atualiza_ticket_').status === 'solved',
};
const falhas = Object.entries(checks).filter(([, ok]) => !ok).map(([k]) => k);
return [{ json: { ok: falhas.length === 0, total: Object.keys(checks).length, falhas, checks } }];
""" % {'ticket': TICKET, 'sunco': SUNCO, 'uuid': UUID, 'ai': AI}


def load_nodes():
    found = {}
    for path in glob.glob(os.path.join(EXPORT_DIR, '*.json')):
        wf = json.load(open(path))
        if not wf.get('active'):
            continue
        for node in wf['nodes']:
            key = (wf['name'], node['name'])
            if key in REAL_NODES:
                found[key] = node
    missing = [k for k in REAL_NODES if k not in found]
    if missing:
        sys.exit(f'nós não encontrados na exportação: {missing}')
    return found


def set_node(name, values, x):
    assignments = [{'id': f'{name}-{k}', 'name': k, 'value': v if not isinstance(v, (dict, list)) else json.dumps(v),
                    'type': 'number' if isinstance(v, int) else ('object' if isinstance(v, dict) else ('array' if isinstance(v, list) else 'string'))}
                   for k, v in values.items()]
    return {'id': f'set-{name}', 'name': name, 'type': 'n8n-nodes-base.set', 'typeVersion': 3.4, 'position': [x, 0],
            'parameters': {'assignments': {'assignments': assignments}, 'options': {}}}


def main():
    found = load_nodes()
    nodes = [{'id': 'trigger', 'name': 'Inicio', 'type': 'n8n-nodes-base.manualTrigger', 'typeVersion': 1, 'position': [0, 0], 'parameters': {}}]
    x = 200
    for name, values in INPUTS.items():
        nodes.append(set_node(name, values, x))
        x += 200
    for key in REAL_NODES:
        node = copy.deepcopy(found[key])
        node['id'] = f'real-{key[1]}'
        node['position'] = [x, 200]
        node.pop('webhookId', None)
        node.pop('retryOnFail', None)
        node.pop('onError', None)
        node['credentials'] = {kind: CREDENTIALS[kind] for kind in (node.get('credentials') or {}) if kind in CREDENTIALS}
        nodes.append(node)
        x += 200
    nodes.append({'id': 'verifica', 'name': 'verifica', 'type': 'n8n-nodes-base.code', 'typeVersion': 2, 'position': [x, 0],
                  'parameters': {'jsCode': VERIFY}})
    connections = {}
    for current, following in zip(nodes, nodes[1:]):
        connections[current['name']] = {'main': [[{'node': following['name'], 'type': 'main', 'index': 0}]]}
    workflow = {'id': 'sdZendeskCompatE2E', 'name': 'e2e M7 - API de compatibilidade com o Zendesk', 'active': False,
                'nodes': nodes, 'connections': connections, 'settings': {'executionOrder': 'v1'}, 'pinData': {}}
    json.dump([workflow], sys.stdout, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
