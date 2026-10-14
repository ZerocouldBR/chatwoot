# Estado atual do fork Chatwoot para um sistema de tickets tipo Zendesk

## Escopo e método

- Repositório: `/home/victor/Projects/Projetos/b2b-helpdesk-platform`, branch `develop`, HEAD `8732dc3ac`.
- Análise estática e somente leitura. Não subi o Rails, não rodei specs e não consultei o banco.
- Não acessei o VPS `servicedesk-dev` (fora do escopo local).
- Não usei fontes web. As citações são caminhos relativos à raiz do repo, com linha quando relevante (`arquivo:linha`). Para os conceitos do Zendesk usei conhecimento geral do modelo de dados, sem consultar a documentação oficial nesta pesquisa.
- Status usado no mapeamento: **Existe**, **Parcial**, **Ausente**.

---

## 1. Estado do repositório, enterprise/ e branches

### Takeaway
O fork está no meio da remoção do módulo Enterprise. `enterprise/` e `spec/enterprise/` saíram da árvore de trabalho e do índice. Com isso `ChatwootApp.enterprise?` (`lib/chatwoot_app.rb:14-18`, `root.join('enterprise').exist?`) retorna falso. Os recursos pagos de ticketing (SLA, papéis customizados, auditoria, capacidade de agente) perderam o backend. Parte do frontend, algumas tabelas do schema e algumas rotas continuam presentes. Não há trabalho de ticket em nenhuma branch local.

### Cited Findings
- `enterprise/` não existe no disco. No HEAD havia 577 arquivos rastreados sob `enterprise/` (`git ls-tree -r --name-only HEAD enterprise`).
- `git status`: 166 modificados (M), 920 deletados (D), 4 não rastreados (??). Destes, 885 deleções estão em `enterprise/` ou `spec/enterprise/`. As deleções de enterprise estão staged (`D ` no índice). As demais alterações estão unstaged.
- Outras deleções: `app/javascript/dashboard/api/changelog.js`, `yearInReview.js`, componentes changelog e year-in-review, 8 arquivos em `public/`, `app/views/super_admin/settings/_upgrade_button_{community,enterprise}.html.erb`.
- Marca: `config/installation_config.yml` troca `INSTALLATION_NAME` e `BRAND_NAME` para `Helpdesk` e zera URLs de marca. Helper novo, não rastreado: `app/javascript/shared/helpers/brandName.js` e `config/initializers/brand_name_i18n.rb`.
- Branches: apenas `develop` local, `origin/develop` e `origin/HEAD`. Não existem `servicedesk/*`, `feat/*` nem `fix/*`. Sem stash, sem worktrees, sem tags. O reflog tem só o clone inicial. `git log --all` filtrado por `servicedesk|ticket|sla|zendesk` não retornou commits.
- A memória do projeto cita `docs/DESIGN-MIGRACAO.md` (módulos M1 a M14). Esse arquivo não existe neste repo. `docs/` contém `captain_v1_sunset.md`, `rails_upgrade_assessment.md` e `rails_upgrades/`.
- `origin` aponta para `https://github.com/ZerocouldBR/chatwoot.git`. O repo é um clone de Chatwoot upstream.
- `research_notes/Sistema de tickets do Zendesk/` existia vazio antes desta pesquisa.
- `enterprise/LICENSE` (presente no HEAD) é a "Chatwoot Enterprise license". O uso em produção depende de contrato e de licença válida. Copiar código de `enterprise/` para o OSS é risco de licenciamento. Isto não é parecer jurídico.
- `db/schema.rb` está na versão `2026_10_08_090132` e foi commitado no HEAD (não aparece como modificado).

### Rotas sem controller e referências órfãs (crítico)
- `config/routes.rb` declara rotas cujos controllers não existem na árvore atual. Nenhuma delas é protegida por `ChatwootApp.enterprise?`:
  - `resource :saml_settings` (linha 138)
  - `resource :audit_logs` (linha 150)
  - `resources :sla_policies` (linha 166)
  - `resources :custom_roles` (linha 167)
  - `resources :agent_capacity_policies`, com `users` e `inbox_limits` aninhados (linha 168)
  - `get 'analytics/metrics'` dentro de campanhas (linha 176)
  - `resources :applied_slas` (linha 302)
- Controllers ausentes: `app/controllers/api/v1/accounts/{sla_policies,custom_roles,agent_capacity_policies,audit_logs,applied_slas,saml_settings}_controller.rb` e `campaigns/analytics_controller.rb`. Como as rotas são lazy, o boot não quebra. Os endpoints respondem com erro.
- Rotas guardadas por `if ChatwootApp.enterprise?`, portanto desligadas: `campaign_history`, `reporting_events`, `calls`, `enrichment` de empresas, `csat_survey_responses#update`, `contacts#call`.
- Referências órfãs em código OSS:
  - `app/models/concerns/sla_activity_message_handler.rb:19` chama `SlaPolicy.find_by`.
  - `lib/tasks/apply_sla.rake` usa `SlaPolicy` e `AppliedSla` (`sla:apply_to_conversations`).
  - `config/initializers/audited.rb:4` define `config.audit_class = 'Enterprise::AuditLog'`. Nenhum model OSS usa `audited`, então isto fica dormente.
  - `lib/seeders/reports/*` referencia `ConversationOutcome`.
- Clientes de API no frontend apontam para recursos inexistentes:
  - `app/javascript/dashboard/api/sla.js` (`sla_policies`)
  - `api/customRole.js` (`custom_roles`)
  - `api/auditLogs.js` (`audit_logs`)
  - `api/agentCapacityPolicies.js` (`agent_capacity_policies`)
- Telas que dependem desses clientes: `routes/dashboard/settings/{sla,customRoles,auditlogs}/`, `routes/dashboard/settings/assignmentPolicy/pages/AgentCapacity*.vue`, `reports/SLAReports.vue`.
- Gate de enterprise que ainda existe no OSS: `app/models/assignment_policy.rb:38` define `enum assignment_order: { round_robin: 0 } unless ChatwootApp.enterprise?`. Hoje a única estratégia OSS é round robin.

### Feature flags (`config/features.yml`)
- `assignment_v2`: `enabled: true` (linhas 202-204). É o gate do motor V2 de atribuição (`app/models/inbox.rb:206-207`).
- `auto_resolve_conversations`, `macros`, `automations`, `canned_responses`, `custom_attributes`, `labels`, `reports`, `help_center`, `campaigns`, `agent_bots`: `enabled: true`.
- `sla` (linhas 130-133), `audit_logs` (111-114), `custom_roles` (147-150): `enabled: false` e `premium: true`.
- `inbox_view`, `report_rollup`, `message_reply_to`, `conversation_unread_counts`: `enabled: false`.
- Itens premium listados no HEAD em `enterprise/config/premium_features.yml`: `disable_branding`, `audit_logs`, `sla`, `custom_roles`, `captain_integration`, `captain_document_auto_sync`, `csat_review_notes`, `conversation_required_attributes`, `conversation_monitors`, `campaign_analytics`.

### Inferences
- A árvore atual está quebrada para os fluxos de SLA, papéis customizados, auditoria e capacidade. Antes de reconstruir, é preciso decidir se as rotas e telas mortas serão removidas ou reimplementadas.
- Reativar o módulo enterprise contraria a regra da memória do projeto (`servicedesk-dev-vps.md`): nada em `enterprise/` pode ser usado. Por isso a reconstrução precisa ser feita em OSS, sem copiar código do HEAD.

### Gaps
- Não verifiquei em runtime quais rotas retornam erro. Essa conclusão é estática.

---

## 2. Conversa (o equivalente ao ticket)

### Takeaway
`Conversation` cumpre o papel de ticket, mas não tem assunto, tipo, vencimento, formulário, nem separação entre solicitante e submissor. Tem quatro status, prioridade nullable, um responsável, um time, um contato como solicitante e campos customizados em jsonb. O assunto de e-mail fica em `additional_attributes`.

### Cited Findings
- Tabela `conversations` (`db/schema.rb:982-1031`):
  - `status` integer, default 0, not null
  - `priority` integer, sem default, nullable
  - `display_id` not null, único por conta
  - `uuid` único
  - `assignee_id`, `team_id`, `contact_id`, `contact_inbox_id`, `inbox_id`, `campaign_id`
  - `assignee_agent_bot_id` mais `ai_assignee_type`, que formam um assignee polimórfico (bot ou Captain)
  - `snoozed_until`, `waiting_since`, `first_reply_created_at`, `status_changed_at`, `last_activity_at`
  - `contact_last_seen_at`, `agent_last_seen_at`, `assignee_last_seen_at`
  - `additional_attributes` jsonb, `custom_attributes` jsonb, `cached_label_list` text
  - `sla_policy_id` bigint, coluna órfã
  - `identifier`
- Enums (`app/models/conversation.rb:86-87`):
  - `status`: `open` 0, `resolved` 1, `pending` 2, `snoozed` 3
  - `priority`: `low` 0, `medium` 1, `high` 2, `urgent` 3
- Associações (`conversation.rb`): `belongs_to` account, inbox, assignee (User), ai_assignee (polimórfico), contact, contact_inbox, team (opcional), campaign. `has_many` messages, mentions, conversation_participants, notifications, reporting_events, attachments (through messages), automation_rule_pending_executions. `has_one` csat_survey_response.
- Snooze: status `snoozed` mais `snoozed_until`. `ensure_snooze_until_reset` zera o campo quando o status deixa de ser snoozed (`conversation.rb:290-292`). Snooze em massa em `app/jobs/bulk_actions_job.rb:50-51`. A criação aceita `snoozed_until` em `app/builders/conversation_builder.rb:35`.
- Espera do cliente (`waiting_since`):
  - definido na criação (`ensure_waiting_since`, `conversation.rb:298-300`)
  - definido por mensagem de entrada (`app/models/message.rb:346-348`)
  - limpo por resposta pública de saída (`message.rb:351-356`)
  - limpo na resolução (`conversation.rb:281-286`)
  - escopos `unattended`, `resolvable_not_waiting`, `resolvable_all` (`conversation.rb:95-107`)
- Auto-resolução: `delegate :auto_resolve_after, to: :account`. Os escopos usam `last_activity_at`.
- `first_reply_created_at` é gravado na primeira resposta de saída (`message.rb:392`).
- Prioridade: `toggle_priority` (`conversation.rb:179-182`). Na atualização, `permitted_update_params` aceita apenas `priority` e valida o valor (`app/controllers/api/v1/accounts/conversations_controller.rb:142-147`).
- Assunto: não existe coluna. Em e-mail, o assunto fica em `additional_attributes['mail_subject']` (gravado em `app/mailboxes/imap/imap_mailbox.rb:99` e usado em `app/mailers/conversation_reply_mailer.rb:122-124`, com prefixo `[#display_id]`).
- Atividades: `app/models/concerns/activity_message_handler.rb:12-18` (`create_activity`) gera mensagens do tipo `activity` para mudança de status, prioridade, labels e SLA.
- Rotas de conversa (`config/routes.rb`, a partir da linha 184):
  - Coleção: `meta`, `search`, `unread_counts`, `filter`
  - Membro: `mute`, `unmute`, `transcript`, `toggle_status`, `toggle_priority`, `toggle_typing_status`, `update_last_seen`, `unread`, `custom_attributes`, `destroy_custom_attributes`, `attachments`, `inbox_assistant`
  - Aninhadas: `messages`, `labels`, `assignments`, `participants`, `draft_messages`, `direct_uploads`, `suggestions`, `contact_info_request`
- Participantes: tabela `conversation_participants` (`account_id`, `user_id`, `conversation_id`), com `resource :participants` e `app/controllers/api/v1/accounts/conversations/participants_controller.rb`. Funciona como colaboradores agentes, não como CCs de cliente.
- Merge de conversas: não encontrado. O único merge é o de contatos (`app/actions/contact_merge_action.rb`, método `merge_conversations` na linha 34). Rota `contact_merge` em `config/routes.rb:74`.

### Inferences
- Para aproximar um ticket Zendesk, faltam colunas `subject` (hoje só existe em e-mail), `ticket_type`, `due_at` e `form_id`.
- "Novo" (new) pode ser derivado como `open` sem `assignee_id`. Não há status próprio. Não há "on hold" separado: `pending` e `snoozed` cobrem parte do caso.

### Gaps
- Não há contador de reaberturas (reopen count).

---

## 3. Mensagens

### Takeaway
As mensagens cobrem comentário público, nota privada, atividade e template. Há anexos, rascunhos, menções e transcrição por e-mail. CC e BCC existem no nível da mensagem de e-mail, mas não como lista persistente do ticket.

### Cited Findings
- Tabela `messages` (`db/schema.rb:1362-1395`): `content` text, `message_type` int not null, `private` boolean (default false), `content_type` int (default 0), `content_attributes` json, `sender_type` e `sender_id` (polimórfico), `source_id` text (Message-ID do e-mail), `external_source_ids` jsonb, `additional_attributes` jsonb, `status` int, `sentiment` jsonb, `processed_message_content` text.
- Enum `message_type` (`app/models/message.rb:88`): `incoming` 0, `outgoing` 1, `activity` 2, `template` 3.
- Enum `content_type` (`message.rb:89-102`): `text`, `input_text`, `input_textarea`, `input_email`, `input_select`, `cards`, `form`, `article`, `incoming_email`, `input_csat`, `integrations`, `sticker`, `voice_call`.
- Enum `status` (`message.rb:104`): `sent`, `delivered`, `read`, `failed`.
- Accessors de `content_attributes` (`message.rb:112-114`): `email`, `in_reply_to`, `in_reply_to_external_id`, `submitted_email`, `items`, `submitted_values`, `deleted`, `translations`, `is_unsupported`, `data`.
- CC e BCC de saída: `app/builders/messages/message_builder.rb:100-108` grava `content_attributes[:cc_emails]` e `[:bcc_emails]`. O envio usa `app/mailers/conversation_reply_mailer_helper.rb:16-17`.
- CC e BCC de entrada: `app/mailboxes/mailbox_sanitizer.rb:22-23` grava `cc_email` e `bcc_email`.
- Nota privada: `messages.private = true`. Nota de contato é outra coisa, na tabela `notes` (`contact_id`, `user_id`, `content`), e não de ticket.
- Anexos: tabela `attachments`, com enum `file_type` em `app/models/attachment.rb:47` (`image`, `audio`, `video`, `file`, `location`, `fallback`, `share`, `story_mention`, e outros). Upload direto em `direct_uploads`.
- Rascunhos: rota `draft_messages` dentro de conversas.
- Transcrição: `POST conversations/:id/transcript` e `ActionService#send_email_transcript` (`app/services/action_service.rb`).
- Menções: tabela `mentions`. Notificações: tabela `notifications` com `notification_type`, definido em `NOTIFICATION_TYPES` (`app/models/notification.rb:38`).
- Conteúdo de e-mail truncado a 150.000 caracteres em `mailbox_sanitizer.rb`.
- Detecção de auto-resposta: `message.rb:227` (`content_attributes.dig(:email, :auto_reply)`).

### Inferences
- Um ticket com CCs persistentes exige uma tabela própria (por exemplo `conversation_cc_addresses`), ou ler os CCs de `messages.content_attributes` do primeiro e-mail.

### Gaps
- Não verifiquei o frontend do editor de resposta (campos CC/BCC na UI).

---

## 4. Contatos, empresas e atributos customizados

### Takeaway
Existe um modelo de empresa (`companies`) na OSS, ligado ao contato por `contacts.company_id`. A conversa chega à empresa pelo contato, não por uma FK própria. Os atributos customizados têm oito tipos e três escopos (conversa, contato e empresa). Não há obrigatoriedade condicional nem campos por grupo.

### Cited Findings
- Tabela `contacts` (`db/schema.rb:795-825`): `name`, `email` (índice único por conta em `lower(email)`), `phone_number`, `identifier` (único por conta), `additional_attributes` jsonb, `custom_attributes` jsonb, `contact_type` int (default 0), `blocked` boolean, `company_id` bigint, `last_activity_at`, `middle_name`, `last_name`, `location`, `country_code`.
- `contact_type` enum (`app/models/contact.rb:72`): `visitor` 0, `lead` 1, `customer` 2.
- `contact.rb` tem `has_many` de conversations, contact_inboxes, csat_survey_responses, messages e notes.
- Tabela `companies` (`db/schema.rb:764-778`): `name` not null, `domain` (único por conta quando preenchido), `description`, `contacts_count`, `custom_attributes`, `additional_attributes`, `last_activity_at`.
- `app/models/company.rb`: `has_many :contacts, dependent: :nullify`. Busca o favicon após a criação. Controller OSS: `app/controllers/api/v1/accounts/companies_controller.rb`.
- Enriquecimento de empresa (`companies/enrichments`) estava no enterprise e não existe mais.
- Tabela `custom_attribute_definitions` (`db/schema.rb:1076-1092`, model `app/models/custom_attribute_definition.rb`):
  - `attribute_model` enum: `conversation_attribute` 0, `contact_attribute` 1, `company_attribute` 2 (linha 48)
  - `attribute_display_type` enum: `text` 0, `number` 1, `currency` 2, `percent` 3, `link` 4, `date` 5, `list` 6, `checkbox` 7 (linha 49)
  - chave única por (`attribute_key`, `attribute_model`, `account_id`)
- Os filtros usam esses tipos (`app/services/filter_service.rb`, `ATTRIBUTE_TYPES`).
- Criação e identificação de contato: `app/actions/contact_identify_action.rb` e `ContactInboxWithContactBuilder`.
- Merge de contatos (`app/actions/contact_merge_action.rb`) mescla conversas, mensagens e demais dados do contato.
- Recurso `custom_attribute_definitions` com CRUD completo em `config/routes.rb`.

### Inferences
- Organização por ticket: o equivalente é `conversation.contact.company`. Para relatórios ou filtros rápidos por empresa, seria preciso denormalizar `company_id` em `conversations`.
- Obrigatoriedade de campos por tipo de ticket só é possível hoje com validação customizada. A feature `conversation_required_attributes` era premium e saiu com o enterprise.

### Gaps
- Não encontrei lógica de campos por grupo (equivalente a field visibility por grupo do Zendesk).

---

## 5. Times, membros, atribuição e disponibilidade

### Takeaway
Time (`team`) é o equivalente de grupo. Há atribuição round robin com política por inbox e motor V2 ativo por feature flag. Não há capacidade por agente, nem skills, nem feriados. A disponibilidade do agente é online, offline ou busy.

### Cited Findings
- Tabela `teams` (`db/schema.rb:1619`): `name` (único por conta), `description`, `allow_auto_assign` (default true), `icon`, `icon_color`. Model `app/models/team.rb`.
- `team_members` (`user_id`, `team_id`, único). `inbox_members` (`user_id`, `inbox_id`, único).
- Cada conversa tem no máximo um time (`conversations.team_id`). Ação de automação `assign_team`.
- Tabela `inboxes` (`db/schema.rb:1256-1283`): `channel` polimórfico, `enable_auto_assignment` (default true), `auto_assignment_config` jsonb, `working_hours_enabled`, `timezone` (default UTC), `out_of_office_message`, `greeting_enabled`, `greeting_message`, `csat_survey_enabled`, `csat_config` jsonb, `allow_messages_after_resolved`, `lock_to_single_conversation`, `portal_id`, `sender_name_type`, `business_name`, `email_address`.
- Tabela `assignment_policies` (`db/schema.rb:231`):
  - `assignment_order`: OSS só tem `round_robin` (`app/models/assignment_policy.rb:38`)
  - `conversation_priority` enum: `earliest_created` 0, `longest_waiting` 1
  - `fair_distribution_limit` (default 100), `fair_distribution_window` (default 3600 s), `exclude_older_than_hours`
- `inbox_assignment_policies`: uma política por inbox (validação de unicidade em `inbox_id`).
- Motor de atribuição (OSS):
  - `app/services/auto_assignment/{assignment_service.rb, agent_assignment_service.rb, inbox_round_robin_service.rb, round_robin_selector.rb, rate_limiter.rb}`
  - jobs `app/jobs/auto_assignment/{assignment_job.rb, periodic_assignment_job.rb}`
  - cron a cada 30 minutos (`config/schedule.yml:63-67`)
  - gate V2: `account.feature_enabled?('assignment_v2')` (`inbox.rb:206-207`)
  - caminho legado: `app/models/concerns/auto_assignment_handler.rb`
- Elegibilidade: somente agentes com status `online`, via `OnlineStatusTracker` em Redis (`agent_assignment_service.rb:61-63`). Se a conversa tem time, só entram membros do time com `allow_auto_assign` (`auto_assignment_handler.rb`, `team_member_ids_with_capacity`).
- Capacidade: não existe na OSS. `Inbox#member_ids_with_assignment_capacity` devolve todos os membros (`inbox.rb`, perto da linha 203). As tabelas `agent_capacity_policies` (`db/schema.rb:139`) e `inbox_capacity_limits` (`db/schema.rb:1236`) continuam no schema sem model.
- Disponibilidade: `account_users.availability` enum `online` 0, `offline` 1, `busy` 2 (`app/models/account_user.rb:35`). A coluna `users.availability` está marcada como legada (`app/models/user.rb:71-72`).
- Rotas e controllers OSS: `teams_controller.rb`, `team_members_controller.rb`, `inbox_members_controller.rb`, `assignable_agents_controller.rb`, `assignment_policies_controller.rb`.

### Inferences
- Para reconstruir balanceamento por carga é preciso: (1) uma tabela de capacidade por agente e por inbox, (2) alterar `member_ids_with_assignment_capacity` para filtrar por capacidade, (3) remover o gate `unless ChatwootApp.enterprise?` de `assignment_policy.rb:38` e adicionar novas estratégias.
- Hoje a atribuição só considera `online`. Estados `busy` e `offline` não entram no round robin.

### Gaps
- Não há skills nem roteamento por habilidade. Não há feriados nem exceções de agenda (não encontrei nenhuma ocorrência de "holiday" em `app/`, `lib/` e `config/`).

---

## 6. Automação, macros, respostas prontas, webhooks, bots e views

### Takeaway
Automação por evento com condições e ações está completa na OSS, incluindo execução com atraso. Macros, respostas prontas e webhooks estão presentes. Views são `custom_filters`, sem compartilhamento nem colunas salvas.

### Cited Findings
- Tabela `automation_rules` (`db/schema.rb:309`): `name`, `description`, `event_name` string, `conditions` jsonb, `actions` jsonb, `active`, `execution_delay` int (em minutos, faixa 10 a 43.200, ou seja de 10 minutos a 30 dias, conforme `EXECUTION_DELAY_RANGE` em `automation_rule.rb`), `monitor_id` (enterprise), `files`.
- Pendências de execução atrasada: tabela `automation_rule_pending_executions`.
- Listener: `app/listeners/automation_rule_listener.rb` (eventos `conversation_created`, `conversation_updated`, `conversation_opened`, `conversation_resolved`, `message_created`).
- Eventos no frontend (`app/javascript/dashboard/routes/dashboard/settings/automation/constants.js`): `message_created`, `conversation_created`, `conversation_updated`, `conversation_opened`, `conversation_resolved`.
- Ações aceitas pelo backend (`automation_rule.rb:60-65`): `send_message`, `add_label`, `remove_label`, `send_email_to_team`, `assign_team`, `assign_agent`, `remove_assigned_agent`, `remove_assigned_team`, `send_webhook_event`, `mute_conversation`, `send_attachment`, `change_status`, `resolve_conversation`, `open_conversation`, `pending_conversation`, `snooze_conversation`, `change_priority`, `send_email_transcript`, `add_private_note`.
- Condições: JSON no formato de filtro, validado por `app/services/automation_rules/condition_validation_service.rb` e avaliado por `conditions_filter_service.rb`. Há um ramo de condições por IA (`captain_conditions`) protegido pela feature `captain_integration` (`automation_rule.rb`, perto das linhas 92-127).
- Execução de ações: `app/services/automation_rules/action_service.rb` e `app/services/action_service.rb`.
- Macros: tabela `macros` (`db/schema.rb:1337`): `name`, `visibility` enum (`personal` 0, `global` 1), `actions` jsonb, `created_by_id`, `updated_by_id`, `files`. Validação das ações em `app/models/macro.rb:68-71`. Execução em `app/services/macros/execution_service.rb` e `app/jobs/macros_execution_job.rb`. Rota `POST macros/:id/execute`.
- Respostas prontas: tabela `canned_responses` (`db/schema.rb:407`) com `short_code` e `content`.
- Webhooks: tabela `webhooks` (`db/schema.rb:1693`), com `subscriptions` jsonb e `webhook_type` enum (`account_type` 0, `inbox_type` 1). Eventos permitidos (`app/models/webhook.rb:32-34`): `conversation_status_changed`, `conversation_updated`, `conversation_created`, `contact_created`, `contact_updated`, `message_created`, `message_updated`, `webwidget_triggered`, `inbox_created`, `inbox_updated`, `conversation_typing_on`, `conversation_typing_off`.
- Eventos internos (`lib/events/types.rb`): `conversation.created`, `conversation.resolved`, `conversation.read`, `conversation.bot_handoff`, `first.reply.created`, `reply.created`.
- Bots de agente: tabela `agent_bots` (`db/schema.rb:126`) com `bot_type`, `bot_config` jsonb, `outgoing_url`, `secret`. Vínculo com inbox em `agent_bot_inboxes`. Listener em `app/listeners/agent_bot_listener.rb`.
- Views (filtros salvos, chamados de "folders" na UI): tabela `custom_filters` (`db/schema.rb:1093`) com `name`, `filter_type` enum (`conversation` 0, `contact` 1, `report` 2), `query` jsonb, `user_id` (dono), `account_id`. Não há coluna de compartilhamento, de colunas exibidas nem de ordenação. Filtro de conversa: `POST conversations/filter`, via `app/services/filter_service.rb` (`STRING_VALUE_ATTRIBUTES` = `status`, `priority`).
- Busca: `app/services/search_service.rb`, com rotas `search` para conversas, mensagens, contatos e artigos.
- Labels: tabela `labels` (`title`, `description`, `color` default `#1f93ff`, `show_on_sidebar`), com taggings e `cached_label_list` em conversas.
- Ações em massa: `app/controllers/api/v1/accounts/bulk_actions_controller.rb` e `app/jobs/bulk_actions_job.rb`.
- Campanhas (`campaigns`, `db/schema.rb:380`): `campaign_type` `ongoing` 0 e `one_off` 1. São mensagens de saída, não tickets.
- Importação: `app/services/data_imports/freshdesk/normalizer.rb` mapeia tickets do Freshdesk para conversas (`subject`, `status`, `priority`, `requester_id`, `responder_id`, `tags`, `custom_fields`). Também existe `app/services/data_imports/intercom/`. Não há importador do Zendesk. A única ocorrência de "zendesk" no repo fora do i18n está em `spec/services/data_imports/source_spec.rb`.

### Inferences
- Para um equivalente de "trigger de tempo" do Zendesk, `execution_delay` já cobre o caso de regras adiadas. Para "automações de tempo" sem evento (ex.: fechar tickets pendentes há 7 dias), é preciso um job periódico com condições.
- Views compartilhadas exigem colunas de visibilidade em `custom_filters` e uma policy para leitura por outros agentes.

### Gaps
- Não verifiquei se o frontend de automação expõe todas as 19 ações.

---

## 7. SLA, CSAT e horário comercial

### Takeaway
O SLA foi removido da árvore de trabalho. Sobraram tabelas no schema, uma coluna em `conversations`, mensagens de atividade, templates de e-mail, uma task de rake e toda a UI. O motor de avaliação e os models ficaram só no HEAD do enterprise. CSAT e horário comercial estão presentes e funcionam sem enterprise. Feriados não existem.

### Cited Findings
- SLA, restos no schema commitado:
  - `sla_policies` (`db/schema.rb:1570-1581`): `name`, `description`, `first_response_time_threshold` float, `next_response_time_threshold` float, `resolution_time_threshold` float, `only_during_business_hours` boolean (default false), `account_id`.
  - `applied_slas` (`db/schema.rb:179-192`): `sla_policy_id`, `conversation_id`, `account_id`, `sla_status` int (default 0), `completed_at`. Índice único por (`account_id`, `sla_policy_id`, `conversation_id`).
  - `sla_events` (`db/schema.rb:1553-1569`): `applied_sla_id`, `conversation_id`, `sla_policy_id`, `inbox_id`, `event_type` int, `meta` jsonb.
  - `conversations.sla_policy_id`.
- SLA, restos no código OSS:
  - `app/models/concerns/sla_activity_message_handler.rb` (mensagem "SLA adicionado, removido ou atualizado", incluída por `activity_message_handler.rb:7`).
  - `app/views/api/v1/conversations/partials/_conversation.json.jbuilder:67-68` (expõe `sla_policy_id` quando a feature `sla` está ligada).
  - `lib/tasks/apply_sla.rake`.
  - Templates `app/views/mailers/agent_notifications/conversation_notifications_mailer/sla_missed_{first_response,next_response,resolution}.liquid`.
  - Frontend: `api/sla.js`, `api/slaReports.js`, `composables/useSlaStatus.js`, `components-next/Conversation/Sla/SLACardLabel.vue`, `routes/dashboard/settings/sla/`, `routes/dashboard/settings/reports/SLAReports.vue`, `store/modules/SLAReports.js`.
- SLA, removido (HEAD, enterprise):
  - models `enterprise/app/models/{sla_policy,applied_sla,sla_event}.rb`
  - services `enterprise/app/services/sla/{evaluate_applied_sla_service,business_hours_service,backfill_applied_sla_completed_at_service}.rb`
  - controllers `enterprise/app/controllers/api/v1/accounts/{sla_policies,applied_slas}_controller.rb`
  - `enterprise/app/drops/sla_policy_drop.rb`
  - O `Sla::BusinessHoursService` do HEAD calculava o prazo com `inbox.working_hours_enabled`, pulando horários fechados.
- CSAT (OSS):
  - tabela `csat_survey_responses` (`db/schema.rb:1055-1075`): `rating` int not null, `feedback_message`, `conversation_id`, `message_id`, `contact_id`, `assigned_agent_id`, `csat_review_notes`, `review_notes_updated_at`, `review_notes_updated_by_id`.
  - validação `rating` em `[1, 2, 3, 4, 5]` (`app/models/csat_survey_response.rb:36`).
  - disparo: `app/listeners/csat_survey_listener.rb` (`conversation_status_changed`, quando o status vira `resolved`).
  - configuração por inbox: `inboxes.csat_survey_enabled` e `inboxes.csat_config` jsonb.
  - templates: `app/services/csat_template_*.rb`.
  - endpoints: `app/controllers/api/v1/accounts/csat_survey_responses_controller.rb` (`index`, `metrics`, `download`) e `app/controllers/public/api/v1/csat_survey_controller.rb` (`show`, `update`).
- Horário comercial (OSS):
  - tabela `working_hours` (`db/schema.rb:1706-1717`): `inbox_id`, `account_id`, `day_of_week`, `closed_all_day`, `open_all_day`, `open_hour`, `open_minutes`, `close_hour`, `close_minutes`.
  - `app/models/working_hour.rb` com `open_at?`, `open_now?`, `closed_now?`.
  - Mensagem fora do expediente: `app/models/concerns/out_of_offisable.rb` (`out_of_office?`, `working_now?`, `weekly_schedule`, `update_working_hours`).
  - Escopo só por inbox. Não existe horário por time nem por conta.
  - Tempo em horário comercial para relatórios: `app/helpers/reporting_event_helper.rb#business_hours(inbox, from, to)`, gravado em `reporting_events.value_in_business_hours` por `app/listeners/reporting_event_listener.rb`. Relatórios v2 aceitam o parâmetro `business_hours`.

### Inferences
- Reconstruir SLA em OSS é viável a partir das tabelas existentes. Faltam: o motor de avaliação (equivalente ao `evaluate_applied_sla_service`), os models, os controllers e a reconexão das rotas. A UI já existe.
- Para o SLA respeitar horário comercial de forma equivalente ao Zendesk, é preciso levar o horário para o nível de time ou de SLA, e não só de inbox. Também falta feriado.

### Gaps
- Não há feriados nem exceções de agenda.
- Não verifiquei se o cálculo de `business_hours` do helper cobre virada de dia e fuso horário com precisão.

---

## 8. Canal de e-mail

### Takeaway
O threading de e-mail é robusto: quatro estratégias em ordem, com fallback para criar conversa nova. Cada endereço de suporte é uma inbox própria. Não existe caixa compartilhada além disso.

### Cited Findings
- Tabela `channel_email` (`db/schema.rb:598-626`): `email` (not null), `forward_to_email` (not null), configurações IMAP (`imap_enabled`, `imap_address`, `imap_port`, `imap_login`, `imap_password`, `imap_enable_ssl`, `imap_authentication`), configurações SMTP (`smtp_enabled`, `smtp_address`, `smtp_port`, `smtp_login`, `smtp_password`, `smtp_domain`, `smtp_enable_starttls_auto`, `smtp_authentication`, `smtp_openssl_verify_mode`, `smtp_enable_ssl_tls`), `provider`, `provider_config` jsonb, `verified_for_sending` boolean.
- Entrada: `app/mailboxes/reply_mailbox.rb` chama `Mailbox::ConversationFinder` (`app/services/mailbox/conversation_finder.rb`). A ordem das estratégias (`DEFAULT_STRATEGIES`) é:
  1. `ReceiverUuidStrategy`
  2. `InReplyToStrategy`
  3. `ReferencesStrategy`
  4. `NewConversationStrategy`
  As estratégias estão em `app/services/mailbox/conversation_finder_strategies/`.
- IMAP: `app/mailboxes/imap/imap_mailbox.rb`.
- Saída: `app/mailers/conversation_reply_mailer.rb` e `conversation_reply_mailer_helper.rb` (CC e BCC). `app/mailers/references_header_builder.rb` monta o cabeçalho `References` a partir da mensagem respondida.
- Assunto de resposta: `additional_attributes['mail_subject']` ou `[#display_id] ...`.
- Templates de e-mail: tabela `email_templates` (`db/schema.rb:1204`): `name`, `body`, `template_type` enum (`layout` 0, `content` 1), `locale` enum, `inbox_id`. Layout base em `app/views/layouts/mailer/base.liquid`. Branding em `branded_email_layouts`.
- Ação de automação `send_email_to_team` (`app/services/automation_rules/action_service.rb`).
- Deduplicação: `messages.source_id` guarda o Message-ID.

### Inferences
- Para um "alias de suporte" com múltiplos endereços, a forma atual é criar uma inbox por endereço. Não existe roteamento por regra (ex.: "se o destinatário é billing@, vai para o time de cobrança").

### Gaps
- Não verifiquei o fluxo completo de "Email Continuity" (feature `email_continuity_on_api_channel`, desligada).

---

## 9. Central de ajuda, portal e visão do cliente final

### Takeaway
Existe Central de Ajuda (artigos, categorias, pastas e portal com domínio próprio). Não existe portal em que o cliente final vê os próprios tickets. Há duas superfícies parciais: a lista de conversas do widget de chat e a API pública por inbox e contato.

### Cited Findings
- `portals` (`db/schema.rb:1478`): `slug` único, `custom_domain` único, `config` jsonb, `channel_web_widget_id`, `color`. Relações: `categories`, `folders` (through categories), `articles`, `inboxes` (`inboxes.portal_id`).
- Rotas públicas da Central: `hc/:slug` e `hc/:slug/:locale` em `config/routes.rb`.
- Widget: `app/controllers/api/v1/widget/conversations_controller.rb#index` lista `@contact.conversations` filtrado por inbox. Se o contato é verificado por HMAC, a lista usa todas as conversas daquele contato (`api/v1/widget/base_controller.rb`, método `conversations`).
- Widget: `channel_web_widgets` tem `pre_chat_form_enabled`, `pre_chat_form_options` jsonb, `hmac_token`, `hmac_mandatory`.
- API pública (`config/routes.rb`, namespace `public`, por volta da linha 664): `inboxes/:inbox_id/contacts/:id/conversations` com `index`, `create`, `show`, `toggle_status`, `toggle_typing`, `update_last_seen`, e mensagens aninhadas.
- O contato é localizado por `contact_inboxes.source_id` (`app/controllers/public/api/v1/inboxes/conversations_controller.rb` e `contacts_controller.rb`). `process_hmac` é chamado antes.

### Inferences
- A API pública pode servir de base para um portal do cliente, mas a proteção depende do HMAC. Se `hmac_mandatory` não estiver ligado, quem conhece o `source_id` consegue listar conversas. É preciso confirmar essa configuração antes de expor a API como portal.
- Falta uma tela do cliente com lista de solicitações, status e histórico. O cliente também não recebe link de ticket em e-mail (não encontrei ocorrência desse link).

### Gaps
- Não li o controller de HMAC em detalhe. A avaliação de "mandatory" é inferida pelo nome das colunas.

---

## 10. Papéis e permissões

### Takeaway
Os papéis são só `agent` e `administrator`. Papéis customizados foram removidos com o enterprise, mas a coluna `account_users.custom_role_id` e a tabela `custom_roles` continuam no schema. A visibilidade de conversas é por inbox e por time. A constante de permissões no frontend já lista permissões finas.

### Cited Findings
- `account_users.role` enum (`app/models/account_user.rb:34`): `agent` 0, `administrator` 1. Coluna `custom_role_id` (`db/schema.rb:43-61`, com índice). Não existe model `CustomRole` na árvore atual.
- Tabela `custom_roles` (`db/schema.rb:1105-1113`): `name`, `description`, `account_id`, `permissions` text array.
- `app/policies/conversation_policy.rb`:
  - `index?` retorna true.
  - `destroy?` exige administrador.
  - `show?` vale para administrador, bot de agente, acesso por inbox (`inbox_access?`, via `user.inboxes`) ou acesso por time (`team_access?`, via `user.teams`).
  - Helpers: `assigned_to_user?`, `participant?`.
  - Hook `ConversationPolicy.prepend_mod_with('ConversationPolicy')`, que hoje não tem efeito.
- `app/services/conversations/permission_filter_service.rb`: administrador vê tudo. Agente vê conversas das inboxes em que é membro. Há uma variante com `plan_hint_selective_filter` para contas grandes.
- Constantes no frontend (`app/javascript/dashboard/constants/permissions.js`): `AVAILABLE_CUSTOM_ROLE_PERMISSIONS` = `conversation_manage`, `conversation_unassigned_manage`, `conversation_participating_manage`, `contact_manage`, `report_manage`, `knowledge_base_manage`. `ROLES` = `agent`, `administrator`.
- Impersonation de super admin: `app/services/impersonation_logger.rb`.

### Inferences
- Para um modelo Zendesk de permissões, a base já existe: `ConversationPolicy` e `PermissionFilterService`. Falta um modelo `CustomRole` em OSS, a ligação com `account_users.custom_role_id`, e a aplicação das permissões finas (`conversation_unassigned_manage`, `conversation_participating_manage`) nas policies e no filtro.

### Gaps
- Não há enforcement no backend OSS para as permissões finas da lista do frontend. Não encontrei nenhuma checagem dessas strings em `app/`.

---

## 11. Relatórios

### Takeaway
A OSS tem relatórios v2 com volume, tempos de primeira resposta, resolução e resposta, além de visões por agente, time, inbox, label e canal. O tempo em horário comercial é suportado. Não há relatórios de SLA nem de capacidade.

### Cited Findings
- Controllers v2 (`app/controllers/api/v2/accounts/`):
  - `reports_controller.rb`: `index`, `summary`, `bot_summary`, `agents`, `inboxes`, `labels`, `teams`, `conversations_summary`, `conversation_traffic`, `drilldown`
  - `summary_reports_controller.rb`: `agent`, `team`, `inbox`, `label`, `channel`
  - `live_reports_controller.rb`
- Métricas (`app/services/reports/report_metric_registry.rb`): `conversations_count`, `incoming_messages_count`, `outgoing_messages_count`, `avg_first_response_time`, `avg_resolution_time`, `reply_time`, `resolutions_count`, `bot_resolutions_count`, `bot_handoffs_count`.
- Builders: `app/builders/v2/report_builder.rb`, `app/builders/v2/reports/drilldown_builder.rb` (parâmetro `business_hours`), `app/builders/v2/reports/base_summary_builder.rb`.
- Eventos gravados (`app/listeners/reporting_event_listener.rb`): `conversation_resolved`, `first_reply_created`, `reply_created`, `conversation_bot_handoff`, `conversation_opened`. Tabela `reporting_events` (`db/schema.rb:1515`). Rollup em `reporting_events_rollups` (`db/schema.rb:1537`), com feature `report_rollup` desligada.
- CSAT: `csat_survey_responses/metrics` e `download`.

### Inferences
- Para relatórios de SLA é preciso gravar eventos de violação. Hoje `reporting_events` não tem nome específico para isso.

### Gaps
- Não há relatório por tipo de ticket, nem por vencimento, nem por reabertura.

---

## 12. Auditoria e histórico

### Takeaway
A trilha de histórico do ticket existe em forma de mensagens de atividade e de eventos de relatório. O audit log formal (gem `audited`) está configurado, mas aponta para uma classe que não existe, e não há mais tela nem API dele.

### Cited Findings
- Histórico do ticket: mensagens do tipo `activity` (`activity_message_handler.rb`), `reporting_events`, eventos de webhook (`conversation_updated`).
- Gem `audited ~> 5.4` no `Gemfile:185`.
- `config/initializers/audited.rb:4` aponta para `Enterprise::AuditLog`, inexistente.
- Tabela `audits` (`db/schema.rb:264-289`): `auditable_type`, `auditable_id`, `associated_*`, `user_*`, `username`, `action`, `audited_changes` jsonb, `version`, `comment`, `remote_address`, `request_uuid`, `city`, entre outros.
- Nenhum model OSS inclui o módulo de auditoria.
- Rota `resource :audit_logs` (`config/routes.rb:150`) sem controller. Cliente `api/auditLogs.js` e telas em `routes/dashboard/settings/auditlogs/`.
- Feature `audit_logs` premium e desligada. `featureFlags.js` lista também `audit_log_ip_address`.

### Inferences
- Para auditoria estilo Zendesk (quem mudou o quê, quando), a base seria a gem `audited` com um model OSS de auditoria, ou eventos explícitos em `reporting_events`.

### Gaps
- Não há histórico de alterações de campos customizados e de atributos do contato, exceto pelo que a gem gravaria.

---

## 13. Mapeamento Zendesk x fork

### Takeaway
A base é sólida em conversa, mensagens, canais, automação, macros, relatórios e Central de Ajuda. Os maiores gaps para um ticketing tipo Zendesk são: SLA (removido), tipo de ticket, vencimento, formulários de ticket, balanceamento por capacidade, skills, feriados, portal do cliente final, merge e vínculo entre tickets, e importação do Zendesk.

### Cited Findings
Legenda: Existe, Parcial ou Ausente. A coluna "Onde mudar" indica o ponto de partida no código.

| # | Conceito Zendesk | Equivalente no fork | Situação | Evidência | Onde mudar |
|---|---|---|---|---|---|
| 1 | Ticket | `Conversation` mais `messages` | Existe | `db/schema.rb:982`, `:1362` | Não precisa |
| 2 | Número do ticket | `display_id` único por conta | Existe | `db/schema.rb:990`, `:1011` | Não precisa |
| 3 | Assunto | `additional_attributes['mail_subject']`, só em e-mail | Parcial | `conversation_reply_mailer.rb:122` | Coluna `subject` em `conversations` (migration), criação e UI |
| 4 | Status Novo | Derivado de `open` sem assignee | Parcial | `conversation.rb:86` | Enum novo ou filtro derivado |
| 5 | Status Aberto, Pendente, Solucionado, Fechado | `open`, `pending`, `resolved`, sem `closed` separado | Parcial | `conversation.rb:86` | Decidir se `resolved` basta |
| 6 | Em espera (on hold) | `snoozed` com `snoozed_until` | Parcial | `conversation.rb:290` | Renomear visualmente ou criar status |
| 7 | Prioridade (baixa, normal, alta, urgente) | `low`, `medium`, `high`, `urgent`, nullable | Existe | `conversation.rb:87` | Renomear `medium` para normal na UI, se necessário |
| 8 | Tipo (pergunta, incidente, problema, tarefa) | Ausente | Ausente | sem ocorrência | Coluna enum em `conversations` ou custom attribute de lista |
| 9 | Solicitante | `contact_id` | Existe | `conversations.contact_id` | Não precisa |
| 10 | Submissor, "em nome de" | Só o autor da mensagem (`messages.sender_*`) | Parcial | `message.rb` | Coluna `submitter_id` em `conversations` |
| 11 | CCs do ticket | `conversation_participants` (só agentes) mais CC por mensagem | Parcial | `conversation_participants`, `message_builder.rb:100` | Tabela de CC de cliente ou leitura do primeiro e-mail |
| 12 | Seguidores (followers) | `conversation_participants` | Existe | `db/schema.rb:970` | Não precisa |
| 13 | Grupo | `teams` mais `conversations.team_id` | Existe | `db/schema.rb:1619` | Multi-time exigiria mudança de modelo |
| 14 | Responsável | `conversations.assignee_id` | Existe | `db/schema.rb:982` | Não precisa |
| 15 | Organização | `contact.company_id` mapeado para `companies` | Parcial | `db/schema.rb:764`, `:795` | Denormalizar `company_id` em `conversations` se preciso |
| 16 | Tags | `labels` e `cached_label_list` | Existe | `db/schema.rb:1307` | Não precisa |
| 17 | Campos customizados | `custom_attributes` mais `custom_attribute_definitions` (8 tipos, 3 escopos) | Parcial | `custom_attribute_definition.rb:48-49` | Obrigatoriedade condicional e campos por time |
| 18 | Formulários de ticket | Só `pre_chat_form` no widget | Ausente | `channel_web_widgets` | Model `TicketForm` e campos por formulário |
| 19 | Vencimento | Ausente | Ausente | sem ocorrência | Coluna `due_at` mais job de alerta |
| 20 | Metas de SLA | Removido. Restos em `sla_policies`, `applied_slas`, `sla_events` | Ausente | `db/schema.rb:1570`, `:179`, `:1553` | Reconstruir em OSS (ver seção 7) |
| 21 | Horário comercial | `working_hours` por inbox | Parcial | `db/schema.rb:1706` | Subir o nível para time ou SLA |
| 22 | Feriados | Ausente | Ausente | sem ocorrência | Tabela `holidays` ligada a `working_hours` |
| 23 | Atribuição automática (round robin) | `assignment_policies` mais `AutoAssignment` | Existe | `app/services/auto_assignment/` | Não precisa |
| 24 | Balanceamento por carga ou capacidade | Removido. `member_ids_with_assignment_capacity` devolve todos | Ausente | `inbox.rb` (perto da linha 203) | Tabela de capacidade, filtro e remoção do gate em `assignment_policy.rb:38` |
| 25 | Skills | Ausente | Ausente | sem ocorrência | Tabelas `skills` e `agent_skills`, e filtro na atribuição |
| 26 | Disponibilidade do agente | `account_users.availability` (online, offline, busy) | Parcial | `account_user.rb:35` | Estado "ausente" ou temporizador |
| 27 | Triggers (regras por evento) | `automation_rules` com 5 eventos | Existe | `automation_rule.rb:60-65` | Novos eventos em `automation_rule_listener.rb` |
| 28 | Automações por tempo | `execution_delay` (10 min a 30 dias) e `auto_resolve_after` | Parcial | `automation_rule.rb` | Job periódico para regras sem evento |
| 29 | Macros | `macros` (personal, global) | Existe | `db/schema.rb:1337` | Não precisa |
| 30 | Respostas prontas | `canned_responses` | Existe | `db/schema.rb:407` | Não precisa |
| 31 | Views (visões salvas) | `custom_filters` do tipo conversation | Parcial | `db/schema.rb:1093` | Compartilhamento, colunas e ordenação salvas |
| 32 | Busca | `search_service.rb` | Existe | `app/services/search_service.rb` | Não precisa |
| 33 | Mesclar tickets | Ausente. Só merge de contatos | Ausente | `contact_merge_action.rb` | Service de merge de conversas |
| 34 | Vincular tickets relacionados | Ausente | Ausente | sem ocorrência | Tabela `conversation_links` |
| 35 | Portal do cliente (ver os próprios tickets) | Widget e API pública | Parcial | `widget/conversations_controller.rb`, rotas `public` | Tela de portal sobre a API pública com HMAC obrigatório |
| 36 | Central de ajuda | `portals`, `categories`, `articles` | Existe | `db/schema.rb:1478` | Não precisa |
| 37 | E-mail com threading | `channel_email` mais estratégias do mailbox | Existe | `conversation_finder.rb` | Não precisa |
| 38 | Múltiplos endereços de suporte | Uma inbox por endereço | Existe | `db/schema.rb:598` | Roteamento por regra, se necessário |
| 39 | Resposta pública versus nota privada | `messages.private` | Existe | `db/schema.rb:1362` | Não precisa |
| 40 | CSAT | `csat_survey_responses` mais `csat_config` | Existe | `csat_survey_response.rb:36` | Não precisa |
| 41 | Relatórios de volume e tempo | Relatórios v2 | Existe | `app/builders/v2/` | Não precisa |
| 42 | Relatórios de SLA | Removidos | Ausente | `sla_*` removidos | Ver seção 7 e 11 |
| 43 | Papéis agente e administrador | `account_users.role` | Existe | `account_user.rb:34` | Não precisa |
| 44 | Papéis customizados e permissões finas | `custom_roles` removido. Permissões só por inbox e time | Ausente | `db/schema.rb:1105`, `policies/conversation_policy.rb` | Model `CustomRole` e enforcement |
| 45 | Auditoria | Gem `audited` mal configurada. Mensagens de atividade | Parcial | `config/initializers/audited.rb:4` | Model OSS de auditoria |
| 46 | Webhooks e API | `webhooks`, API v1, bots de agente | Existe | `webhook.rb:32-34` | Não precisa |
| 47 | Importação do Zendesk | Ausente. Existem importadores de Freshdesk e Intercom | Ausente | `app/services/data_imports/freshdesk/normalizer.rb` | Importador Zendesk, seguindo o padrão do Freshdesk |
| 48 | Tarefas (checklists) | Ausente | Ausente | sem ocorrência | Model `ConversationTask` |
| 49 | Tickets recorrentes ou agendados | Ausente | Ausente | sem ocorrência | Job e model de recorrência |
| 50 | Contagem de reaberturas | Ausente | Ausente | sem ocorrência | Contador em `conversations` ou evento |

### Inferences
- Os gaps de maior impacto para um ticketing tipo Zendesk, em ordem de prioridade: (1) SLA com horário comercial e feriados, (2) tipo, vencimento e assunto no ticket, (3) formulários de ticket, (4) balanceamento por capacidade e skills, (5) portal do cliente final, (6) papéis customizados com enforcement, (7) merge e vínculo entre tickets.
- Reconstruir SLA, papéis customizados, auditoria e capacidade em OSS é mais barato do que começar do zero, porque as tabelas, as telas e parte da lógica já existem no schema e no frontend. O custo principal é reconectar rotas e escrever os models e services.
- Reconstruir a partir do código do HEAD enterprise é risco de licença. A rota segura é uma implementação nova, inspirada no comportamento das tabelas e das telas.

### Gaps
- A coluna "Equivalente" de SLA e de papéis customizados se refere ao que existia no HEAD do enterprise. Esse código não está mais na árvore atual.
- Conceitos do Zendesk foram descritos com base em conhecimento geral. Não consultei a documentação oficial nesta pesquisa.

---

## 14. Pontos de atenção para o planejamento

- A árvore atual não está em estado funcional para SLA, papéis customizados, auditoria e capacidade. Antes de reconstruir é preciso decidir entre remover rotas e telas mortas (`config/routes.rb:138-302`, clientes em `app/javascript/dashboard/api/`) e reimplementar.
- Não reativar `ChatwootApp.enterprise?`. A regra do projeto proíbe usar `enterprise/`.
- Tabelas sem model OSS: `sla_policies`, `applied_slas`, `sla_events`, `agent_capacity_policies`, `inbox_capacity_limits`, `custom_roles`, `audits`, `conversation_monitors*`, `calls`, `captain_*`. Migrations novas seguem `CLAUDE.md`: gerar com `bundle exec rails g migration` e evitar FK de banco sem necessidade.
- Colunas novas em `conversations` (`subject`, `ticket_type`, `due_at`, `submitter_id`) pedem migration com índice, conforme as regras de modelo do `CLAUDE.md`.
- A regra de enforcement de permissões precisa passar por `ConversationPolicy` e por `PermissionFilterService`, que são os pontos de entrada compartilhados.

---

## 15. Lacunas da pesquisa

- Não rodei a aplicação nem as specs. Os erros de runtime citados são inferidos do código.
- Não inspecionei o VPS `servicedesk-dev` (`/opt/servicedesk-dev/chatwoot`) nem as branches `servicedesk/main` citadas na memória. Essas informações não puderam ser verificadas a partir do repo local.
- Não li o frontend em profundidade. Foram verificadas presença de arquivos, clientes de API e rotas, mas não o comportamento das telas.
- Não li o conteúdo dos specs de enterprise, que foram deletados.
- Não consultei fontes web sobre o Zendesk. O mapeamento usa conhecimento geral do modelo de dados.
