# Zendesk Support: API e plataforma de extensibilidade em torno de tickets (estado em 2026)

Consulta feita em 2026-10-13. Fonte principal: referência oficial em developer.zendesk.com, complementada por um artigo da Central de Ajuda para a sintaxe de busca.

Ressalvas de método, que o leitor deve considerar:
- As páginas foram lidas com WebFetch, que devolve um resumo gerado por modelo pequeno e não o HTML bruto. Nomes de campos, limites e cabeçalhos devem ser conferidos contra a especificação OpenAPI oficial (https://developer.zendesk.com/zendesk/oas.yaml). Esse arquivo apareceu em resultado de busca, mas não foi aberto.
- O trecho sobre `update_many` veio de snippet de busca, não da página completa.
- Quatro páginas retornaram 404 para os caminhos tentados: eventos de auditoria, localizações do ZAF, Custom Objects e verificação de assinatura de webhooks. Não há conteúdo verificado sobre elas.
- As páginas lidas não mostram datas de 2025 ou 2026, então "estado atual" significa o que as páginas exibiam na data da consulta. Não há changelog confirmado.

## 1. Objeto Ticket: campos e forma do JSON

### Conclusão
O objeto ticket é plano: relações são ids numéricos (`requester_id`, `assignee_id`, `group_id`, `organization_id`, `brand_id`), e status e prioridade são strings. Vários campos são só de escrita (`comment`, `requester`, `followers`) ou só de leitura (`id`, `url`, `created_at`, `via`). `description` é ignorada na atualização.

### Achados com fontes
- Endpoints de leitura: `GET /api/v2/tickets`, `GET /api/v2/tickets/{ticket_id}`, `GET /api/v2/tickets/count`, `GET /api/v2/tickets/recent` e `GET /api/v2/organizations/{organization_id}/tickets` (com `/count`). Fonte: [Tickets](https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/)
- Campos extraídos da tabela do objeto (RO = somente leitura, WO = somente escrita):
  - Identificação: `id` (RO), `url` (RO), `encoded_id` (RO), `external_id` (não único), `type` (`problem`, `incident`, `question`, `task`).
  - Conteúdo: `subject`, `raw_subject` (placeholder de conteúdo dinâmico), `description` (primeiro comentário na criação; ignorada na atualização), `comment` (WO; primeiro comentário na criação), `priority` (`urgent`, `high`, `normal`, `low`), `status` (`new`, `open`, `pending`, `hold`, `solved`, `closed`), `custom_status_id`, `tags` (substituem as existentes por padrão), `custom_fields` (array de id e valor).
  - Pessoas: `requester_id`, `requester` (WO; aceita e-mail, id ou objeto), `submitter_id` (vira autor do primeiro comentário), `assignee_id`, `assignee_email` (WO), `group_id`, `organization_id`, `brand_id`, `collaborator_ids`, `collaborators` (WO; adiciona CCs na criação), `additional_collaborators` (WO; envia e-mail aos colaboradores na atualização), `email_cc_ids` (RO), `email_ccs` (WO), `follower_ids` (RO), `followers` (WO).
  - Datas: `created_at` (RO), `updated_at` (RO; muda só com eventos de ticket), `generated_timestamp` (RO; Unix, inclui atualizações de sistema), `due_at` (ISO 8601; usado no tipo `task`).
  - Relações entre tickets: `problem_id`, `has_incidents` (RO), `followup_ids` (RO), `via_followup_source_id` (WO), `sharing_agreement_ids`.
  - Origem e canal: `via` (RO), `via_id` (WO), `from_messaging_channel` (RO), `allow_channelback` (RO), `allow_attachments` (RO), `recipient`, `forum_topic_id` (a página o descreve como depreciado).
  - Outros: `is_public` (RO), `satisfaction_rating` (RO), `support_type` (`agent` ou `ai_agent`), `ticket_form_id` (a página indica que é só Enterprise), `attribute_value_ids` (WO), `macro_ids` (WO), `metadata` (WO), `system_metadata` (WO), `voice_comment` (WO).
  - Controle de concorrência: `safe_update` (WO) e `updated_stamp` (WO), usados juntos para evitar colisão de atualização.
  - Fonte: [Tickets](https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/)
- A página não marca nenhum campo como obrigatório. Fonte: [Tickets](https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/)
- Criação de tickets aceita o header `Idempotency-Key`, e as chaves expiram em duas horas. Fonte: [Ticketing introduction](https://developer.zendesk.com/api-reference/ticketing/introduction/)

### Inferências
- Os campos mais difíceis de replicar são `collaborators` e `followers`, que têm semântica de adicionar ou remover no escrever e lista de ids no ler. Também são difíceis `custom_fields` (array de id e valor) e `via`.
- Status: o Chatwoot tem `open`, `resolved`, `pending`, `snoozed` (`app/models/conversation.rb:86`). O Zendesk tem seis valores. Pelos nomes, `solved` corresponde a `resolved` e `hold` a `snoozed`. `new` e `closed` não têm equivalente direto. Isso é inferência de nomes, não de semântica, e exige decisão de produto.
- Prioridade: o Chatwoot tem `low`, `medium`, `high`, `urgent` (`app/models/conversation.rb:87`). O Zendesk usa `normal` onde o Chatwoot usaria `medium`. Inferência de nomes.
- `type` (`problem`, `incident`, `question`, `task`) e o par `problem_id`/`has_incidents` não têm campo correspondente no que li do Chatwoot. Só li os enums de status e prioridade, não o schema completo.

### Lacunas
- O conteúdo da página de Tickets foi truncado antes das seções de criação, atualização e exclusão. Ver seção 2.
- Os tipos exatos de `tags` e `requester` (que é união de tipos na escrita) não foram confirmados. Conferir no OAS.
- Não há confirmação de quais campos são nativos e quais são customizados além de `custom_fields`.

## 2. Criação, atualização em lote e jobs

### Conclusão
A atualização em lote é assíncrona: a chamada devolve um `job_status`, que é consultado depois. Não confirmei a criação unitária nem a criação em lote de tickets pela API de Tickets. Só confirmei a criação em lote pela API de importação (seção 11).

### Achados com fontes
- `PUT /api/v2/tickets/update_many` aceita até 100 tickets por chamada. Para a mesma alteração em vários tickets, os ids vão em `ids` na query, com um único objeto `ticket`. Para alterações diferentes, envia-se o array `tickets` no corpo, com `id` em cada item. Fonte: snippet de busca de [Tickets](https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/) (página não lida por inteiro)
- A resposta é um objeto `job_status`, e o trabalho roda em background. Fonte: [Job Statuses](https://developer.zendesk.com/api-reference/ticketing/ticket-management/job_statuses/)
- Tags em lote: `additional_tags` e `remove_tags` no objeto ticket adicionam ou removem tags sem sobrescrever as existentes. Fonte: snippet de busca de [Adding tags to tickets without overwriting existing tags](https://developer.zendesk.com/documentation/ticketing/managing-tickets/adding-tags-to-tickets-without-overwriting-existing-tags/) (página não aberta)
- Endpoints de job status, só para agentes:
  - `GET /api/v2/job_statuses` (lista, com cursor)
  - `GET /api/v2/job_statuses/show_many?ids=` (ids separados por vírgula)
  - `GET /api/v2/job_statuses/{job_status_id}`
  Fonte: [Job Statuses](https://developer.zendesk.com/api-reference/ticketing/ticket-management/job_statuses/)
- Campos do job status, todos somente leitura: `id` (string, atribuído ao enfileirar), `job_type`, `message`, `progress` (inteiro, tarefas concluídas), `total` (inteiro), `status`, `results` (array) e `url` (endereço para consultar o andamento). Fonte: [Job Statuses](https://developer.zendesk.com/api-reference/ticketing/ticket-management/job_statuses/)
- Valores de `status`: `queued`, `working`, `failed`, `completed`. O valor é `completed`, não `complete`. Fonte: [Job Statuses](https://developer.zendesk.com/api-reference/ticketing/ticket-management/job_statuses/)
- Conteúdo de `results` por tipo de job:
  - Atualização em lote: `id`, `action`, `success` e `status` de cada item.
  - Criação em lote: `id` e `index`.
  - Exclusão permanente: um objeto com flag de sucesso.
  Fonte: [Job Statuses](https://developer.zendesk.com/api-reference/ticketing/ticket-management/job_statuses/)
- Os registros de job ficam disponíveis por um dia. Fonte: [Job Statuses](https://developer.zendesk.com/api-reference/ticketing/ticket-management/job_statuses/)
- Limite por ticket: 30 atualizações por 10 minutos, por usuário, por ticket, para qualquer PUT que atualize tickets. Há também 100 requisições por minuto por conta, ou 300 com o add-on High Volume. Fonte: [Rate limits](https://developer.zendesk.com/api-reference/introduction/rate-limits/)
- Header `zendesk-ratelimit-inflight-jobs` mostra a fila de jobs, por exemplo `total=30; remaining=29; resets=60`. Fonte: [Rate limits](https://developer.zendesk.com/api-reference/introduction/rate-limits/)
- A documentação diz que só um número limitado de jobs pode estar enfileirado ou rodando ao mesmo tempo, sem publicar o número. Fonte: snippet de busca de [Tickets](https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/)

### Inferências
- A convenção (lista de ids, `job_status` e polling) é simples de imitar. O contrato de resultado por item (`id`, `action`, `success`, `status`) é o que um cliente de migração usa para reconciliar falhas. Vale replicá-lo.
- O limite de 30 atualizações por ticket em 10 minutos não é por conta. Um cliente de migração que atualiza muitos tickets por vez pode esbarrar nele mesmo com cota de conta sobrando.

### Lacunas
- Criação unitária (`POST /api/v2/tickets`), criação em lote pela API de Tickets (`create_many`) e exclusão em lote não foram confirmados, porque o extrator não recebeu essas seções. Não tratar como fato.
- O limite exato de jobs simultâneos não foi publicado nas páginas lidas.
- Os campos exatos do `job_status` devolvido por `update_many` foram confirmados só via snippet.

## 3. Comentários e auditorias (audits)

### Conclusão
Comentários são um recurso de leitura separado. A criação acontece pelo objeto `comment` ao criar ou atualizar um ticket. Auditorias são o log de eventos de cada ticket. Não obtive a lista de tipos de evento.

### Achados com fontes
- Endpoints de comentários, só para agentes:
  - `GET /api/v2/tickets/{ticket_id}/comments`
  - `GET /api/v2/tickets/{ticket_id}/comments/count` (aproximado; acima de 100.000 é cacheado e atualizado a cada 24 horas)
  - `PUT /api/v2/tickets/{ticket_id}/comments/{ticket_comment_id}/make_private`
  Fonte: [Ticket comments](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_comments/)
- Campos do comentário:
  - Leitura: `id`, `type` (`Comment` ou `VoiceComment`), `plain_body` (sanitizado; não pode ser enviado), `attachments`, `audit_id`, `created_at`, `metadata` (inclui `flags`).
  - Escrita: `body` (Markdown só para autores agentes), `html_body` (recomendado para o Agent Workspace), `public` (`false` = nota interna), `author_id` (padrão é o usuário autenticado), `uploads` (tokens de upload).
  - `via` descreve a origem do comentário.
  Fonte: [Ticket comments](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_comments/)
- Paginação de comentários: cursor (recomendado) com `page[size]`, `page[after]`, `page[before]` e `sort` (`created_at` ou `-created_at`), ou offset com `sort_order`. Até 100 por página. Os comentários vêm em ordem crescente de criação por padrão. Fonte: [Ticket comments](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_comments/)
- Parâmetros: `include=users` traz os usuários; `include_inline_images=true` lista imagens inline como anexos. Fonte: [Ticket comments](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_comments/)
- Endpoints de auditoria:
  - `GET /api/v2/ticket_audits` (só admins; exclui tickets arquivados)
  - `GET /api/v2/tickets/{ticket_id}/audits` (agentes; aceita `filter_events`, `sort`, `sort_order` e cursor; tickets arquivados não têm paginação aqui)
  - `GET /api/v2/tickets/{ticket_id}/audits/count` (aproximado)
  - `GET /api/v2/tickets/{ticket_id}/audits/{ticket_audit_id}` (agentes)
  - `PUT /api/v2/tickets/{ticket_id}/audits/{ticket_audit_id}/make_private`
  Fonte: [Ticket audits](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_audits/)
- Objeto de auditoria: `id`, `ticket_id`, `author_id`, `created_at`, `metadata` (somente leitura), `events` (array), `via`. Fonte: [Ticket audits](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_audits/)
- Exemplos do que uma auditoria registra: mudança de valor de campo, novo comentário, tags adicionadas ou removidas, notificação enviada. Fonte: [Ticket audits](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_audits/)
- A página diz que a listagem geral de auditorias não deve ser usada para capturar mudanças, e recomenda a exportação incremental de eventos de ticket. Fonte: [Ticket audits](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_audits/)
- Escopo OAuth: segundo o extrato, os endpoints de auditoria exigem o escopo global `read`. `auditlogs:read` e `tickets:read` não funcionam. Verificar na página original. Fonte: [Ticket audits](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_audits/)

### Inferências
- Um modelo de auditoria compatível é um log somente de inserção por ticket, com lista de eventos tipados. Para sincronização, o caminho é a exportação incremental de eventos (seção 7), não a listagem de auditorias.
- Comentários têm `audit_id`, o que sugere relação de um para um entre comentário e auditoria. Não confirmei a cardinalidade para outros tipos de evento.

### Lacunas
- A lista de tipos de evento (Create, Change, Comment, Notification e outros) e os campos de cada tipo não foram obtidos. A página de auditorias remete a uma "Ticket Audit events reference" cuja URL não localizei. A URL que tentei (`https://developer.zendesk.com/api-reference/ticketing/ticket-management/ticket_audit_events/`) retornou 404.
- Não confirmei se a importação de tickets gera auditorias (ver seção 11).

## 4. Paginação, side-loading e limites de taxa

### Conclusão
Cursor é o método recomendado e não tem limite de profundidade. Offset tem teto de 100 páginas ou 10.000 recursos. Os limites de taxa variam por plano e add-on, e são separados entre Suite e Support.

### Achados com fontes
- Paginação, regras gerais:
  - Se `page[size]` for omitido, a paginação é por offset.
  - Cursor: seguir `links[next]` (que adiciona `page[after]`) até `meta[has_more]` ser falso. Máximo de 100 por página na maioria dos endpoints.
  - Offset: `page` e `per_page`. Parar quando `next_page` for null.
  - Offset tem teto de 100 páginas e 10.000 recursos. Ao exceder, responde HTTP 400.
  - Cursor não tem limite de profundidade nem de recursos.
  - Exportações incrementais e a listagem de auditorias têm variantes de cursor próprias.
  Fonte: [Pagination](https://developer.zendesk.com/api-reference/introduction/pagination/)
- Listagem de tickets: não misturar `page` com `page[...]`. Cursor usa `sort` com `updated_at`, `id` ou `status` (prefixo `-` para decrescente). Offset usa `sort_by` (`id`, `subject`, `deleted_at`, `created_at`, `updated_at`, `status`, `requester`, `requester.name`, `group`, `assignee`, `assignee.name`) e `sort_order`. Fonte: [Tickets](https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/)
- Parâmetros de listagem de tickets também incluem `external_id`, `include` (side-loads) e `support_type_scope` (`all`, `agent`, `ai_agent`; padrão `agent`). Fonte: [Tickets](https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/)
- Limites de conta, em requisições por minuto (a página separa Suite e Support):
  - Essential (legado): Support 10.
  - Team: Suite 200, Support 200.
  - Growth: Suite 400; Support não se aplica.
  - Professional: Suite 400, Support 400.
  - Enterprise: Suite 700, Support 700.
  - Enterprise Plus: Suite 2.500; Support não se aplica.
  - Add-on High Volume: 2.500 para Suite e Support. Exige Suite Growth ou superior, ou Support Professional ou superior, com mínimo de 10 agentes. O add-on substitui o limite do plano; não soma a ele.
  - Help Center tem limite separado do Support.
  Fonte: [Rate limits](https://developer.zendesk.com/api-reference/introduction/rate-limits/)
- Limites por endpoint, na mesma página:
  - Listagem de tickets por offset com `page` acima de 500: 50 por minuto.
  - Exportar views: 100.000 por hora.
  - Executar view: 5 por minuto, por view e por agente.
  - Eventos incrementais de side conversation: 600 a cada 10 minutos.
  - Criar ou responder side conversation: 300 a cada 10 minutos.
  - Exportação de busca: 100 por minuto.
  - Exportações incrementais: 10 por minuto (30 com High Volume).
  Fonte: [Rate limits](https://developer.zendesk.com/api-reference/introduction/rate-limits/)
- Cabeçalhos: `X-Rate-Limit` mostra o limite e as requisições restantes no minuto (nas APIs de ticketing aparece em minúsculo, `x-rate-limit`). `Retry-After` vem com 429 e indica a espera em segundos. Fonte: [Rate limits](https://developer.zendesk.com/api-reference/introduction/rate-limits/)

### Inferências
- Um cliente de migração precisa tratar 429 com `Retry-After` e controlar a concorrência. O gargalo para sincronização contínua é o limite de 10 por minuto das exportações incrementais, por isso a exportação por cursor com `per_page` de 1.000 é a forma eficiente.
- O modelo "limite por plano mais add-on" pode ser reproduzido por configuração, sem valores fixos no código.

### Lacunas
- Não detalhei limites por plano para endpoints de tickets além dos limites gerais de conta.
- Não extraí a lista de valores de `include` aceitos por endpoint, exceto `users` nos comentários e `last_audits` (que não é suportado em endpoints incrementais; ver seção 7).

## 5. Requests API (perspectiva do usuário final)

### Conclusão
Não pesquisei esta seção.

### Achados com fontes
- Nenhum. Não acessei a referência de Requests nem comparei com a API de tickets.

### Inferências
- Nenhuma confirmada.

### Lacunas
- Pendente: referência de Requests (solicitações do usuário final, endpoints sob `/api/v2/requests`) e diferenças em relação à API de tickets. Não consultei por causa do limite de chamadas de pesquisa, que as páginas de Tickets consumiram.

## 6. Search API e sintaxe de busca

### Conclusão
A Search API tem paginação por offset com teto de 1.000 resultados por consulta. A exportação usa cursor, aceita até 1.000 por página e ordena só por `created_at`. A sintaxe é a da busca de tickets da Central de Ajuda.

### Achados com fontes
- Endpoints, só para agentes:
  - `GET /api/v2/search?query=`
  - `GET /api/v2/search/count?query=` (devolve só a contagem)
  - `GET /api/v2/search/export?filter[type]=...&query=`
  Fonte: [Search](https://developer.zendesk.com/api-reference/ticketing/ticket-management/search/)
- Busca: `sort_by` (`updated_at`, `created_at`, `priority`, `status`, `ticket_type`; padrão é relevância) e `sort_order` (padrão `desc`). Até 1.000 resultados, 100 por página, só offset. Pedir a página 11 com 100 por página retorna 422. Fonte: [Search](https://developer.zendesk.com/api-reference/ticketing/ticket-management/search/)
- Exportação: `filter[type]` é obrigatório (`ticket`, `organization`, `user`, `group`). Colocar o tipo na query causa erro. Paginação por cursor com `page[size]` e `page[after]`, máximo de 1.000 por página. A Zendesk recomenda 100, porque conjuntos grandes com tickets arquivados podem ser lentos ou dar timeout. Ordem só por `created_at`. Cursores expiram em uma hora. Fonte: [Search](https://developer.zendesk.com/api-reference/ticketing/ticket-management/search/)
- Limites de taxa de busca: 2.500 por minuto por conta, para planos padrão e o add-on High Volume, medidos pelo cabeçalho `Zendesk-RateLimit-search-index`. Exportação: 100 por minuto por conta. Fonte: [Search](https://developer.zendesk.com/api-reference/ticketing/ticket-management/search/). A página de rate limits lista só a exportação (100 por minuto). Fonte: [Rate limits](https://developer.zendesk.com/api-reference/introduction/rate-limits/)
- Sintaxe, na Central de Ajuda:
  - `:` é igualdade (`status:open`). Os operadores `<`, `>`, `<=` e `>=` não levam espaços (`updated<2025-07-04`).
  - Aspas fazem busca de frase. `-` exclui um termo (`status:pending -tags:invoice`).
  - `*` é curinga, mas só depois de uma palavra-chave (`subject:photo*`).
  Fonte: [Zendesk search reference](https://support.zendesk.com/hc/en-us/articles/4408886879258-Zendesk-search-reference)
- Palavras-chave de ticket:
  - `status`: `new`, `open`, `pending`, `hold`, `solved`, `closed` (exemplo: `status<closed`).
  - `ticket_type`: `question`, `incident`, `problem`, `task`.
  - `assignee`, `requester`, `submitter`, `commenter`, `cc`: aceitam `none`, `me`, nome, e-mail, id ou telefone (exemplo: `submitter:me`).
  - `tags`: vários valores da mesma palavra-chave funcionam com OR (`tags:important tags:urgent`). Valor entre aspas exige que todas as palavras batam (`tags:"important urgent"`).
  - `created`, `updated`, `solved`, `due_date`: buscas de data e hora.
  - `custom_field_{id}`: campo customizado pelo id numérico (exemplo: `custom_field_455214213:shoes`).
  - `type`: limita a um tipo (`ticket`, `user`, `organization`, `group`). Sem ele, os resultados incluem tickets (por exemplo, `organization:customers` também traz tickets dos solicitantes da organização).
  Fonte: [Zendesk search reference](https://support.zendesk.com/hc/en-us/articles/4408886879258-Zendesk-search-reference)
- Datas: formato `YYYY-MM-DD` (também aceita formato local como `MM/DD/YYYY`). Data com hora usa ISO 8601 (`created>2015-09-01T12:00:00-08:00`). Intervalo usa duas condições (`created>2014-08-01 created<2014-08-05`). Tempo relativo usa unidades como `created>4hours`. Fonte: [Zendesk search reference](https://support.zendesk.com/hc/en-us/articles/4408886879258-Zendesk-search-reference)
- Ordenação na busca da interface: `order_by:` com `sort:asc` ou `sort:desc`. Campos: `created`, `commented`, `priority`, `status`, `ticket_type`. Eles mapeiam para `sort_by` e `sort_order` na API. Fonte: [Zendesk search reference](https://support.zendesk.com/hc/en-us/articles/4408886879258-Zendesk-search-reference)
- Limites: uma consulta tem até 64 palavras. A palavra-chave `comment` busca só nos primeiros 500 comentários do ticket. O artigo não menciona o teto de 1.000 resultados. Fonte: [Zendesk search reference](https://support.zendesk.com/hc/en-us/articles/4408886879258-Zendesk-search-reference)

### Inferências
- A sintaxe é uma linguagem pequena e analisável, com tokens `chave:valor` e `chave<valor`. Dá para reproduzir o subconjunto usado em migração (`status`, `assignee`, `tags`, `created`/`updated`, `custom_field_{id}`).
- Para migração, a exportação de busca (cursor, até 1.000 por página, 100 por minuto) é melhor que varrer a busca por offset, que para em 1.000 resultados. Não confirmei se a exportação tem teto total.
- `custom_field_{id}` usa ids numéricos do Zendesk. Por isso a migração precisa de tabela de mapeamento de campos customizados.

### Lacunas
- Busca unificada entre tipos, como produto ou endpoint próprio: não encontrei página dedicada. Confirmei só `type` e `filter[type]`.
- Teto total de resultados da exportação de busca: não publicado nas páginas lidas.
- Parâmetros `page` e `per_page` da busca: não aparecem na tabela de parâmetros. Só aparecem no texto sobre limites.
- O exemplo `type:ticket` não aparece no extrato da página de Search. A palavra-chave `type` está documentada no artigo de ajuda.

## 7. Exportações incrementais

### Conclusão
Exportações incrementais são o caminho oficial para sincronização. A versão por cursor é a recomendada, `end_of_stream` sinaliza o fim, e o limite é de 10 requisições por minuto. A versão por tempo existe, mas é menos consistente.

### Achados com fontes
- Endpoints:
  - Tickets por cursor: `GET /api/v2/incremental/tickets/cursor`
  - Tickets por tempo: `GET /api/v2/incremental/tickets?start_time=`
  - Eventos de tickets: `GET /api/v2/incremental/ticket_events?start_time=`
  - Usuários por cursor: `GET /api/v2/incremental/users/cursor`
  - Usuários e organizações por tempo.
  - Métricas de eventos, registros de objetos customizados e artigos têm documentação em outras páginas.
  Fonte: [Incremental exports](https://developer.zendesk.com/api-reference/ticketing/ticket-management/incremental_exports/)
- `end_of_stream` (booleano) vem em toda resposta. `true` significa que os resultados chegaram até o momento atual. `false` significa que ainda há mais. Fonte: [Incremental exports](https://developer.zendesk.com/api-reference/ticketing/ticket-management/incremental_exports/)
- Paginação por cursor: `after_url`, `after_cursor`, `before_url`, `before_cursor`. `start_time` só vale na primeira requisição; as seguintes usam `cursor`. Paginação por tempo: `end_time` (vira o próximo `start_time`), `next_page`, `count`. Fonte: [Incremental exports](https://developer.zendesk.com/api-reference/ticketing/ticket-management/incremental_exports/)
- `start_time` é Unix epoch e precisa estar há mais de um minuto no passado. Tickets e eventos não retornam dados do último minuto. Fonte: [Incremental exports](https://developer.zendesk.com/api-reference/ticketing/ticket-management/incremental_exports/)
- `per_page`: padrão e máximo de 1.000. Fonte: [Incremental exports](https://developer.zendesk.com/api-reference/ticketing/ticket-management/incremental_exports/)
- Na exportação por tempo, itens com o mesmo timestamp podem fazer uma página passar de 1.000. A exportação por cursor evita isso. Fonte: [Incremental exports](https://developer.zendesk.com/api-reference/ticketing/ticket-management/incremental_exports/)
- Na exportação por tempo de tickets, o filtro compara `start_time` com `generated_timestamp`. Por isso, pode devolver tickets com `updated_at` anterior ao `start_time`. Fonte: [Incremental exports](https://developer.zendesk.com/api-reference/ticketing/ticket-management/incremental_exports/)
- Limites: endpoints incrementais têm 10 requisições por minuto (30 com o add-on High Volume). Fonte: [Rate limits](https://developer.zendesk.com/api-reference/introduction/rate-limits/). O endpoint de usuários por cursor tem limite próprio de 20 por minuto, ou 60 com High Volume. Fonte: [Incremental exports](https://developer.zendesk.com/api-reference/ticketing/ticket-management/incremental_exports/). Respostas 429 trazem `Retry-After`.
- Modo de amostra: até 50 resultados por requisição, para conferir o formato antes da exportação completa. Fonte: [Incremental exports](https://developer.zendesk.com/api-reference/ticketing/ticket-management/incremental_exports/)
- `exclude_deleted=true` remove tickets excluídos da resposta. `last_audits` não é suportado em endpoints incrementais. Fonte: [Incremental exports](https://developer.zendesk.com/api-reference/ticketing/ticket-management/incremental_exports/)
- A página recomenda a exportação por cursor, por ter desempenho e tamanho de resposta mais consistentes. Fonte: [Incremental exports](https://developer.zendesk.com/api-reference/ticketing/ticket-management/incremental_exports/)

### Inferências
- Para reproduzir isso no Chatwoot, o contrato importante é `end_of_stream` mais `after_cursor`. A chave de mudança também importa: a exportação por tempo usa `generated_timestamp`, não `updated_at`. Vale documentar a semântica e usar um campo monotônico equivalente.
- Aritmética a partir dos números citados: sincronizar 1 milhão de tickets com 1.000 por página são cerca de 1.000 requisições. A 10 por minuto, isso leva cerca de 100 minutos, sem contar as requisições de outros endpoints.

### Lacunas
- Os tipos de evento retornados por `ticket_events` não foram extraídos.
- Limites e detalhes da exportação de usuários por tempo e de organizações não foram detalhados.
- Métricas de eventos e artigos estão fora do que li.
- Não encontrei confirmação de depreciação das exportações por `start_time`. A página só recomenda cursor.

## 8. Webhooks (assinatura de evento versus gatilho)

### Conclusão
Webhooks são objetos de API com destino, método, formato e lista de `subscriptions`. Para disparar a partir de gatilhos ou automações, a assinatura usa `conditional_ticket_events`. Não confirmei o catálogo de eventos nem o esquema de assinatura.

### Achados com fontes
- Campos obrigatórios do objeto: `endpoint`, `http_method`, `name`, `request_format`, `status`. Opcionais: `authentication`, `custom_headers`, `description`, `external_source`, `signing_secret`, `subscriptions`. Somente leitura: `id`, `created_at`, `created_by`, `updated_at`, `updated_by`. Fonte: [Webhooks API](https://developer.zendesk.com/api-reference/webhooks/webhooks-api/webhooks/)
- Para assinatura de eventos: `http_method` deve ser `POST`. `request_format` deve ser `json` (alternativas: `xml`, `form_encoded`). `status` é `active` ou `inactive`. Fonte: [Webhooks API](https://developer.zendesk.com/api-reference/webhooks/webhooks-api/webhooks/)
- Endpoints:
  - `GET /api/v2/webhooks` (filtros por nome e status, paginação e ordenação)
  - `POST /api/v2/webhooks` (clonagem com `clone_webhook_id`)
  - `POST /api/v2/webhooks/test` (aceita `webhook_id` para testar um webhook existente)
  - `GET /api/v2/webhooks/{webhook_id}`
  - Atualização, exclusão, invocações e reset do signing secret aparecem no índice da página, mas o detalhe não foi extraído.
  Fonte: [Webhooks API](https://developer.zendesk.com/api-reference/webhooks/webhooks-api/webhooks/)
- Para vincular a um gatilho ou automação, o array `subscriptions` recebe só `conditional_ticket_events`. Fonte: [Webhooks API](https://developer.zendesk.com/api-reference/webhooks/webhooks-api/webhooks/)
- O formato do nome de evento (um exemplo seria `zen:event-type:ticket.created`) não aparece no extrato. A página remete a uma referência de tipos de evento. Fonte: [Webhooks API](https://developer.zendesk.com/api-reference/webhooks/webhooks-api/webhooks/)
- Verificação de assinatura: a página `https://developer.zendesk.com/documentation/webhooks/verifying-webhooks/` retornou 404 para o caminho tentado. Nada confirmado.

### Inferências
- Há dois modelos a espelhar. (a) Assinatura de evento, com `subscriptions` listando tipos de evento, que serve à sincronização de dados. (b) Disparo por gatilho ou automação, com `conditional_ticket_events`, que é lógica de negócio do cliente.
- O objeto tem `signing_secret`, então a assinatura depende de segredo por webhook. O algoritmo e os headers não foram confirmados.

### Lacunas
- Catálogo completo de tipos de evento (ticket, usuário, organização) não extraído.
- Esquema de assinatura (headers e algoritmo): não confirmado, porque a página de verificação retornou 404.
- Detalhes de atualização, exclusão e invocações: não extraídos.
- Eventos de usuário e de organização: não confirmados.

## 9. Custom Objects (legado versus novo) e Sunshine

### Conclusão
Não obtive fonte verificada. Esta seção fica em aberto.

### Achados com fontes
- Nenhum. A página `https://developer.zendesk.com/api-reference/custom-data/custom-objects-api/introduction/` retornou 404 para o caminho tentado.

### Inferências
- Nenhuma confirmada.

### Lacunas
- Pendente: diferença entre custom objects legados e novos, tipo de campo `lookup`, endpoints sob `/api/v2/custom_objects` e o produto Sunshine. Nenhum desses pontos foi verificado nesta pesquisa.

## 10. Zendesk Apps Framework (ZAF)

### Conclusão
Não obtive fonte verificada para o ZAF. Localizações, API de cliente e eventos de ticket ficam em aberto.

### Achados com fontes
- A página `https://developer.zendesk.com/apps/docs/developer-guide/location` retornou 404 para o caminho tentado. Nada confirmado.
- As localizações citadas no pedido (`ticket_sidebar`, `nav_bar`, `top_bar`, `new_ticket_sidebar`) não foram verificadas.

### Inferências
- Nenhuma confirmada.

### Lacunas
- Pendente: lista oficial de localizações; API de cliente do ZAF para ler e escrever campos de ticket; hooks de eventos de ticket (como `ticket.save`); manifesto do app; e a exigência de token OAuth global para apps distribuídos a vários clientes (ver seção 12). A solução é provavelmente encontrar outra URL no portal de desenvolvedores.

## 11. Import API e migração a partir do Zendesk

### Conclusão
A Import API é o caminho oficial para trazer tickets históricos com timestamps. Ela tem efeitos colaterais conhecidos sobre gatilhos, SLAs e notificações. Não consultei ferramentas de migração de terceiros.

### Achados com fontes
- Endpoints, só para admins:
  - `POST /api/v2/imports/tickets` (um ticket)
  - `POST /api/v2/imports/tickets/create_many` (até 100 tickets; devolve `job_status` e enfileira um job)
  Fonte: [Ticket import](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_import/)
- `archive_immediately` (booleano, padrão `false`): tickets criados com status `closed` vão direto para o arquivo, sem o ciclo de vida normal. Fonte: [Ticket import](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_import/)
- Campos confirmados: `solved_at`, `updated_at` e `created_at` podem ser definidos. Comentários aceitam `value`, `body` ou `html_body` e `created_at`. Anexos sobem antes, e o token vai nos parâmetros do comentário. Fonte: [Ticket import](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_import/)
- A página diz que a importação aceita "as propriedades normais do ticket" da referência de Tickets. O extrato não mostra o corpo completo dos exemplos, então `requester_id`, `submitter_id`, `assignee_id`, `tags` e `custom_fields` não foram confirmados diretamente. Fonte: [Ticket import](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_import/)
- Timestamps: `created_at` e `updated_at` anteriores a 1970 são arredondados para 1970. `created_at` de comentário não pode ser anterior a 1970 nem estar no futuro. Fonte: [Ticket import](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_import/)
- Efeitos colaterais:
  - Gatilhos não rodam em tickets importados com status diferente de `closed`. Eles voltam a rodar se o ticket for atualizado depois.
  - Métricas e SLAs não são suportados em tickets importados. A Zendesk recomenda marcar os tickets importados com tag e excluí-los dos relatórios.
  - Nenhuma notificação é enviada aos usuários em cópia na importação.
  Fonte: [Ticket import](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_import/)
- Limite de lote: 100 tickets por `create_many`. Limite de taxa não citado na página. Fonte: [Ticket import](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_import/)
- A página não diz se auditorias são criadas ou suprimidas na importação. Fonte: [Ticket import](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_import/)

### Inferências
- Um migrador deve importar como `closed` sempre que possível, para não disparar gatilhos. Deve gravar `created_at` e `solved_at` históricos, e marcar os tickets com uma tag de origem para filtrar relatórios.
- Inferência: `requester_id`, `submitter_id` e `assignee_id` exigem usuários já existentes no destino. A ordem de migração deve ser usuários, organizações, campos, tickets e depois comentários e anexos. Isso não foi confirmado em fonte oficial.
- Para o Chatwoot, a importação com timestamps sem disparar automações é um requisito de design a planejar. Não verifiquei se já existe equivalente no código.

### Lacunas
- Documentação de Help Desk Migration e Import2 não consultada. Mapeamento de entidades (agentes, grupos, macros, campos) continua em aberto.
- Ordem e dependências de migração não extraídas de fonte oficial.
- Não confirmado se a importação gera auditorias.
- Limite de taxa específico da importação não confirmado.

## 12. Autenticação

### Conclusão
OAuth com Bearer é o método recomendado. O token de API, com Basic e formato `email/token`, está marcado como depreciado. Os escopos OAuth detalhados não foram extraídos desta página.

### Achados com fontes
- OAuth access token (recomendado): `Authorization: Bearer {access_token}`. Tem até 184 caracteres. Cada token só funciona na instância Zendesk do cliente OAuth que o criou. Fonte: [Security and auth](https://developer.zendesk.com/api-reference/introduction/security-and-auth/)
- Global OAuth access token: obrigatório para apps e integrações distribuídos a vários clientes Zendesk. Tokens comuns não são aceitos nesse caso. Não é exigido para uso interno. Fonte: [Security and auth](https://developer.zendesk.com/api-reference/introduction/security-and-auth/)
- Token de API (depreciado): Basic com `{email_address}/token:{api_token}` em base64, enviado como `Authorization: Basic {base64}`. Na transmissão HTTP, a barra de `{email}/token` vira `%2F`. Admins podem ter até 256 tokens, ou 2.048 em contas que já passavam desse limite. Fonte: [Security and auth](https://developer.zendesk.com/api-reference/introduction/security-and-auth/)
- Tokens de API agem como senha e podem se passar por qualquer usuário, inclusive admin. A página recomenda excluir os não usados. Fonte: [Security and auth](https://developer.zendesk.com/api-reference/introduction/security-and-auth/)
- CORS no cliente só funciona com OAuth, não com token de API. Fonte: [Security and auth](https://developer.zendesk.com/api-reference/introduction/security-and-auth/)
- TLS 1.2 com SNI é exigido. TLS 1.0 e 1.1 foram removidos em junho de 2018. Fonte: [Security and auth](https://developer.zendesk.com/api-reference/introduction/security-and-auth/)
- Autenticação de usuário final: em instâncias abertas, alguns endpoints não exigem autenticação. Em instâncias fechadas, e-mail e senha funcionam se o admin habilitar. Fonte: [Security and auth](https://developer.zendesk.com/api-reference/introduction/security-and-auth/)

### Inferências
- Clientes de migração costumam aceitar Bearer (OAuth) e Basic com token. Se a meta for trocar só a URL base de um cliente Zendesk, a API própria teria de aceitar o formato `{email}/token`. Isso é inferência do objetivo, não do Zendesk.

### Lacunas
- Lista de escopos OAuth (`read`, `write`, `tickets:read`, `tickets:write` e outros) não extraída. A página de diferenças entre token de API e OAuth, linkada no texto, não foi aberta.
- Não encontrei datas de 2025 ou 2026 nesta página, então mudanças recentes de autenticação não estão confirmadas.

## 13. Modelo de dados e diagramas

### Conclusão
Não encontrei diagrama oficial de entidades nas páginas consultadas. As relações abaixo foram inferidas a partir dos campos de ticket.

### Achados com fontes
- Campos de ticket que apontam para outras entidades:
  - Usuários: `requester_id`, `submitter_id`, `assignee_id`, `collaborator_ids`, `follower_ids`, `email_cc_ids`.
  - Organização: `organization_id`. Grupo: `group_id`. Marca: `brand_id`. Formulário: `ticket_form_id` (Enterprise).
  - Tickets: `problem_id` e `has_incidents` (problema e incidente), `followup_ids` (follow-ups).
  Fonte: [Tickets](https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/)
- Auditoria aponta para ticket e autor (`ticket_id`, `author_id`). Comentário aponta para autor e auditoria (`author_id`, `audit_id`). Fontes: [Ticket audits](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_audits/) e [Ticket comments](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_comments/)
- Job status referencia tarefas por id e índice em `results`. Fonte: [Job Statuses](https://developer.zendesk.com/api-reference/ticketing/ticket-management/job_statuses/)

### Inferências
- Modelo mínimo para compatibilidade, reconstruído a partir dos campos (não é diagrama oficial):
  - Ticket tem muitos Comment, e Comment pode ter uma Audit.
  - Ticket tem muitos AuditEvent.
  - Ticket se relaciona com User (requester, submitter, assignee), Organization, Group, Brand, e com Problem ou Incident.
- Para o Chatwoot, a conversa corresponde ao ticket, e a mensagem corresponde ao comentário. A distinção `public` (nota interna ou pública) precisa de mapeamento explícito para o equivalente de mensagem privada do Chatwoot. Não verifiquei esse ponto no schema de mensagens.

### Lacunas
- Diagrama oficial de entidades (ERD) não encontrado.
- Modelos de usuário, organização, grupo e marca: não extraídos.
- Modelo de Custom Objects e relações lookup: ver seção 9.
- Pendentes para uma próxima rodada, na ordem de prioridade: (1) lista de tipos de evento de auditoria; (2) criação de tickets e `create_many` pela API de Tickets; (3) assinatura de webhooks e catálogo de eventos; (4) ZAF; (5) Custom Objects; (6) Requests API; (7) documentação de Help Desk Migration e Import2. Também vale abrir a OpenAPI (https://developer.zendesk.com/zendesk/oas.yaml) para conferir todos os campos citados aqui.
