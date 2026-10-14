# Workflows n8n do ServiceDesk (WF00–WF12)

Versão 1, de 2026-10-13 (agente A1). Branch `feat/n8n-workflows`. Os JSON em `workflows/` são **gerados** por `tools/build_workflows.py` (não edite à mão: mude o gerador e rode de novo).

O n8n **orquestra**: avisos, prioridade, etiquetas, notificações ao cliente, reconciliação agendada, relatórios. A lógica transacional (contato, ticket, máquina de estados, SLA, idempotência, gravações) fica no **sd-ops** (A2); transcrição e QA no **qa-pipeline** (A3). Contratos: `servicedesk/docs/integrations/WEBHOOK_CONTRACTS.md` (§8 é o contrato vinculante do sd-ops) e `EVENT_LIFECYCLE.md`.

## 1. Workflows

| Arquivo | Workflow | Gatilho | Faz | sd-ops usado |
|---|---|---|---|---|
| `wf00.json` | Erros dos workflows | Error Trigger | nota na conversa interna de operações (sem dados pessoais) | — |
| `wf01.json` | Ligação recebida | `POST /webhook/sd/wf01-ligacao-recebida` (`call.started`) | se o sd-ops não atribuiu agente nem time, atribui o time pela fila (mapa) e registra nota | — |
| `wf02.json` | Encerramento | `.../sd/wf02-encerramento` (`call.ended`, `recording.stored`, `recording.failed`) | gravação esperada e ausente após 60 min → alerta; falha permanente → nota no ticket + alerta | `GET /calls/{id}` |
| `wf03.json` | Ligação perdida | `.../sd/wf03-perdida` (`call.missed`) | prioridade alta, etiqueta `retorno_pendente` (mescla com as atuais), nota com a tarefa de retorno | — |
| `wf04.json` | Escalonamento | `.../sd/wf04-escalonamento` (`ticket.escalated`) | prioridade urgente, supervisores do time como participantes, nota | `GET /tickets/{id}` |
| `wf05.json` | WhatsApp pós-atendimento | `.../sd/wf05-whatsapp-pos-atendimento` (`ticket.status_changed` → `resolvido`) | template aprovado, **só com opt-in** (`sd_whatsapp_optin`), horário 8–20 h seg–sáb, 1 vez por ticket; **`dry_run=true`** | `GET /tickets/{id}`, `POST /notifications/log`, `POST /tickets/{id}/links` |
| `wf06.json` | E-mail de protocolo | `.../sd/wf06-email-protocolo` (`ticket.created`) | responde na thread de e-mail ou abre conversa na inbox de e-mail e vincula; 1 vez por ticket; **`dry_run=true`** | idem |
| `wf07.json` | CSAT | `.../sd/wf07-csat` (`ticket.status_changed` → `resolvido`) | espera 2 h; se não reabriu, CSAT por template de WhatsApp (telefonia sem pesquisa 55PBX); e-mail/chat usam o CSAT nativo do Chatwoot; **`dry_run=true`** | idem |
| `wf08.json` | Reabertura | `POST /webhook/sd/wf08-chatwoot-<segredo>` (webhook do **Chatwoot**, `message_created`) | cliente cita protocolo: mesmo contato → reabre (resolvido) ou o sd-ops cria a continuação (encerrado/cancelado) e vincula a conversa; aberto → só vincula; outro contato → só nota para verificar identidade | `GET /tickets/{protocolo}`, `POST /tickets/{id}/reopen`, `POST /tickets/{id}/links` |
| `wf09.json` | Reconciliação | cron 03:00 + `.../sd/wf09-reconciliar` (manual) | pede ao sd-ops a reconciliação do dia anterior pelo Report02; divergência/erro → alerta | `POST /reconciliations` |
| `wf10.json` | Alertas de SLA | cron a cada 15 min + `.../sd/wf10-sla` (`sla.breached`) | SLA vencendo em 60 min → nota (1 vez por prazo, *static data*); violado → urgente + nota + alerta | `GET /sla/at-risk`, `GET /tickets/{id}` |
| `wf11.json` | QA crítico | `.../sd/wf11-qa-critico` (`qa.completed`, publicado pelo A3) | nota < mínimo (60) ou alerta crítico → supervisor participante, nota com link do console de QA, registro no ticket | `GET /calls/{id}`, `POST /tickets/{id}/notes` |
| `wf12.json` | Relatório gerencial | cron segunda 08:00 | resumo de 7 dias (números agregados) na conversa interna de operações | `GET /reports/summary`, `GET /metrics/telephony`, `GET /metrics/tickets` |

Mapeamento para o prompt mestre §9: WF01 "55PBX → validação → contato → ticket → conversa → atribuição" — validação, contato, ticket e conversa são feitos pelo sd-ops (transacional); o WF01 cobre a atribuição de reserva e o aviso. O mesmo vale para WF02 (registro final/gravação/transcrição/QA são do sd-ops/A3; o WF02 acompanha e alerta).

## 2. Importar (instância do cliente, por quem administra o n8n)

1. Criar **3 credenciais** do tipo *Header Auth* (os IDs nos JSON são placeholders `REPLACE_*`; ao importar, o n8n pede para escolher a credencial):

   | Placeholder | Nome sugerido | Header | Valor |
   |---|---|---|---|
   | `REPLACE_CRED_SDOPS_SERVICE_TOKEN` | SD-OPS: token de serviço do n8n | `Authorization` | `Bearer sdsvc_…` (gerado no sd-ops: `python -m sd_ops new-service-token n8n`; escopos `tickets:read`, `tickets:write`, `calls:read`, `notify:send`, `reconcile:run`, `reports:read`) |
   | `REPLACE_CRED_CHATWOOT_N8N` | ServiceDesk: api_access_token da Integração n8n | `api_access_token` | token do usuário "Integração n8n" (papel **agente**) |
   | `REPLACE_CRED_SDOPS_WEBHOOK_TOKEN` | SD-OPS → n8n: X-SD-Webhook-Token | `X-SD-Webhook-Token` | mesmo valor do `token_ref` da rota em `ops.automation_routes` |

2. Importar: *Workflows > Import from file* (ou `n8n import:workflow --separate --input=workflows/`). Os workflows entram **inativos**.
3. Em cada workflow, abrir o nó **`config`** e preencher: `sdops_base_url`, `chatwoot_base_url`, `chatwoot_account_id`, `ops_alert_conversation_id` (conversa interna "Operações" que recebe alertas), `console_base_url` e os campos próprios (mapa fila→time, supervisores por time, inboxes, template, `dry_run`). No WF10 há também o nó `config_evento`.
4. WF08: trocar `REPLACE_SEGREDO_LONGO` no path por um valor aleatório (`openssl rand -hex 24`) e cadastrar a URL no webhook da conta do Chatwoot (evento `message_created`).
5. Settings de cada workflow: *Error workflow* = "SD WF00 - Erros dos workflows".
6. Publicar (ativar) primeiro WF00, WF01–WF04, WF08–WF12; WF05–WF07 só depois da aprovação, trocando `dry_run` para `false`.
7. No sd-ops, cadastrar as rotas (`/admin/automation-routes`) com a URL de produção de cada webhook.

## 3. Regras embutidas

| Regra | Como |
|---|---|
| Sem segredo no JSON | credenciais por referência; URLs base no nó `config`; o validador recusa valor que pareça token |
| Anti-loop | (1) webhook recusa origem diferente de `X-SD-Origin: sd-ops`; (2) evento com `caused_by = n8n:<mesmo WF>` é ignorado; (3) toda chamada ao sd-ops leva `X-SD-Origin: n8n` + `X-SD-Workflow`, e o sd-ops marca `caused_by`; (4) toda mensagem criada no Chatwoot leva `content_attributes.sd_origin` e o WF08 ignora mensagens com essa marca ou de agente |
| Idempotência | `Idempotency-Key` em toda chamada ao sd-ops (`<execução>:<nó>:<item>`). Envios ao cliente e alertas de SLA: **no máximo 1 vez por chave** (`whatsapp_pos_atendimento:<ticket>`, `csat:<ticket>`, `email_protocolo:<ticket>`, `sla:<ticket>:<métrica>:<prazo>`), guardada no *static data* do workflow (30 dias; 7 no SLA) **antes** do envio; o registro de auditoria vai para `POST /notifications/log` |
| Replay | eventos com `X-SD-Timestamp` a mais de 15 min são ignorados |
| Etiquetas | `POST /labels` do Chatwoot sobrescreve: o WF03 lê as atuais e grava a união |
| Atributos | qualquer `custom_attributes` no Chatwoot exige `merge: true` (sem ele o hash inteiro é substituído) — conferido pelo validador |
| LGPD | alertas sem telefone/CPF; WhatsApp só com opt-in, horário e template; nada de payload bruto no n8n |
| Compatibilidade | só nós/versões já usados na instância do cliente (webhook 2, code 2, if 2.2, switch 3.2, set 3.4, httpRequest 4.2, scheduleTrigger 1.2, wait 1.1, noOp 1, errorTrigger 1) |

## 4. Validação e testes

```bash
cd servicedesk/integrations/n8n
python3 tools/build_workflows.py --check          # JSON idênticos ao gerador
python3 tools/validate_workflows.py --node-check  # estrutura, conexões, segurança, contrato, JS compilado
python3 tools/test_code_nodes.py                  # lógica dos nós Code com dados sintéticos (Node.js)
bash tools/e2e/run_e2e.sh                         # n8n descartável (docker) + mock do sd-ops/Chatwoot
```

Resultados de 2026-10-13: ver §6.

## 5. Estado da implementação no sd-ops (conferência com o código do A2)

Conferido em 2026-10-13 contra o **código e o OpenAPI do sd-ops** (branch `feat/integracao-55pbx`, commit `2201722d35`, `servicedesk/integrations/pbx-bridge/openapi.json`) com `python3 tools/validate_workflows.py --openapi .../openapi.json`: **as 12 rotas usadas existem**. Os corpos e respostas foram ajustados ao código real:

| Endpoint | Ajuste feito nos workflows (leitura de `sd_ops/api.py`, `views.py`, `tickets.py`) |
|---|---|
| `GET /tickets/{ref}` | `ref` aceita UUID, protocolo (`B2B-2026-000123`) ou numérico; campos `status` (não `state`), `channel` (`phone`, `email`…), `conversations` = lista de IDs (a 1ª é a primária), `contact_id` |
| `POST /tickets/{ref}/reopen` | corpo `TransitionIn` exige `to` → `{"to":"em_atendimento","reason":…}`; para `encerrado`/`cancelado` o próprio sd-ops cria o ticket de continuação (o WF08 não chama mais `POST /tickets`) |
| `POST /tickets/{ref}/notes` | `{"kind":"nota_interna","body":…,"post_to_chatwoot":false}` (`kind` ∈ `registro`, `disposicao`, `nota_interna`) |
| `POST /notifications/log` | `NotificationLogIn` = `channel` (obrigatório), `ticket_id`, `template`, `status`, `detail`; responde `201 {"ok":true}` e **não é idempotente** → a regra "1 envio por ticket" ficou no n8n (*static data* do workflow, nó `ja_enviado`), e o nó também respeita o header `Idempotent-Replay: true` caso o sd-ops passe a aplicar `Idempotency-Key` nessa rota |
| `GET /sla/at-risk` | resposta `{"items":[{ticket_id, protocol, metric, due_at, breached,…}]}` sem conversa → o WF10 busca o ticket para achar `conversations[0]`; alerta 1 vez por ticket/métrica/prazo (*static data*) |
| `POST /reconciliations` | `202 {rows, new}`, `202 {skipped}` (sem `PBX_API_KEY`) ou `502 {error}` → o WF09 alerta em erro, em "não executada" e quando `new` (ligações que o tempo real não entregou) passa de `alerta_novas_acima` |
| `GET /calls/{id}` | `conversation_id`, `tickets[]`, `recordings[].status` (`stored`/`failed`) |
| Escopos do token de serviço | `tickets:read`, `tickets:write`, `calls:read`, `notify:send`, `reconcile:run`, `reports:read`. **Atenção:** `CTI_AUTH.md` traz o exemplo `"n8n": {"roles": ["service_read"]}`; com só leitura o WF08/WF09/WF11 recebem 403 |

Pendências que dependem de outros agentes:

| Item | Situação |
|---|---|
| `qa.completed` chegando ao WF11 | publicado pelo qa-pipeline (A3); o sd-ops não o roteia para o n8n (§8.2 do contrato). Definir quem entrega (rota do sd-ops ou dispatcher do A3) |
| Tarefa formal de revisão de QA | não existe endpoint; o WF11 usa nota no ticket + supervisor como participante |
| Prioridade | o WF03/WF04 mudam a prioridade **da conversa** no Chatwoot (`urgent/high/…`); a prioridade do ticket no sd-ops (`baixa/normal/alta/urgente`) é do sd-ops (`/escalate`, classificação de perdida). Se o sd-ops passar a sincronizar a prioridade, retirar esses nós |

## 6. Evidências (2026-10-13)

| Teste | Resultado |
|---|---|
| `build_workflows.py --check` | JSON idênticos ao gerador |
| `validate_workflows.py --node-check` | 13 arquivos, 35 nós Code compilados com Node.js, **0 erros** |
| `validate_workflows.py --openapi` (sd-ops `2201722d35`) | **12/12 rotas existem** |
| Teste negativo do validador (conexão quebrada, segredo, versão inexistente, credencial real, nó solto, JS inválido) | **6/6 detectados** |
| `test_code_nodes.py` | **32/32 casos**; achou 1 bug (regex do protocolo não aceitava `B2B-…`), corrigido |
| Importação no n8n **2.43.4** descartável | **13/13 importados e publicados** |
| e2e `run_e2e.sh` (n8n 2.43.4 + mock com as respostas do sd-ops real) | 1ª rodada: 14/15 — o WF01 revelou bug real (resposta em array vira vários itens no nó HTTP), corrigido no WF01 e no WF10. **Rodada final: 15/15** (WF01–WF06, WF08–WF11, anti-loop, token errado = 403, envio único por ticket) |

**Nada foi criado ou alterado no n8n do cliente** (só leitura via API: `GET /healthz`, `GET /api/v1/workflows?limit=1`).
