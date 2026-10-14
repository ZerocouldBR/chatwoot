# Mapeamento da API do Chatwoot (fork CE v4.18.0) usada pelo sd-ops, pbx-bridge, sd-console e n8n

Versão 1, de 2026-10-13 (agente A1). **Fonte de verdade: o código do fork** (`/opt/servicedesk-dev/chatwoot`, `config/routes.rb` e controllers), conferido com a referência online (https://developers.chatwoot.com/api-reference). A referência online acompanha versões mais novas que a 4.18.0; quando divergem, vale o código.

**Edição:** Community (CE). A imagem de produção é construída **sem `enterprise/`** (`docs/CI-IMAGEM.md`). Rotas protegidas por `if ChatwootApp.enterprise?` **não existem** na nossa instalação.

## 1. Convenções

| Item | Valor |
|---|---|
| Base | `{CHATWOOT_URL}/api/v1/accounts/{account_id}` (interno: `http://servicedesk_rails:3000`) |
| Autenticação | header `api_access_token: <token>` |
| Usuário de integração | "Integração 55PBX" / "Integração sd-ops": papel **agente**, membro só das inboxes necessárias (pbx-bridge: inbox "Telefone (55PBX)"). Token em segredo (`CHATWOOT_API_TOKEN`), nunca em log |
| Token do n8n | usuário separado ("Integração n8n"), papel agente, credencial n8n do tipo *Header Auth* (`api_access_token`) |
| Paginação | `page` (contatos: 15/página; conversas: 25) |
| Idempotência | não há chave de idempotência na API. Usar: busca prévia por atributo (`pbx_call_id`, `sd_ticket_id`), `source_id` nas mensagens (`55pbx:<call_id>:<parte>`, `sdops:<evento>`), estado local |
| Origem/anti-loop | toda escrita feita por integração leva **`content_attributes.sd_origin`** (mensagens) ou atributo `sd_last_writer` (conversa) e o autor é o usuário de integração; webhooks recebidos cujo autor é usuário de integração são ignorados (ver `WEBHOOK_CONTRACTS.md` §4) |

## 2. Endpoints usados

| # | Uso | Método e caminho | Parâmetros principais | Quem usa | Evidência |
|---|---|---|---|---|---|
| C1 | Buscar contato por telefone/e-mail/identifier | `GET /contacts/search?q=` | `q` (substring, `ILIKE` em name/email/phone_number/identifier) | pbx-bridge, sd-ops, WF01, WF08 | código `contacts_controller#search`; e2e |
| C2 | Filtro exato de contato | `POST /contacts/filter` | `payload: [{attribute_key:"phone_number", filter_operator:"equal_to", values:["+55..."]}]` | sd-ops | doc `contact-filter` |
| C3 | Criar contato | `POST /contacts` | `inbox_id`, `name`, `phone_number` (E.164), `email`, `identifier`, `custom_attributes` | pbx-bridge, sd-ops | e2e |
| C4 | Atualizar contato | `PUT /contacts/{id}` | `custom_attributes`, `additional_attributes` | sd-ops | doc |
| C5 | Conversas do contato (histórico 360°) | `GET /contacts/{id}/conversations` | — | sd-console (CTI) | doc |
| C6 | Vincular contato à inbox | `POST /contacts/{id}/contact_inboxes` | `inbox_id`, `source_id` | sd-ops | rota `contact_inboxes#create` |
| C7 | Mesclar contatos | `POST /actions/contact_merge` | `base_contact_id`, `mergee_contact_id` | **só humano** (nunca automático por nome) | doc `merge-contacts` |
| V1 | Criar conversa (tela de trabalho do ticket) | `POST /conversations` | `source_id`, `inbox_id`, `contact_id`, `status`, `assignee_id`, `team_id`, `additional_attributes` (`mail_subject`, `pbx_call_id`), `custom_attributes` | pbx-bridge, sd-ops | `conversation_builder.rb`; e2e |
| V2 | Detalhe da conversa | `GET /conversations/{display_id}` | — | sd-ops, sd-console, n8n | doc |
| V3 | Filtrar conversas por atributo (ex. `sd_ticket_id`, `pbx_call_id`) | `POST /conversations/filter` | `payload` (attribute_key, filter_operator, values, query_operator) | sd-ops, WF08, WF10 | `conversations_controller#filter` |
| V4 | Mudar status | `POST /conversations/{id}/toggle_status` | `status` ∈ `open`,`resolved`,`pending`,`snoozed`; `snoozed_until` (epoch) | sd-ops (sincronização de status) | doc `toggle-status` |
| V5 | Prioridade | `POST /conversations/{id}/toggle_priority` ou `PATCH /conversations/{id}` | `priority` ∈ `urgent`,`high`,`medium`,`low`, `null` | sd-ops, WF04 | código (`permitted_update_params` só aceita `priority`) |
| V6 | Atributos personalizados | `POST /conversations/{id}/custom_attributes` | `custom_attributes: {...}` **+ `merge: true`**. Sem `merge`, o padrão **substitui o hash inteiro** e apaga os `zd_*` (código `conversation_custom_attributes_concern.rb`) | sd-ops, pbx-bridge (já usa `merge: true`), n8n | código; e2e |
| V7 | Remover atributos | `POST /conversations/{id}/destroy_custom_attributes` | `custom_attributes: ["chave"]` | sd-ops | rota |
| V8 | Atribuir agente/time | `POST /conversations/{id}/assignments` | `assignee_id` **ou** `team_id` (um por chamada) | sd-ops, WF01, WF04 | `assignments_controller#create` |
| V9 | Etiquetas | `POST /conversations/{id}/labels` | `labels: [...]` (**sobrescreve** a lista; ler antes com `GET`) | sd-ops, WF03 | doc `add-labels` |
| V10 | Nota interna / mensagem | `POST /conversations/{id}/messages` | `content`, `message_type` (`outgoing`/`incoming`), `private` (true = nota), `source_id`, `content_attributes` (`in_reply_to`), `attachments[]` (multipart) | pbx-bridge (notas e MP3), sd-ops (resumo IA, mudança de estado), WF05/WF06 | `message_builder.rb` (`source_id` aceito); e2e |
| V11 | Listar mensagens | `GET /conversations/{id}/messages` | `before` | sd-ops (checar `source_id`) | doc |
| V12 | Participantes (seguidores) | `POST/PATCH /conversations/{id}/participants` | `user_ids` | WF04 (supervisor) | rota |
| T1 | Times, agentes, inboxes (cache de mapas) | `GET /teams`, `GET /agents`, `GET /inboxes` | — | sd-ops, n8n | doc |
| A1 | Definições de atributos (provisionamento) | `POST /custom_attribute_definitions` | `attribute_key`, `attribute_model` (`conversation_attribute`/`contact_attribute`), `attribute_display_type` | provisionamento (rails runner) | código |
| A2 | Dashboard App (CTI) | `POST /dashboard_apps` | `title`, `content: [{type:"frame", url}]` | provisionamento | rota `dashboard_apps` |
| A3 | Webhook de conta (eventos para o sd-ops/n8n) | `POST /webhooks` | `url`, `subscriptions[]` (ver §3) | provisionamento | `webhook.rb` |
| R1 | Relatórios de conversa (FRT, resolução) | `GET /api/v2/accounts/{id}/reports`, `/reports/summary`, `/reports/conversations` | `metric`, `type`, `since`, `until` | WF12, sd-console (admin) | doc |

## 3. Eventos de webhook disponíveis (CE 4.18.0)

`app/models/webhook.rb` → `ALLOWED_WEBHOOK_EVENTS`:
`conversation_status_changed`, `conversation_updated`, `conversation_created`, `contact_created`, `contact_updated`, `message_created`, `message_updated`, `webwidget_triggered`, `inbox_created`, `inbox_updated`, `conversation_typing_on`, `conversation_typing_off`.

Assinatura (quando o webhook tem `secret`): `X-Chatwoot-Signature: sha256=<hex HMAC-SHA256(secret, "<X-Chatwoot-Timestamp>.<corpo>")>`, `X-Chatwoot-Timestamp` (epoch s), `X-Chatwoot-Delivery` (UUID) — `lib/webhooks/trigger.rb`. Validar: assinatura em tempo constante + |agora − ts| ≤ 300 s + deduplicação por `X-Chatwoot-Delivery`.

## 4. O que NÃO existe na CE (e o substituto)

| Recurso | Situação no fork CE | Substituto |
|---|---|---|
| SLA (`sla_policies`, `applied_slas`) | enterprise — **proibido** | `ops.sla_*` no sd-ops + WF10 (alertas) |
| `GET /conversations/{id}/reporting_events` | rota só com `ChatwootApp.enterprise?` (a doc online lista como disponível) | `ops.ticket_events` + relatórios v2 |
| Papéis personalizados (custom roles) | enterprise | M13 (fork, Pundit) — `docs/PERMISSOES.md` |
| Audit logs | enterprise | `ops.audit_events` (domínio de ticket) + M13/S8 |
| Voz (Twilio/WhatsApp Calling) | premium | 55PBX: webphone/extensão + Dashboard App CTI |
| Captain / Copilot | enterprise | sd-ops (QA/IA, A3) e n8n (agentes existentes) |
| Capacidade por agente | enterprise | regra de atribuição no sd-ops (fase posterior) |
| Status personalizado | não existe (4 status nativos) | `zd_status` (rótulo) + status canônico (`TICKET_DOMAIN.md` §4) |

## 5. Atributos personalizados usados pela integração

| Chave | Modelo | Escrito por | Conteúdo |
|---|---|---|---|
| `zd_status` | conversa | importador, sd-ops | rótulo do status de negócio (Novo, Aberto, Em andamento, Pendente, Resolvido…) |
| `zd_*` (63 campos) | conversa | importador, painel, macros | campos do Zendesk (`docs/CAMPOS.md`) |
| `pbx_call_id`, `pbx_tipo`, `pbx_ramal`, `pbx_fila`, `pbx_numero`, `pbx_duracao_total`, `pbx_tempo_falado`, `pbx_tempo_espera`, `pbx_desconexao`, `pbx_ura`, `pbx_humor`, `pbx_agente` | conversa | pbx-bridge / sd-ops | dados da última ligação ligada à conversa |
| `sd_ticket_id` (proposto) | conversa | sd-ops | UUID do ticket de negócio em `ops.support_tickets` |
| `sd_protocolo` (proposto) | conversa | sd-ops | protocolo legível (`TICKET_DOMAIN.md` §3) |
| `sd_ticket_status` (implementado pelo A2; a proposta era `sd_estado`) | conversa | sd-ops | estado de negócio canônico (`novo`, `triagem`, `em_atendimento`, `aguardando_cliente`, `aguardando_terceiro`, `resolvido`, `encerrado`, `cancelado`); também `sd_protocolo_numerico` e `zd_status_sistema` (`TICKET_DOMAIN.md` §8) |
| `sd_sla_due_at`, `sd_sla_status` (proposto) | conversa | sd-ops (WF10) | prazo e situação do SLA (para coluna/visão) |
| `sd_last_writer` (proposto) | conversa | sd-ops, n8n | `sd-ops`/`n8n`/`pbx-bridge` — anti-loop |

Os atributos "propostos" são criados por provisionamento idempotente (rails runner, mesmo padrão do `provision_55pbx.rb`), dormentes até a ativação.
