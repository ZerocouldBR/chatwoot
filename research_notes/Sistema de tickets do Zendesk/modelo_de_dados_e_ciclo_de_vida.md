# Zendesk Support: modelo de dados e ciclo de vida do ticket (estado em 2026)

Pesquisa feita em 2026-10-13, para replicação em fork do Chatwoot (Rails + Vue).

Legenda de confiança usada nas notas:
- **[F]**: página oficial lida diretamente via WebFetch. O WebFetch devolve um resumo produzido por modelo, então valores de enum e nomes de campo devem ser conferidos na página antes de virar contrato de API.
- **[S]**: trecho oficial obtido em resultado de busca (help center da Zendesk), sem leitura integral.
- **[T]**: fonte de terceiros (blogs, conectores, guias). Não usar como fonte normativa.
- **[I]**: inferência minha a partir das fontes.
- **[N]**: conhecimento prévio, não verificado nesta sessão.

Tentativas sem conteúdo: `developer.zendesk.com/api-reference/ticketing/ticket-management/ticket_fields/` (404), artigo de auto-fechamento `support.zendesk.com/hc/en-us/articles/4408883475354` (404). Não consegui ler as páginas de ticket forms, users, organizations, groups e brands na API.

---

## 1. Propriedades padrão do ticket (modelo de dados)

### Takeaway
A API v2 de Tickets expõe um objeto com cerca de 40 propriedades. `status` guarda a categoria (`new`, `open`, `pending`, `hold`, `solved`, `closed`). Quando status customizados estão ativos, `custom_status_id` guarda o rótulo específico. A maioria dos vínculos (requester, submitter, assignee, group, organization) é por ID.

### Cited Findings
- `status`: valores `"new"`, `"open"`, `"pending"`, `"hold"`, `"solved"`, `"closed"`. Com status customizados, representa a categoria. Note que a API chama on-hold de `hold` — [F] https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/
- `priority`: `"urgent"`, `"high"`, `"normal"`, `"low"` — [F] mesma página.
- `type`: `"problem"`, `"incident"`, `"question"`, `"task"` — [F] mesma página.
- `requester_id` (gravável): usuário que pediu o ticket — [F] mesma página.
- `submitter_id` (gravável): usuário que submeteu; por padrão é o usuário autenticado; vira o autor do primeiro comentário — [F] mesma página.
- `assignee_id`, `group_id`: agente atual e grupo — [F] mesma página.
- `organization_id` (gravável): precisa ser uma organização à qual o requester pertence — [F] mesma página.
- `collaborators` (somente escrita, na criação) e `collaborator_ids` (leitura): CCs — [F] mesma página.
- `follower_ids` (somente leitura) e `followers` (somente escrita, adiciona/remove agentes seguidores). Ignorados se CCs e seguidores não estiverem habilitados — [F] mesma página.
- `email_cc_ids` (somente leitura): agentes ou usuários finais em CC no ticket — [F] mesma página.
- `via` (somente leitura): descreve o canal de criação. `from_messaging_channel` (somente leitura): true se o canal for de mensageria — [F] mesma página.
- `external_id` (string): ID para vincular a registros locais; não precisa ser único — [F] mesma página.
- `due_at` (ISO 8601): data de vencimento, usada em tasks — [F] mesma página.
- `problem_id` (inteiro, em incidents): ID do problem vinculado. `has_incidents` (somente leitura, em problems) — [F] mesma página.
- `ticket_form_id`: resumo do modelo diz "Enterprise only" — [F, verificar].
- `custom_status_id`: ID do status customizado — [F] mesma página.
- `satisfaction_rating` (somente leitura): objeto com a avaliação, ou `"offered"` / `"unoffered"`; nulo em planos sem CSAT — [F] mesma página.
- `created_at` (somente leitura). `updated_at` (somente leitura) só muda quando a alteração gera evento no ticket — [F] mesma página.
- `allow_attachments` (booleano, padrão `true`): se agentes podem anexar a comentários — [F] mesma página.
- `is_public` (somente leitura): true se algum comentário for público — [F] mesma página.
- `allow_channelback` (somente leitura): false se channelback estiver desabilitado; aplica-se a tickets do channels framework — [F] mesma página.
- `sharing_agreement_ids`: substitui os acordos existentes — [F] mesma página.
- `custom_fields`: lista de pares `{id, value}` para gravar campos customizados — [F] mesma página.
- `tags`: o resumo diz que o comportamento padrão é sobrescrever as tags existentes — [F, ambíguo, verificar].
- Eventos: `Create`, `Change`, `Comment`, `Notification`, entre outros. O evento `Change` traz `value` e `previous_value` — [F] https://developer.zendesk.com/documentation/ticketing/reference-guides/ticket-audit-events-reference/

### Inferences
- [I] Modelo mínimo para réplica: ticket = (requester, submitter, assignee, group, organization, status, priority, type, tags, external_id, due_at) + participantes (CCs e seguidores) + comentários (seção 5) + eventos de auditoria (seção 5).
- [I] `status` (categoria) e `custom_status_id` (rótulo) coexistem. Automações e SLA leem a categoria, e o rótulo é só apresentação. Isso precisa ser decidido já no modelo.
- [I] `updated_at` só deve mudar em alterações que gerem evento. Operações internas (ex.: recalcular contadores) não devem tocar nesse campo.

### Gaps
- `subject`, `description`, `id`, `url`, `brand_id` (presente no ticket segundo o resumo da API, mas sem detalhe), `merged_ticket_ids` e `fields` não foram lidos na página. Os significados gerais são [N].
- Enum de `via.channel` não foi confirmado.
- A página da API não confirmou se `tags` sobrescreve ou acrescenta.

---

## 2. Statuses: semântica, transições e auto-fechamento

### Takeaway
Os seis status padrão seguem um fluxo claro. New é o estado inicial sem ação. Open é o estado de trabalho do agente. Pending aguarda o solicitante. On-hold (opcional) aguarda outra equipe e é invisível ao solicitante. Solved indica solução enviada. Closed é definido pelo sistema e não pode ser setado manualmente. Responder a um Solved reabre o ticket. Responder a um Closed cria um follow-up. O fechamento automático de Solved é de 4 dias por padrão.

### Cited Findings
- New: "no action has been taken on the ticket". Depois de alterado, o ticket não volta a New — [F] https://support.zendesk.com/hc/en-us/articles/8263915942938-About-the-ticket-lifecycle-and-ticket-statuses
- New é aplicado na chegada do ticket. Open é aplicado quando há atribuição a agente — [F] mesma página.
- Open: ticket atribuído e em andamento, "waiting for action by the agent" — [F] mesma página.
- Pending: agente aguarda informação do solicitante. Ao comentar, o solicitante faz o ticket voltar automaticamente para Open ("the ticket status is automatically reset to Open") — [F] mesma página.
- On-hold: "an internal status that the ticket requester never sees". É opcional e precisa ser ativado por um admin — [F] mesma página. O solicitante vê o ticket como Open — [T] https://www.getmacha.com/blog/zendesk-ticket-statuses-explained
- Solved: agente enviou a solução — [F] mesma página. Agentes setam Open, Pending, On-hold (se ativo) e Solved — [F] mesma página.
- Solved: resposta do solicitante reabre o ticket e ele vai para o agente que resolveu, salvo se um trigger mudar o responsável — [F] mesma página.
- Closed: "Tickets can't manually be set to Closed." O solicitante não pode mais reabrir — [F] mesma página. Fechamento é feito por automação — [F] mesma página.
- Resposta a um ticket Closed cria um follow-up request que referencia o original — [F] mesma página.
- Auto-fechamento padrão: "a ticket is closed automatically four days after it has been solved" — [F] mesma página.
- Automação "Close ticket 4 days after status is set to solved": prazo ajustável de 1 hora a 28 dias, sem possibilidade de desativar ou excluir — [S] resultados de busca do help center (artigo 4408883475354, que não abriu no fetch).
- Sistema: se nenhuma automação fechar um ticket Solved, ele fecha após 28 dias — [S] busca, e a página fetchada diz "If auto-close automations are deactivated: tickets will be closed automatically 28 days after they're solved" — [F]. **Conflito**: a busca diz que a automação não pode ser desativada, e a página fala em desativação. Verificar na Admin Center.
- Zendesk sugere fechar entre 3 e 5 dias após Solved — [S] busca.
- Closed: "archived for later reference". Tickets fechados não podem ser modificados, com exceções descritas em artigo ligado. Ainda podem ser buscados, aparecem em views e podem ser excluídos por quem tiver permissão — [F] mesma página de lifecycle.
- Arquivamento de Closed após 120 dias — [S] https://support.zendesk.com/hc/en-us/articles/4408887617050-About-ticket-archiving (detalhes na seção 8).
- **Conflito de SLA**: um blog diz que On-hold não pausa SLA, diferente de Pending. Outro diz que Pending pausa o SLA — [T] https://www.eesel.ai/blog/zendesk-ticket-status-lifecycle. O artigo de lifecycle não trata de SLA — [F]. Não resolvido.

### Inferences
- [I] Grafo de transições derivado das fontes:
  - new → open (atribuição).
  - open ↔ pending (agente aguarda solicitante; resposta do solicitante volta para open).
  - open ↔ hold (agente; solicitante continua vendo open).
  - open / pending / hold → solved (agente).
  - solved → open (resposta do solicitante; reatribuído ao agente que resolveu, salvo trigger).
  - solved → closed (automação, padrão 4 dias).
  - closed → nenhuma transição. Resposta gera novo ticket de follow-up.
  - qualquer estado → new é proibido depois de sair de new.
  - Não existe transição manual para closed.
- [I] Como o solicitante reabre um solved, ele é uma transição disparada por evento de comentário, e não por edição de status.

### Gaps
- Não confirmei quais status o solicitante pode setar diretamente via Help Center ou API de usuário final.
- O efeito de uma resposta do solicitante sobre On-hold não está documentado no artigo.
- Conflito sobre fechamento de 28 dias (ver acima).
- Sem fonte oficial sobre contagem de reaberturas nas métricas.

---

## 3. Status customizados (status categories)

### Takeaway
Status customizados são rótulos (`agent_label`, `end_user_label`) pendurados em uma de cinco categorias fixas: `new`, `open`, `pending`, `hold`, `solved`. `closed` pertence à categoria `solved`. Admins não criam nem alteram categorias. Limites: 300 status no total e 100 por categoria.

### Cited Findings
- Campos do objeto: `id` (somente leitura); `agent_label` (obrigatório, até 48 caracteres); `end_user_label` (até 48); `description`; `end_user_description`; `active` (booleano); `default` (booleano); `status_category` (obrigatório, enum `new` / `open` / `pending` / `hold` / `solved`); `raw_*` (placeholders dinâmicos, somente leitura); `created_at`, `updated_at`, `url` — [F] https://developer.zendesk.com/api-reference/ticketing/tickets/custom_ticket_statuses/
- **Conflito interno da página**: `end_user_label` aparece como opcional na tabela de propriedades, mas o endpoint de criação diz que ele é obrigatório — [F] mesma página.
- Categorias não podem ser criadas, alteradas ou excluídas pela API. Cada categoria tem um status padrão sempre ativo. O padrão só muda pelo endpoint de default em lote — [F] mesma página.
- `hold` e seu status de sistema são opcionais. Se `hold` estiver inativo, não precisa de default ativo — [F] mesma página.
- Limites: 300 status customizados por conta e 100 por categoria — [F] mesma página.
- Endpoints:
  - `GET /api/v2/custom_statuses` (end users podem; sem paginação; filtros `active`, `default`, `status_categories`) — [F].
  - `GET /api/v2/custom_statuses/{custom_status_id}` (end users podem) — [F].
  - `POST /api/v2/custom_statuses` (somente admin; exige `agent_label`, `end_user_label`, `status_category`) — [F].
  - `PUT /api/v2/custom_statuses/{custom_status_id}` (somente admin; `status_category` não é atualizável) — [F].
  - `PUT /api/v2/custom_status/default` (admin; parâmetro `ids`) — [F].
  - Endpoint de exclusão: detalhes não capturados pelo fetch — [F, gap].
- Criação na Admin Center: Objects and rules > Tickets > Ticket statuses, escolhendo categoria — [S] https://support.zendesk.com/hc/en-us/articles/4412575841306-Enabling-Custom-Statuses
- Desativar status customizados faz o ticket voltar à categoria. Exemplo do artigo: "Open Investigating" vira Open — [S] mesma página.
- **Conflito sobre categorias**: um blog de setembro de 2026 diz que status customizados só se ligam a quatro categorias, e que New e Closed não podem receber status — [T] https://www.getmacha.com/blog/zendesk-custom-ticket-status-model. A API diz cinco categorias — [F]. Prevalece a API até que se confirme o contrário.
- Automações e SLA usam a categoria por baixo do rótulo — [T] mesma fonte do blog. Não verificado na documentação oficial.

### Inferences
- [I] Modelo sugerido: `ticket_statuses(id, category enum, agent_label, end_user_label, description, end_user_description, active, default)`. Ticket guarda `status` (categoria) e `custom_status_id` (FK opcional).
- [I] Cada categoria deve ter exatamente um default ativo, enforçado no model (validação), e não por convenção.
- [I] Um status customizado desativado deve cair para a categoria, sem reescrever o histórico.

### Gaps
- Detalhes do endpoint de exclusão.
- Confirmação oficial sobre quais categorias aceitam status customizados.
- Permissões de criação e edição por tipo de agente.

---

## 4. Tipos (question, incident, problem, task) e prioridade

### Takeaway
`type` e `priority` são enums fixos na API. O comportamento não trivial está no vínculo incident → problem. Ao resolver um problem, todos os incidents vinculados são resolvidos em massa e recebem o comentário de solução. Tasks usam `due_at`. Não encontrei documentação oficial sobre o uso do tipo `question`.

### Cited Findings
- Enums de `type` e `priority` — [F] https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/
- Confirmação de valores também em conector — [T] https://docs.workato.com/connectors/zendesk/ticket-fields.html
- Fluxo de problem e incident: criar o problem; mudar os duplicados para `incident` e vinculá-los; resolver o problem. Isso resolve todos os incidents vinculados e adiciona o comentário de solução aos que ainda não estiverem resolvidos. O campo Type precisa estar no formulário — [S] https://support.zendesk.com/hc/en-us/articles/4408835103898
- Resolver um incident individualmente deixa os outros abertos. A recomendação é não fazer isso — [S] mesma fonte.
- Reabrir um problem resolvido não reabre os incidents. É preciso selecionar os incidents na aba Incidents, editar em lote, reabrir e só então resolver o problem de novo — [S/T] mesma fonte e getmacha.
- Campos obrigatórios vazios nos incidents não bloqueiam o fechamento em massa — [S] mesma fonte.
- Vinculação é manual: nada no Zendesk liga incidents automaticamente — [T] https://www.getmacha.com/blog/zendesk-problem-incident-linking
- `has_incidents` é verdadeiro quando um problem tem incidents vinculados — [F] API.
- Task: `due_at` é a data de vencimento usada em tasks — [F] API. Tasks para trabalho interno com prazo — [T] https://www.eesel.ai/blog/zendesk-ticket-type-incident-problem-task
- Prioridade: sugestões de uso (low para dúvidas gerais, normal como padrão, high para impacto em vários usuários ou funções críticas, urgent para indisponibilidade ou segurança) — [T] https://www.eesel.ai/blog/zendesk-ticket-priority-urgency-impact. Não é definição oficial.
- O mesmo blog diz que é possível renomear as prioridades. Não confirmado em fonte oficial, e o enum da API é fixo — [F] + [T].

### Inferences
- [I] Problem/incident deve ser uma relação `incident.problem_id → problem`, com ação em lote "resolver problem = resolver incidents" feita no serviço, e não por callback isolado em cada incident.
- [I] Como o fechamento em massa ignora campos obrigatórios, a validação de "required to solve" não pode ser aplicada no caminho em lote sem uma decisão explícita.

### Gaps
- Semântica exata do tipo `question`.
- Regras de SLA por tipo ou prioridade.
- Se prioridades podem ser renomeadas ou acrescidas (a API sugere que não).

### Mapeamento para o fork Chatwoot (inferência, com base no código)
- Chatwoot tem `enum status: { open: 0, resolved: 1, pending: 2, snoozed: 3 }` e `enum priority: { low: 0, medium: 1, high: 2, urgent: 3 }` em `app/models/conversation.rb` (linhas 86-87). Não há "none" nem "normal".
- [I] Mapeamento inicial possível: new/open → `open`; pending → `pending`; hold → `snoozed` ou status customizado sobre `pending` (decisão de produto); solved → `resolved`; closed → `resolved` com flag de arquivado. Prioridade normal ↔ medium, com renomeação na camada de UI.
- [I] Não há tipos (question, incident, problem, task) nem vínculo de problem/incident no modelo atual. Isso precisa ser adicionado como modelo novo.

---

## 5. Comentários, notas internas, privacidade, redação e eventos de auditoria

### Takeaway
Cada comentário é público ou privado. Comentário público é visível a todos com acesso ao ticket, inclusive CCs. Comentário privado é visível só a agentes. A conversão de público para privado é unidirecional e gera evento. A redação remove conteúdo de comentários e anexos, mas não o ticket inteiro. O log de auditoria tem tipos de evento documentados e a própria Zendesk diz que novos tipos podem surgir.

### Cited Findings
- Visibilidade: comentário público é visto por quem tem acesso ao ticket, incluindo CCs. Comentário privado é visto só por agentes — [S] https://support.zendesk.com/hc/en-us/articles/4408846470170-Redacting-ticket-content (resultado de busca sobre comentários e notas)
- Agentes e admins podem converter comentário público em privado. A conversão é unidirecional: não volta a ser público, e deixa de aparecer para usuários finais — [S] mesma família de artigos.
- Conversões geram evento no ticket — [S] mesma fonte, e [F] tipo `CommentPrivacyChange`.
- Redação cobre comentários públicos, notas internas, imagens e anexos, com limitações por canal. Não remove o ticket inteiro — [S] https://support.zendesk.com/hc/en-us/articles/4408846470170-Redacting-ticket-content
- Permissão para redigir: ligada à permissão de excluir tickets, nos planos sem custom roles — [S] mesma fonte.
- Tipos de evento documentados em `ticket audit events`: `Create`, `Change`, `Comment`, `CommentRedactionEvent`, `AttachmentRedactionEvent`, `VoiceComment`, `CommentPrivacyChange`, `SuspendedTicketRecovery`, `Notification`, `NotificationWithCcs`, `SmsNotification`, `Cc`, `FollowerNotificationEvent`, `FollowersChange`, `EmailCcChange`, `MacroReference`, `SatisfactionRating`, `TicketSharingEvent`, `OrganizationActivity`, `Error`, `External`, `Push`, `ChatStartedEvent`, `ChatEndedEvent`, `SurveyOffered`, `SurveyResponseSubmitted`, `OfferedToEvent`, `RoutingChannelEvent`, `CollabThreadCreated`, entre outros — [F] https://developer.zendesk.com/documentation/ticketing/reference-guides/ticket-audit-events-reference/
- Em eventos `Comment`, a propriedade `public` indica visibilidade — [F] mesma página.
- `CommentRedactionEvent` registra `comment_id` e a string redigida. `AttachmentRedactionEvent` registra `attachment_id` e `comment_id` — [F] mesma página.
- Eventos `Change` têm `value` e `previous_value`. Em `tags`, esses valores são arrays. Campos de SLA são objetos — [F] mesma página. A lista completa de `field_name` não está na página.
- A Zendesk diz que pode adicionar tipos de evento, e que integrações devem ignorar tipos não documentados — [F] mesma página.
- Comunidade: não é possível editar nota interna, nem com acesso de admin. Usuários pedem que alterações de notas apareçam no log — [S/comunidade] https://support.zendesk.com/hc/de/community/posts/4409222727194-Edit-internal-notes. Pedido de usuário, não recurso documentado.

### Inferences
- [I] Modelo de comentário: `comments(ticket_id, author_id, body, public boolean, via, created_at)` e `comment_attachments`. Conversão público → privado: um único sentido, com evento.
- [I] Redação como substituição do conteúdo (campo zerado e marcado), com evento `CommentRedactionEvent` / `AttachmentRedactionEvent`, e não como exclusão da linha.
- [I] Log de auditoria: tabela append-only com `event_type`, `field_name`, `value`, `previous_value`, `actor_id`, `created_at`. Os nomes de tipo podem seguir o padrão da Zendesk, mas o conjunto deve ser o que o produto usa.

### Gaps
- Limite de tamanho de anexo e regras de tipo de arquivo.
- Janela de edição de comentário público e de nota interna, se existir.
- Efeito de um comentário privado sobre a visibilidade de CCs e seguidores.
- Lista completa de `field_name` em eventos `Change`.

---

## 6. Campos do ticket, formulários e campos condicionais

### Takeaway
Campos de sistema (assignee, priority, group etc.) não são exibidos a usuários finais no formulário. Campos customizados só aparecem para o usuário final se forem marcados como visíveis para ele. Campos condicionais são configurados por formulário e por audiência (agente ou usuário final). O "Required" muda conforme a audiência. Não consegui confirmar a lista de tipos de campo nem o modelo de formulários na API.

### Cited Findings
- Campos customizados só chegam ao cliente depois de ficarem visíveis para usuário final. Campos de sistema, como atribuição e prioridade, não aparecem no formulário de ticket para o usuário final — [S] https://support.zendesk.com/hc/en-us/articles/4408834799770-Creating-conditional-ticket-fields
- Somente admins criam e gerenciam condições. Cada condição vale para agentes ou para usuários finais. Condições de agente afetam a interface de agente; condições de usuário final afetam formulários do Help Center e do Web Widget (Classic) — [S] mesma fonte.
- O "Required" depende de a condição ser de agente ou de usuário final. O trecho que li foi cortado, então não confirmei se existe obrigatoriedade apenas na resolução — [S] mesma fonte.
- Quando um agente abre um ticket como requester, os campos condicionais precisam estar preenchidos antes de o agente responder pelo Help Center — [S] mesma fonte.
- Lógica condicional vale só na submissão. Na página de Requests, o usuário vê todos os campos visíveis, inclusive os condicionais não preenchidos — [S] mesma fonte.
- Limite de 1500 condições por formulário, por tipo de usuário — [S] mesma fonte.
- Relato de comunidade: campo condicional aparecia no formulário principal antes da opção gatilho ser escolhida — [S/comunidade] mesma fonte.
- Terceiros dizem que `required` é por campo e vale para todos os formulários. Isso conflita com a regra por audiência da Zendesk. Considerar a fonte pouco confiável neste ponto — [T] https://www.getmacha.com/blog/zendesk-ticket-fields-vs-forms
- `ticket_form_id`: resumo da API diz "Enterprise only" — [F, verificar].

### Inferences
- [I] Modelo de condição: `ticket_form_conditions(form_id, audience enum agent|end_user, parent_field, parent_value, child_field, required boolean)`. Validar limite de 1500 por formulário e por audiência no próprio model, antes de salvar.
- [I] Como o "Required" é por audiência, a validação deve ser feita em dois pontos: formulário do usuário final e formulário do agente.

### Gaps
- Lista oficial de tipos de campo (`text`, `textarea`, `checkbox`, `date`, `integer`, `decimal`, `regexp`, `tagger` / dropdown, `multiselect`, `partial_credit_card`, `lookup`). Os nomes de API são [N], e a página da API de ticket fields retornou 404.
- Comportamento de tags em dropdown e checkbox.
- Semântica de lookup relationship.
- "Required to solve": não confirmado em fonte oficial.
- Modelo completo de ticket forms (múltiplos formulários por marca, formulário padrão) não lido.

---

## 7. Usuários, organizações, grupos e marcas

### Takeaway
As docs de desenvolvedor descrevem três papéis: end user, agent e admin. Um guia de terceiros de março de 2026 lista cinco níveis, incluindo Light Agent e Account Owner, mas isso não foi confirmado. Agentes podem pertencer a vários grupos e cada um precisa de pelo menos um. Organizações podem ser usadas em regras de atribuição. Marcas não foram pesquisadas.

### Cited Findings
- Papéis: end users, agents e admins — [S] resultados de busca de https://developer.zendesk.com/rest_api/docs/support/users e https://developer.zendesk.com/api-reference/ticketing/users/users/ (páginas não lidas).
- Cinco níveis: End User, Light Agent, Agent, Administrator e Account Owner — [T] https://www.stitchflow.com/user-management/zendesk/manual (guia de terceiros, março de 2026).
- Admins têm todas as capacidades de agente, mais as administrativas — [S] busca.
- Agentes não acessam configurações administrativas, como business rules e automações, mas podem criar macros e views pessoais — [S] busca.
- Agentes podem pertencer a vários grupos. Cada agente precisa estar em pelo menos um grupo. Grupos só aceitam agentes e admins, não usuários finais — [S] busca (artigos 4408836154266 e 360002029747).
- Organizações são coleções de usuários finais. Podem também incluir funcionários — [S] busca.
- Exemplo de auto-atribuição por organização: um ticket de usuário de uma empresa específica vai para o grupo que atende aquela empresa — [T] https://www.oreilly.com/library/view/practical-zendesk-administration/9781491900741/ch01.html (livro).
- Recomendação de no máximo 5 admins — [S] busca.
- Custom roles de agente: as docs de desenvolvedor dizem Enterprise. Um guia de terceiros diz Suite Professional. Um artigo de suporte diz que em planos inferiores é possível definir permissões extras por agente, como acesso a tickets — [S/T]. **Conflito**.
- `organization_id` do ticket precisa ser uma organização do requester — [F] API de tickets.
- Compartilhamento de tickets: `sharing_agreement_ids` na API de tickets e evento `TicketSharingEvent` — [F].

### Inferences
- [I] Ao modelar papéis, é mais seguro começar com três (end_user, agent, admin) e tratar light agent como extensão, dado o conflito.
- [I] Auto-atribuição por organização deve ser uma regra de atribuição consultando `organization_id` na criação do ticket, e não um campo fixo.

### Gaps
- Email identities, múltiplos emails por usuário, user fields e identities não foram lidos.
- Regra de mapeamento de domínio de email para organização: não encontrada.
- Marcas (brands): não pesquisei modelo, escopo de formulários e de visibilidade.
- Light Agent: capacidades não confirmadas.

---

## 8. Mesclagem, follow-up, vinculação, exclusão, arquivamento, suspensos e spam

### Takeaway
Confirmado: follow-up é criado por resposta a ticket Closed, e arquivamento acontece cerca de 120 dias após o fechamento, com exceções por volume de eventos. Não encontrei fonte oficial sobre merge, tickets suspensos, spam e exclusão. Qualquer decisão de produto nessas áreas precisa de pesquisa adicional.

### Cited Findings
- Follow-up: resposta a Closed cria novo ticket que referencia o original — [F] lifecycle.
- Arquivamento: normalmente 120 dias após o ticket ser fechado. Contas de volume muito alto podem ter arquivamento antes disso — [S] https://support.zendesk.com/hc/en-us/articles/4408887617050-About-ticket-archiving (busca).
- Tickets com mais de 10.000 eventos não são arquivados automaticamente — [S] mesma fonte, versão inglesa. A versão italiana da busca também cita limite de 2 MB em registros associados — [S] https://support.zendesk.com/hc/it/articles/4408887617050-Ticket-Archiving. Divergência entre idiomas a verificar.
- Tickets arquivados continuam acessíveis por URL direta, busca e perfis de usuário, grupo e organização — [S] mesma fonte.
- Tickets arquivados saem de views, regras e contexto do cliente, mas continuam em relatórios, exportação e API — [S] resumo de IA na versão espanhola da mesma página. Trate com cautela.
- Não há view nem filtro específico de tickets arquivados. A alternativa é buscar tickets fechados há mais de 120 dias — [S] busca.
- Vinculação de problem e incident: ver seção 4.
- Merge: as fontes encontradas são blogs de terceiros, que descrevem merge como consolidação de conversas em um só fio. Não há informação oficial sobre quem fica como ticket principal, sobre histórico, nem sobre o efeito no arquivamento — [T] https://www.eesel.ai/blog/how-to-merge-tickets-in-zendesk
- Eventos de referência para suspensos e compartilhamento: `SuspendedTicketRecovery` e `TicketSharingEvent` — [F] audit events. Regras de suspensão e spam não lidas.

### Inferences
- [I] Arquivamento como flag e job diário: tickets fechados há 120 dias ou mais viram arquivados, saem de views e de automações, e continuam acessíveis por URL e busca. Os limites de eventos precisam de confirmação antes de virar regra.
- [I] Merge exige decisão de produto sobre o que acontece com comentários, participantes e status dos tickets envolvidos. Não há base oficial suficiente para replicar isso agora.

### Gaps
- Merge: regras, status resultante, tratamento de CCs e de anexos.
- Tickets suspensos: critérios e fila.
- Spam: regras e ação.
- Exclusão e janela de recuperação de tickets excluídos.
- Vínculos genéricos entre tickets, além de problem/incident.

---

## 9. CCs e seguidores (CCs and followers)

### Takeaway
São dois mecanismos diferentes. CCs (`collaborators`) são pessoas em cópia que recebem notificações e podem responder publicamente. Podem ser agentes ou usuários finais. Seguidores são só agentes, internos, e não aparecem nas notificações para os outros participantes. Configuração em Admin Center > Objects and rules > Tickets > Settings.

### Cited Findings
- CCs podem ser adicionados por agentes e por usuários finais. Quem está em CC pode responder publicamente, ou remover o requester da notificação para responder em privado — [S] https://support.zendesk.com/hc/en-us/articles/4408843795482-Configuring-CC-and-follower-permissions
- Limite de 48 CCs de email por ticket — [S] busca. A fonte exata não ficou clara no snippet, então verificar.
- Agentes em CC ficam com o email visível para todos os usuários finais do thread — [S] mesma fonte.
- Seguidores são internos. Não aparecem nas notificações por email para outros participantes e ficam invisíveis para usuários finais. Usuários finais não podem adicionar seguidores — [S] mesma fonte.
- Auto-follow: agente em CC por email ou pela interface do ticket também vira seguidor. Agente em CC via formulário do Help Center ou pela API não vira seguidor — [S] mesma fonte.
- Toggle "Enable CCs for end users on help center". Se "Anybody can submit tickets" estiver desligado, CCs não cadastrados são ignorados — [S] mesma fonte.
- Se um usuário final em CC responder pelo email usando Reply (em vez de Reply all), a resposta vira comentário privado por padrão. Admins podem alterar — [S] mesma fonte.
- Funcionalidade indisponível em contas trial — [S] mesma fonte.
- Campos na API: `collaborators` (escrita, na criação), `collaborator_ids` (leitura), `follower_ids` (somente leitura), `followers` (escrita, adiciona/remove agentes; ignorado se o recurso não estiver habilitado), `email_cc_ids` (somente leitura) — [F] API de tickets.
- Eventos: `Cc`, `EmailCcChange`, `FollowersChange`, `FollowerNotificationEvent`, `NotificationWithCcs` — [F] audit events.
- Afirmação de terceiros de que não há limite de seguidores. Não confirmada — [T] https://www.eesel.ai/blog/zendesk-cc-vs-follower-email

### Inferences
- [I] Modelo: `ticket_participants(ticket_id, user_id, role enum cc|follower, origin enum email|help_center|api|agent_ui)`. O `origin` é necessário para reproduzir a regra de auto-follow.
- [I] O comportamento de Reply versus Reply all de um CC é uma armadilha de privacidade. Se for replicado, deve ser explícito e documentado para o agente.

### Gaps
- Limite de seguidores.
- Se seguidores podem ser adicionados pelo Help Center.
- Mecânica exata de adição de CC por email.

---

## Lacunas e conflitos que afetam a implementação

- **Conflito**: fechamento de Solved sem automação (28 dias): a página diz que é a regra quando a automação é desativada, e a busca diz que a automação não pode ser desativada. Verificar na Admin Center.
- **Conflito**: categorias de status customizados: API com cinco categorias, blog de terceiros com quatro.
- **Conflito**: `end_user_label` obrigatório ou opcional na mesma página da API de status customizados.
- **Conflito**: SLA com On-hold versus Pending. Não resolvido.
- **Conflito**: custom roles disponíveis em Enterprise (docs de desenvolvedor) versus Suite Professional (terceiro).
- **Conflito**: arquivamento com limite de 2 MB (versão italiana) versus 10.000 eventos (versão inglesa).
- **Não pesquisado ou sem fonte**: merge, tickets suspensos, spam, exclusão, marcas, lista de tipos de campo, ticket forms na API, users API (identities, emails, user fields), Light Agent, mapeamento de domínio de email para organização.
- **Métodos**: a pesquisa usou 16 chamadas de busca e leitura web (WebSearch e WebFetch), acima do limite típico de 10 a 15 do protocolo de pesquisa. Isso se deve à amplitude do escopo.
