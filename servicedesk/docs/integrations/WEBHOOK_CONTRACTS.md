# Contratos de webhook e de API entre 55PBX, sd-ops, Chatwoot, URA e n8n

Versão 1, de 2026-10-13 (agente A1). Os contratos de **entrada da 55PBX** seguem o manual oficial (F1/F3, ver `55PBX_API_MAPPING.md`). Os contratos **internos** (sd-ops ↔ n8n, URA) são propostos aqui e são implementados pelo A2. A conferência com as rotas reais do código do A2 está no §7 (atualizada ao fim da rodada).

## 1. Entrada: 55PBX → sd-ops ("Tempo real por URL")

| Item | Contrato |
|---|---|
| URL a cadastrar no painel 55PBX | `https://<domínio>/sd-ops/api/v1/webhooks/55pbx/<segredo>` (legado aceito: `/integracoes/55pbx/webhook/<segredo>` da pbx-bridge) |
| Métodos | `POST` e `PUT` (o painel permite os dois) |
| Autenticação | (a) segredo ≥ 32 bytes no caminho, comparado em tempo constante; (b) header `token` = "Chave (token)" do painel (F1 p.5), também em tempo constante, quando configurado; (c) opcional: IP de origem em `ALLOWED_IPS` (pendente: IPs da 55PBX) |
| Corpo | JSON (objeto; tolera lista, embrulho `data`/`call`/`payload`, form-urlencoded e o literal `ISODate("…")` do manual) |
| Limites | `MAX_BODY_BYTES` 256 KiB → 413; rate limit 50 req/s por IP → 429 |
| Respostas | `202 {"accepted":true,"id":"<uuid>"}` após gravar em `ops.webhook_inbox`; `200 {"duplicate":true}` se `dedupe_key` já existe; `404` segredo errado (sem detalhe); `401` token errado; `413`; `503` se `ENABLED=false` |
| Tempo | ≤ 300 ms (nada de Chatwoot, áudio ou IA no request) |
| Log | só versão mascarada (telefone, CPF, número na URL) |

Exemplo (fictício, campos do readme `objeto-de-resposta`):

```json
{
  "central_id": "3855", "branch_mask": "5005", "call_id": "1760380000.1234",
  "call_date": "2026-10-13 14:23:41", "call_type": "receptive",
  "call_number": "+5511900000000", "call_area_code": "11", "call_country_code": 55,
  "call_queue": "FILA_SUPORTE_1", "call_status": "call_attended", "call_disconnection": "externo",
  "call_time": "180", "call_duration": "150", "call_time_waiting": "30", "call_total_time": "180",
  "call_url_audio": "https://vsa19.55pbx.com/webphone/webphone-3855/2026/10/13/audio-....WAV",
  "branch_email": "ramal5005@exemplo.test"
}
```
Header: `token: <chave do painel>`.

## 2. Entrada: Chatwoot → sd-ops (webhook de conta)

| Item | Contrato |
|---|---|
| URL | `https://<domínio>/sd-ops/api/v1/webhooks/chatwoot/<segredo>` (rede interna preferida) |
| Assinaturas | `conversation_created`, `conversation_status_changed`, `conversation_updated`, `message_created` (e `contact_updated` para identidade) |
| Autenticação | `X-Chatwoot-Signature: sha256=HMAC_SHA256(secret, "<X-Chatwoot-Timestamp>.<corpo>")`; timestamp ≤ 300 s; deduplicação por `X-Chatwoot-Delivery` |
| Uso | sincronizar estado de negócio quando o agente muda o status da conversa; gatilho de atribuição (nota de agente em conversa 55PBX sem responsável); detectar resposta do cliente (Aguardando cliente → Em atendimento) |
| Anti-loop | ignorar se `sender`/`performer` é usuário de integração, se `message.content_attributes.sd_origin` existe, ou se `conversation.custom_attributes.sd_last_writer` ∈ {sd-ops, n8n} e a mudança é a última escrita registrada por nós (comparação com `ops.ticket_events.last_synced_hash`) |
| Respostas | `204` (sempre rápido; processamento assíncrono) |

## 3. Saída: sd-ops → n8n (eventos de domínio)

| Item | Contrato |
|---|---|
| Transporte | `POST` HTTPS para o webhook de produção do workflow (`https://<n8n>/webhook/sd/<wfXX>`) |
| Autenticação | header **`X-SD-Webhook-Token`** validado pelo nó Webhook do n8n com credencial *Header Auth* (sem segredo no JSON do workflow) **+** `X-SD-Signature: sha256=HMAC_SHA256(secret, "<X-SD-Timestamp>.<corpo>")` para auditoria |
| Headers | `X-SD-Event-Id`, `X-SD-Event-Type`, `X-SD-Timestamp`, `X-SD-Origin: sd-ops`, `X-Correlation-Id` |
| Corpo | envelope de `EVENT_LIFECYCLE.md` §5 |
| Resposta esperada | `2xx` em ≤ 10 s (o workflow responde logo e processa depois); outro código → retentativa (30 s … 1 h, 8×) → DLQ |
| Roteamento | `ops.automation_routes` (`call.started`→WF01, `call.ended`→WF02, `call.missed`→WF03, `ticket.escalated`→WF04, `ticket.status_changed`(resolvido)→WF05/WF07, `ticket.created`→WF06, `ticket.reopen_requested`→WF08, `sla.*`→WF10, `qa.completed` com alerta→WF11) |

## 4. Entrada: n8n → sd-ops (ações)

| Item | Contrato |
|---|---|
| Autenticação | `Authorization: Bearer <token de serviço n8n>` (credencial n8n *Header Auth*), token com escopo (`tickets:write`, `calls:read`, `callbacks:write`, `reconcile:run`, `notify:send`), hash no banco, rotação |
| Headers obrigatórios | `X-SD-Origin: n8n`, `X-SD-Workflow: WFxx`, `Idempotency-Key: <execution_id>:<nó>` |
| Anti-loop | o sd-ops **não** reemite para o n8n eventos causados por requisição com `X-SD-Origin: n8n` do mesmo workflow (marca `caused_by` no outbox); profundidade máxima de cadeia = 2 (`X-SD-Hop`) |
| Erros | `400` validação, `401/403` token/escopo, `404`, `409` transição inválida (máquina de estados), `422` regra de negócio, `429`, `5xx` (n8n repete 3× com espera) |

### 4.1 Endpoints do sd-ops usados pelos workflows (proposta A1 → conferir com A2, §7)

| Método e caminho | Uso | WF |
|---|---|---|
| `GET /sd-ops/api/v1/health` | saúde | todos (alerta) |
| `GET /sd-ops/api/v1/calls/{id}` | detalhe da ligação (pernas, gravação, outcome) | WF01, WF02 |
| `POST /sd-ops/api/v1/tickets` | criar ticket (normalmente o próprio sd-ops cria; o n8n só em fluxo manual) | WF03 |
| `GET /sd-ops/api/v1/tickets/{id}` / `GET /sd-ops/api/v1/tickets?protocolo=` | consultar | WF04–WF08 |
| `POST /sd-ops/api/v1/tickets/{id}/transitions` `{"to":"em_atendimento","reason":"..."}` | mudar estado (valida a máquina) | WF04, WF08 |
| `POST /sd-ops/api/v1/tickets/{id}/links` `{"call_id"|"conversation_id"}` | vínculo N:N | WF08 |
| `POST /sd-ops/api/v1/callbacks` / `PATCH /sd-ops/api/v1/callbacks/{id}` | tarefa de retorno | WF03 |
| `POST /sd-ops/api/v1/dial` `{"agent_email","phone","ticket_id"}` | click-to-call (chama a 55PBX) | sd-console (não o n8n) |
| `POST /sd-ops/api/v1/reconciliations` `{"from","to"}` | pedir reconciliação | WF09 |
| `GET /sd-ops/api/v1/sla/at-risk?within=60` | tickets com SLA em risco | WF10 |
| `GET /sd-ops/api/v1/qa/evaluations/{id}` | avaliação (A3) | WF11 |
| `POST /sd-ops/api/v1/qa/evaluations/{id}/review-tasks` | tarefa de revisão humana | WF11 |
| `GET /sd-ops/api/v1/reports/summary?from&to` | números gerenciais | WF12 |
| `POST /sd-ops/api/v1/notifications/log` | registrar envio (WhatsApp/e-mail/CSAT) e opt-out; **idempotente** por `dedupe_key` (implementado, §8.4.1) | WF05, WF06, WF07 |

## 5. Entrada: URA dinâmica (55PBX) → sd-ops (consulta de protocolo)

| Item | Contrato |
|---|---|
| Configuração no painel | Integração > Padrão 55PBX, método `GET`, URL `https://<domínio>/sd-ops/api/v1/ura/tickets/:protocolo?ani=:telefone` (variáveis declaradas em "Configurar variáveis de envio") |
| Autenticação | token fixo em header (`X-SD-URA-Token`, cadastrado no painel) + IP de origem; alternativa Basic |
| Resposta 200 (achatada pela URA) | `{"encontrado":"sim","situacao":"em_atendimento","situacao_fala":"em atendimento","proxima_acao":"aguardando retorno da equipe","fila":"FILA_SUPORTE_1"}` — **sem** nome, e-mail, CPF ou valores |
| Regra de autorização | só responde detalhes se o `ani` (telefone que liga) pertence ao contato do ticket; senão `{"encontrado":"sim","situacao_fala":"localizado; para detalhes fale com um atendente"}`. Protocolo inexistente: `{"encontrado":"nao"}` (200, para a URA seguir o fluxo) |
| Limites | ≤ 1,5 s; 5 consultas/min por `ani` (anti-enumeração); auditoria de cada consulta |
| Pendente | timeout da URA e IP de origem (fornecedor) |

## 6. Saída: sd-ops → 55PBX

| Chamada | Contrato | Status |
|---|---|---|
| Discagem | `POST {PBX_DIAL_URL}` (padrão `https://ws.55pbx.com:20500/api/webphone/dial`), headers `client_code`, `api_key`, `Authorization: Bearer <JWT>`, corpo `{"email","phone"}` | **não testado** (sem credenciais); divergência de URL D9 |
| Report02 | `GET https://reportapi02.55pbx.com:50500/api/pbx/reports/metrics/{9 segmentos}`, header `key`, timeout ≥ 120 s (doc recomenda 7200 s) | testado só com mock |
| Gravação | `GET call_url_audio` (hosts permitidos) | bloqueado por IP (T3) |

## 7. Conferência com o código do A2

Ver a seção "Estado da implementação" no fim do `README` dos workflows (`servicedesk/integrations/n8n/README.md`), que lista cada endpoint como **existe** / **pendente**, com o commit lido.

---

## 8. Implementação sd-ops (A2): contrato vinculante

Versão 1, de 2026-10-13 (agente A2). As §1–§7 acima são a proposta do A1. **Esta seção descreve o que o código do sd-ops implementa** e prevalece em caso de diferença. Adotei as propostas do A1 onde não conflitam com as decisões fixas do projeto. Código: `servicedesk/integrations/pbx-bridge/sd_ops/` (branch `feat/integracao-55pbx`). OpenAPI: `servicedesk/integrations/pbx-bridge/openapi.json`.

Convenções: JSON UTF-8; datas ISO 8601 em **UTC**; IDs internos UUID (texto); `tenant_id` = slug (`b2b`, `dev55`); telefone E.164. Erro: `{"error":"<codigo>","message":"<pt-BR>"}`. Recurso de outro tenant → **404**.

### 8.1 Entradas

| Rota | Autenticação | Resposta |
|---|---|---|
| `POST`/`PUT /sd-ops/api/v1/webhooks/55pbx/{segredo}` e o legado `POST`/`PUT /integracoes/55pbx/webhook/{segredo}` (mesmo código) | segredo no caminho (≥ 32, tempo constante; o hash identifica o tenant em `ops.integration_accounts`); header `token` quando a conta tiver `webhook_token_ref`; `ALLOWED_IPS` opcional | **202** `{"accepted":true,"id":<inbox_id>,"duplicate":false,"correlation_id":"…"}` após gravar em `ops.webhook_inbox`; **200** `{"accepted":true,"duplicate":true,"id":…}` para corpo idêntico; 404 segredo; 401 token; 413; 503 `ENABLED=false` |
| `POST /sd-ops/api/v1/webhooks/chatwoot/{segredo}` e o legado `POST /integracoes/55pbx/servicedesk-events/{segredo}` | HMAC `X-Chatwoot-Signature` + `X-Chatwoot-Timestamp` (≤ 300 s) quando `CHATWOOT_WEBHOOK_HMAC_SECRET` estiver definido | **204** (nova) / 200 (legado); o corpo vai para `ops.webhook_inbox` (`source=chatwoot`) e é processado pelo worker |

Campos 55PBX lidos, inconsistências do manual e regra de fase: `EVENT_LIFECYCLE.md`, seção "Implementação sd-ops". `call_type = sms` é registrado e ignorado.

### 8.2 Stream `sd:events` (Redis DB 7)

`XADD sd:events MAXLEN ~ 200000 * type <type> data <envelope JSON>`, publicado pela outbox transacional (entrega pelo menos uma vez; deduplicar por `id`). Envelope **fixo** do projeto, com campos extras de rastreio compatíveis com a proposta do A1:

```json
{"type":"recording.stored","id":"<uuid v5 determinístico>","occurred_at":"2026-10-13T18:06:40Z","tenant_id":"dev55",
 "version":1,"source":"sd-ops","correlation_id":"…","caused_by":null,
 "subject":{"call_id":"…","provider_call_id":"…","ticket_id":"…","conversation_id":1234},
 "payload":{ "…": "…" }}
```

`payload` é o campo canônico (o `data` da proposta do A1 **não** existe). `id` é o `event_id`.

| type | Quando | `payload` |
|---|---|---|
| `call.started` | 1ª vez que a chamada lógica é vista | campos comuns* |
| `call.ended` | a chamada lógica terminou (todas as pernas encerradas) | comuns + `outcome`, `talk_s`, `wait_s`, `total_s`, `disconnection`, `legs`, `has_recording_url` |
| `call.transferred` | perna encerrada com `call_transfer_id` (ou perna nova com `call_id_origin`) | comuns + `from_leg_id`, `to_provider_call_id`, `from_branch`, `from_queue`, `transfer_seq` |
| `call.missed` | com `call.ended`, se `outcome` ∈ `missed`, `abandoned_ura`, `abandoned_queue`, `after_hours`, `dropped` | comuns + `outcome`, `callback_task_id` |
| `recording.stored` | gravação validada no storage privado | `recording_id`, `call_id`, `leg_id`, `ticket_id`, `conversation_id`, `storage_key`, `mime`, `duration_s`, `size_bytes`, `sha256`, `expected_talk_s`, `integrity` (`ok`, `duration_mismatch` ou `short`) |
| `recording.failed` | falha permanente | `recording_id`, `call_id`, `reason` |
| `ticket.created`, `ticket.status_changed`, `ticket.reopened`, `ticket.escalated` | domínio de ticket | `ticket_id`, `protocol`, `protocol_numeric`, `from`, `to`, `reason`, `actor`, `priority`, `team_id`, `assignee_id` |
| `sla.breached` | meta vencida | `ticket_id`, `protocol`, `metric`, `due_at` |
| `callback.created` | tarefa de retorno | `callback_task_id`, `call_id`, `ticket_id`, `reason`, `due_at` |

\* comuns: `call_id`, `leg_id`, `provider_call_id`, `root_provider_call_id`, `direction` (`receptivo`, `ativo`, `interno`), `number_masked` (o número completo **nunca** vai ao stream), `contact_id`, `conversation_id`, `ticket_id`, `ticket_protocol`, `branch`, `agent_email`, `queue`, `started_at`, `answered_at`, `ended_at`.

`ticket_id`/`conversation_id` podem ser `null` (política sem ticket, conversa ainda não sincronizada). O `outcome` `abandoned_ura` equivale ao `abandoned_ivr` da proposta do A1. `transcription.completed` e `qa.completed` são do A3: o qa-pipeline os publica no `sd:events` e o sd-ops não os consome do stream. **Exceção (integração final):** o `qa.completed` que chega por REST (`POST /analysis-results`, §8.8) é **repassado às rotas do n8n** pela ponte do §8.3 (não é publicado de novo no stream, para não duplicar).

### 8.3 Ponte para o n8n (implementada)

Cada evento do stream também é entregue, pela outbox, às rotas ativas de `ops.automation_routes` (`event_types` aceita `*` no fim, ex. `ticket.*`): `POST <url>` com o envelope e os headers `X-SD-Webhook-Token` (valor da variável `token_ref`), `X-SD-Signature: sha256=HMAC(<segredo de secret_ref>, "<X-SD-Timestamp>.<corpo>")`, `X-SD-Timestamp`, `X-SD-Event-Id`, `X-SD-Event-Type`, `X-SD-Origin: sd-ops`, `X-Correlation-Id`. 2xx = entregue; outro código → retentativa exponencial (15 s … 1 h, `OUTBOX_MAX_ATTEMPTS`) → DLQ. Registro por entrega em `ops.automation_executions`. **Anti-loop**: evento causado por requisição com `X-SD-Origin: n8n` + `X-SD-Workflow: WFxx` leva `caused_by: "n8n:WFxx"` e não é reenviado à rota de mesmo `name`.

**`qa.completed` → WF11 (integração final).** Ao receber `POST /analysis-results` com `kind=qa` e `status` `completed` ou `partial` (inédito), o sd-ops grava na outbox um item `fanout` com o envelope abaixo, na mesma transação. O worker o entrega às rotas que assinam `qa.completed` exatamente como os eventos de chamada (mesmos headers, HMAC, retentativa, DLQ, `automation_executions`, anti-loop por `caused_by`), mas **sem XADD** no `sd:events`. O `id` é determinístico (`qa.completed` + tenant + `external_id`): repetir o POST devolve `{"duplicate":true}` e não reenvia. Rota sugerida: `{"name":"WF11","event_types":["qa.completed"],"url":"https://<n8n>/webhook/sd/wf11-qa-critico",…}`.

```json
{"type":"qa.completed","id":"<uuid v5>","source":"sd-ops","caused_by":null,"occurred_at":"<completed_at>",
 "subject":{"call_id":"…","ticket_id":"…","conversation_id":1234,"recording_id":"…"},
 "payload":{"evaluation_id":"42","external_id":"qa.qa_evaluations:42","analysis_ref_id":7,"status":"completed",
            "score":41.5,"alerts":["reclamacao","supervisor"],"critical_alerts":["reclamacao","supervisor"],
            "rubric_version":3,"console_url":"https://…/sd-console/qa/avaliacoes/42","recording_id":"…","call_id":"…",
            "ticket_id":"…","ticket_protocol":"B2B-2026-000123","conversation_id":1234,"is_recommendation":true,
            "origin":"qa-pipeline"}}
```

`ticket_id`/`conversation_id` vêm do vínculo chamada→ticket (o ticket mais antigo da chamada) e da conversa da chamada; podem ser `null`. `critical_alerts` = `data.critical_alerts` ou, na falta, `data.alerts` (o qa-pipeline só manda alertas que pedem revisão). `transcription`/`summary` e `status=failed` não são repassados.

### 8.4 REST `/sd-ops/api/v1`

Autenticação: `CTI_AUTH.md` (sessão do agente ou token de serviço com `scopes`). Requisições de serviço aceitam `Idempotency-Key` (resposta guardada 24 h em `ops.idempotency_keys`).

| Rota | Quem | Função |
|---|---|---|
| `GET /health`, `GET /ready`, `GET /sd-ops/metrics` (Prometheus) | livre, livre, token opcional | saúde, prontidão (banco, Redis, migration), métricas técnicas |
| `POST /auth/session`, `GET /auth/me`, `POST /auth/logout` | — | sessão do CTI |
| `GET /capabilities` | agente+, qualquer token de serviço | capacidades do CTI **para este usuário** (§8.10); o sd-console usa só esta rota (sem sondagem) |
| `GET /context?conversation_id=&contact_id=&phone=` | agente+ | contato, identificação (`unique`, `ambiguous`, `none`), tickets abertos com SLA, últimas chamadas, retornos pendentes, chamada ativa |
| `GET /calls?conversation_id=&contact_id=&ticket_id=&phone=&needs_classification=`, `GET /calls/{id}` | agente+, `calls:read` | chamadas com pernas, transferências, gravações (metadados) e tickets |
| `POST /dial`, `GET /dial/{id}` | agente+ | click-to-call (8.5) |
| `GET /tickets?status=&protocolo=&contact_id=&conversation_id=`, `POST /tickets`, `GET /tickets/{id ou protocolo}`, `PATCH /tickets/{id}` | agente+, `tickets:read`/`tickets:write` | domínio de ticket (`TICKET_DOMAIN.md`) |
| `POST /tickets/{id}/transitions` `{"to","reason"}`, `/escalate`, `/reopen` | agente+ (encerrar/cancelar: supervisor+) | máquina de estados; 409 se a transição não existe |
| `POST /tickets/{id}/notes`, `POST /tickets/{id}/links`, `GET /tickets/{id}/events` | agente+ | registro/disposição/nota interna (opcionalmente espelhada como nota privada no Chatwoot); vínculos N:N; histórico |
| `GET /callbacks?status=`, `POST /callbacks`, `PATCH /callbacks/{id}` | agente+, `callbacks:write` | tarefas de retorno |
| `GET /recordings/{id}`, `GET /recordings/{id}/url`, `GET /recordings/stream/{token}` | 8.6 | gravação |
| `GET /metrics/telephony`, `GET /metrics/tickets`, `GET /reports/summary` | supervisor, qa, admin, `reports:read` | dashboards (fórmulas em 8.7); `?detail=1` lista os IDs |
| `GET /sla/at-risk?within=60` | supervisor+, `tickets:read` | tickets com SLA vencendo em N min |
| `POST /reconciliations` `{"from","to"}` | admin, `reconcile:run` | reconciliação pelo Report02 |
| `POST /notifications/log`, `GET /notifications/log?ticket_id=&dedupe_key=` | `notify:send` (GET também supervisor+) | registro **idempotente** de envio (WhatsApp/e-mail/CSAT) do n8n em `ops.notification_logs` + `audit_events` (§8.4.1) |
| `POST /analysis-results` | `analysis:write` (A3) | 8.8 |
| `/admin/agent-phone-mappings`, `/admin/ticket-open-rules`, `/admin/user-roles`, `/admin/automation-routes`, `/admin/dlq`, `/admin/dlq/{fila}/{id}/retry`, `/admin/sessions` | admin | operação |

#### 8.4.1 `POST /notifications/log` idempotente (integração final)

O n8n não guarda estado para "1 envio por ticket": a garantia é do sd-ops. Tabela `ops.notification_logs` (migration `0002`) com **único (`tenant_id`, `dedupe_key`)**, permanente (não expira como `ops.idempotency_keys`).

| Item | Contrato |
|---|---|
| Chave | `dedupe_key` no corpo (≤ 200 caracteres) ou, na falta, o header `Idempotency-Key`. Sem nenhum dos dois: **422** `dedupe_key_required` |
| Corpo | `{"channel","ticket_id","call_id","template","status","opt_out","detail","dedupe_key"}` |
| 1ª chamada | **201** `{"ok":true,"duplicate":false,"id":…,"dedupe_key":"…"}`; grava `notification_logs` (com `actor` e `caused_by`) e `audit_events` (`notification.<status>`) |
| Repetição (mesma chave, mesmo tenant) | **200** + header `Idempotent-Replay: true` e o registro **original** `{"ok":true,"duplicate":true,"id","dedupe_key","status","channel","ticket_id",…,"created_at"}`; nada é gravado. Concorrência: `INSERT … ON CONFLICT DO NOTHING` (teste com 6 requisições simultâneas → 1×201 + 5×200) |
| Chaves usadas pelos workflows | `whatsapp_pos_atendimento:<ticket>` (WF05), `csat:<ticket>` (WF07), `email_protocolo:<ticket>` (WF06); em `dry_run` o sufixo `:simulado`, para o envio real ainda acontecer quando o `dry_run` for desligado |
| Fluxo no n8n | registra **antes** de enviar (status `enviando`/`simulado`) e só envia se a resposta for `< 300` **sem** `Idempotent-Replay` (no máximo uma vez; falha depois do registro não reenvia sozinha) |

### 8.5 Click-to-call

`POST /dial {"phone":"+5511999990001","ticket_id":"…","conversation_id":1234,"contact_id":55}` (com token de serviço, também `agent_email`). Usuário → `ops.agent_phone_mappings` (ramal e **e-mail do ramal na 55PBX**) → valida E.164 → `POST {PBX_DIAL_URL}` com `client_code`, `api_key`, `Authorization: Bearer <JWT>` e corpo `{"email","phone"}` (readme "Discagem automática para ramal"). A resposta é sempre o resultado real:

| HTTP | Corpo | Quando |
|---|---|---|
| 200 | `{"dial_id","status":"accepted","provider_call_id":"…","message":"Ligação efetuada com sucesso"}` | 55PBX 200 + `status: OK` |
| 200 | `{"dial_id","status":"mock","simulated":true,"message":"MODO MOCK (DEV): nenhuma ligação foi feita"}` | `PBX_DIAL_MODE=mock` (só com `SDOPS_ENV=dev`) |
| 409 | `{"error":"dial_pending"}` | discagem do mesmo usuário há menos de `PBX_DIAL_PENDING_S` |
| 403 / 422 | `no_branch_mapping` / `invalid_phone` | |
| 502 | `{"dial_id","status":"rejected" ou "error","provider_http_status":404,"message":"E-mail inválido."}` | 55PBX recusou ou falhou (inclui 500 "Usuário com requisição pendente") |
| 503 | `{"error":"dial_disabled"}` | `PBX_DIAL_MODE=disabled` ou credenciais ausentes |

O `provider_call_id` devolvido amarra a ligação que chegar depois pelo webhook ao ticket e à conversa informados.

### 8.6 Gravação: acesso e storage

`GET /recordings/{id}/url` → `{"url":"/sd-ops/api/v1/recordings/stream/<token>","expires_at":"…","expires_in":300}`. O token é HMAC-SHA256 (`RECORDING_URL_SECRET`) de `recording_id + usuário + tenant + exp`, vale `RECORDING_URL_TTL_S` (300 s), aceita `Range` e nunca contém nem redireciona para a URL da 55PBX. Emissão e acesso vão para `ops.audit_events` (`recording.url_issued`, `recording.accessed`). O agente só ouve gravações de chamadas em que foi o agente ou de tickets atribuídos a ele.

Storage (o A3 lê): `SDOPS_STORAGE_BACKEND=local` (padrão, `SDOPS_STORAGE_DIR`, diretório 0700, arquivos 0600; o A3 monta o volume **somente leitura**) ou `s3` (`S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_REGION`; MinIO opcional). `storage_key` = `recordings/<tenant>/<AAAA>/<MM>/<recording_id>.<ext>`. O original validado é preservado; o MP3 anexado ao Chatwoot é cópia derivada.

### 8.7 Métricas (fórmulas)

Fonte: `ops.calls` (webhook **e** Report02). Período por `started_at` (`?from=&to=`, UTC). Filtros: `queue`, `branch`, `agent_email`, `direction`.

| Métrica | Fórmula |
|---|---|
| recebidas | chamadas lógicas `direction=receptivo` |
| atendidas | recebidas com `answered_at` ou `talk_s > 0` |
| abandonadas | recebidas com `outcome ∈ {abandoned_ura, abandoned_queue}` |
| perdidas | recebidas com `outcome ∈ {missed, after_hours, dropped}` |
| efetuadas / efetuadas_atendidas | `direction=ativo` / com `talk_s > 0` |
| TMA | média de `talk_s` das atendidas, por direção |
| TME | média de `wait_s` das recebidas atendidas (`tme_abandono`: das abandonadas) |
| nível de serviço | atendidas com `wait_s ≤ SL_THRESHOLD_S` (20) ÷ (atendidas + abandonadas com `wait_s > SL_SHORT_ABANDON_S` (5)) |
| taxa de abandono | abandonadas ÷ recebidas |
| transferidas | chamadas com `legs_count > 1` |
| retornos | `callback_tasks` criadas, concluídas, pendentes e vencidas |
| tickets criados / resolvidos / backlog | `created_at` / `resolved_at` no período / estado não final agora |
| tempo de resolução | média e mediana de `resolved_at − created_at` (corrido) |
| SLA cumprido | instâncias paradas sem violação ÷ instâncias paradas, por métrica |
| reaberturas | `ticket_events.kind = reopened` no período |
| FCR | resolvidos no período com `reopen_count = 0` e ≤ 1 contato (chamada ou conversa) ÷ resolvidos |

### 8.8 Retorno de resultados do A3

Decisão: **REST** `POST /sd-ops/api/v1/analysis-results` com token de serviço (`analysis:write`). O sd-ops não consome o stream.

```json
{"kind":"transcription","status":"completed","recording_id":"…","call_id":"…","external_id":"qa.transcriptions:123",
 "completed_at":"2026-10-13T18:10:00Z","score":null,"data":{"language":"pt-BR","segments":84,"confidence":0.91}}
```

`kind` ∈ `transcription`, `summary`, `qa`; `status` ∈ `completed`, `partial`, `failed`; `qa` aceita `score` (0–100) e `data.rubric_version`. É idempotente por (`kind`, `external_id`): repetir → 200 `{"duplicate":true}`. Efeito: `ops.analysis_refs`, atividade `analise` nos tickets da chamada, `audit_events` e, para `kind=qa` com `status` `completed`/`partial`, o repasse do `qa.completed` ao n8n (§8.3; resposta `{"id":…,"duplicate":false,"forwarded":true}`). Não cria nota no Chatwoot (a nota revisável é do A3). O qa-pipeline manda em `data`: `evaluation_id`, `rubric_version`, `prompt_version`, `model`, `alerts`, `console_url`, `recommendation_only`.

### 8.9 Menu Dinâmico / URA

`GET`/`POST /sd-ops/api/v1/ura/tickets/{protocolo}?ani=:telefone` (a 55PBX substitui `:variavel`). Autenticação conforme o painel do Menu Dinâmico (token, bearer ou usuário/senha): header de token (`X-SD-URA-Token`, nome configurável em `integration_accounts.ura_auth.header`), `Bearer` ou Basic. A credencial identifica o tenant. Resposta **200** com objeto plano de strings (lido na URA como `55pbx_<atributo>`):

| Caso | Corpo |
|---|---|
| encontrado e `ani` confere com o telefone do ticket | `{"encontrado":"sim","verificado":"sim","protocolo":"DEV-2026-000123","situacao":"em_atendimento","situacao_fala":"em atendimento","proxima_acao":"aguarde o retorno da equipe","fila":"FILA_SUPORTE_1"}` |
| encontrado, `ani` ausente ou diferente | `{"encontrado":"sim","verificado":"nao","situacao_fala":"localizado; para detalhes fale com um atendente","proxima_acao":"transferir"}` |
| inexistente ou dígito verificador errado | `{"encontrado":"nao","proxima_acao":"repetir"}` |

Nunca devolve nome, e-mail, CPF ou valores. Limite `URA_RATE_LIMIT_PER_MIN` por `ani`/IP (429 além disso). Cada consulta vai para `audit_events` (`ura.lookup`, protocolo mascarado).

### 8.10 Capacidades do CTI: `GET /sd-ops/api/v1/capabilities` (integração final)

Fonte única do que o sd-console oferece no CTI (antes: heurística sobre `/context.dial` e sondagem de `GET /callbacks`). Responde **por usuário** (sessão do agente; token de serviço também é aceito). Capacidade desabilitada vem com `reason` em pt-BR para a interface mostrar; nada é simulado.

```json
{"tenant_id":"b2b","env":"prod","integration_enabled":true,
 "capabilities":{
   "dial":{"enabled":false,"mode":"disabled","reason":"click-to-call desativado (PBX_DIAL_MODE=disabled)"},
   "webphone":{"enabled":true,"mode":"external","url":"https://fone.55pbx.com","reason":null},
   "callbacks":{"enabled":true,"reason":null},
   "recordings":{"enabled":true,"mode":"local","reason":null},
   "ura":{"enabled":false,"mode":"menu_dinamico","reason":"Menu Dinâmico (URA) sem credencial configurada para este tenant"}}}
```

| Capacidade | `enabled` quando | `mode` / extras |
|---|---|---|
| `dial` | `PBX_DIAL_MODE=live` com `client_code`/`api_key`/JWT (ou `mock` com `SDOPS_ENV=dev`) **e** o usuário tem papel agente/supervisor/admin **e** ramal ativo em `ops.agent_phone_mappings` (token de serviço: escopo `dial:write`) | `live`/`mock`/`disabled`; `branch` = ramal do usuário; em `mock`, `reason` = "MODO MOCK (DEV)…" |
| `webphone` | `PBX_WEBPHONE_URL` definido (webphone oficial da 55PBX, aberto em janela própria; o áudio nunca passa pelo ServiceDesk) | `external`; `url` |
| `callbacks` | papel agente/supervisor (token de serviço: `callbacks:write`) | — |
| `recordings` | `RECORDING_URL_SECRET` com ≥ 32 caracteres (token de serviço: também `recordings:read`). A permissão por gravação continua no `GET /recordings/{id}/url` (§8.6) | `local`/`s3` |
| `ura` | o tenant tem conta de integração ativa com `ura_auth` e a credencial referenciada existe no ambiente | `menu_dinamico` |

Sem a rota (sd-ops antigo: 404/405), o sd-console desabilita tudo e explica. O `dial` que ainda vem no `GET /context` é mantido por compatibilidade e **não** é usado pela interface.
