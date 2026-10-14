# Regras de negócio e SLA do Zendesk Support (estado em 2026)

Pesquisa realizada em 2026-10-13, para replicação no fork Chatwoot (Rails + Vue). Cobre gatilhos (triggers), automações, views, macros, políticas de SLA, horários comerciais (schedules) e placeholders.

**Método e limites.** Foram usadas 15 chamadas de ferramenta. As fontes oficiais foram lidas por WebFetch. Algumas páginas vieram truncadas ou sem os trechos pedidos, e isso está registrado em Gaps. Quando a informação veio só de blog de terceiros, está marcada como "secundário". Nomes de interface estão em inglês entre aspas, como aparecem no Zendesk. "Legado" marca o que a própria documentação indica como substituído. Citações em português são traduções livres, exceto quando indicado.

**Fontes oficiais lidas:**
- Ticket trigger conditions and actions reference: https://support.zendesk.com/hc/en-us/articles/4408893545882-Ticket-trigger-conditions-and-actions-reference
- Automation conditions and actions reference: https://support.zendesk.com/hc/en-us/articles/4408885654298-Automation-conditions-and-actions-reference
- Artigo sobre triggers (ciclo, fechamento, limites): https://support.zendesk.com/hc/en-us/articles/203662246
- Triggers API: https://developer.zendesk.com/api-reference/ticketing/business-rules/triggers/
- SLA Policies API: https://developer.zendesk.com/rest_api/docs/core/sla_policies
- Macros API: https://developer.zendesk.com/api-reference/ticketing/business-rules/macros/
- Views API: https://developer.zendesk.com/api-reference/ticketing/business-rules/views/
- Object trigger conditions (apenas referenciado, não lido): https://support.zendesk.com/hc/en-us/articles/7313293784218

**Fontes secundárias (usadas só como pista, não normativas):**
- eesel.ai, visão geral de business rules: https://www.eesel.ai/blog/zendesk-business-rules-overview-and-setup
- eesel.ai, SLA com calendário e horário comercial: https://www.eesel.ai/blog/zendesk-sla-calendar-business-hours
- eesel.ai, horário comercial: https://www.eesel.ai/blog/zendesk-business-hours
- eesel.ai, condições baseadas em horário de agendamento: https://eesel.ai/blog/zendesk-automation-schedule-based-conditions
- getmacha, business rules: https://www.getmacha.com/blog/zendesk-business-rules-explained
- getmacha, SLA: https://www.getmacha.com/blog/zendesk-sla-explained

---

## Gatilhos (triggers)

### Takeaway
Triggers são regras disparadas por evento (criação ou atualização de ticket). Elas são avaliadas logo após o evento, com condições em dois grupos (`all` = E, `any` = OU) e ações que alteram o ticket ou notificam. Triggers de ticket são percorridos em ordem de `position`, e as ações de um podem afetar os seguintes (encadeamento). A documentação lida não confirma a regra de "um disparo por ciclo" nem o limite de ciclos.

### Cited Findings

**Timing e ordem de avaliação**
- "Triggers always run, or check the conditions, immediately after the qualifying event happens." — [Artigo sobre triggers](https://support.zendesk.com/hc/en-us/articles/203662246)
- Todos os triggers de ticket são verificados do primeiro ao último a cada criação ou atualização. A ordem importa porque as ações de um trigger podem afetar outro. Novos triggers entram por último por padrão. O campo `position` controla a ordem de execução. — [Triggers API](https://developer.zendesk.com/api-reference/ticketing/business-rules/triggers/)
- Encadeamento: "Actions applied by one ticket trigger can affect how other triggers run and fire for a ticket." Outros tipos de trigger (chat, messaging, sales) rodam simultaneamente, "without this looping behavior". — [Artigo sobre triggers](https://support.zendesk.com/hc/en-us/articles/203662246)
- Mudanças que automações fazem no ticket podem disparar triggers. — [Artigo sobre triggers](https://support.zendesk.com/hc/en-us/articles/203662246)
- Triggers de ticket não rodam nem disparam em tickets fechados. Podem disparar no momento em que o ticket está sendo marcado como fechado, mas não quando o sistema fecha automaticamente após 28 dias. — [Artigo sobre triggers](https://support.zendesk.com/hc/en-us/articles/203662246)
- Limite de tamanho: triggers, como todos os business rules, devem ter menos de 65 KB. — [Artigo sobre triggers](https://support.zendesk.com/hc/en-us/articles/203662246)
- Não há regra de "nullifying condition" documentada para triggers nas fontes lidas. A exigência documentada é para automações.

**Lógica de condições**
- Condições ficam em dois grupos: "meet ALL" (`all`, todas devem ser verdadeiras) e "meet ANY" (`any`, basta uma). Triggers de ticket podem misturar os dois grupos. — [Artigo sobre triggers](https://support.zendesk.com/hc/en-us/articles/203662246); [Triggers API](https://developer.zendesk.com/api-reference/ticketing/business-rules/triggers/)

**Condições de ticket (lista oficial resumida)** — [Ticket trigger conditions](https://support.zendesk.com/hc/en-us/articles/4408893545882-Ticket-trigger-conditions-and-actions-reference)
- Evento, "Ticket > Ticket": `Created` (só em ticket novo; para AI agent, quando escalado a humano) ou `Updated` (a cada modificação submetida).
- Comentário, "Ticket > Comment": `Public`, `Private`, `Present` (público ou privado), `Present and requester can see`. Em mensageria, o comentário só conta como público se a transcrição for pública.
- "Ticket > Comment text": operadores "contains at least one word", "contains none of the words", "contains the string", "does not contain the string". Não diferencia maiúsculas. Em ticket novo, cai para o subject se o primeiro comentário não bater. Atualização sem comentário avalia um comentário vazio.
- "Ticket > Subject text": inclui "present" e "not present". Fica indisponível se o campo Subject estiver desativado.
- "Ticket > Update via": mesmas fontes de "Channel". Autoreplies não são identificáveis de forma confiável. Respostas do Agent Workspace e da interface padrão registram como `Web`, mesmo quando aparecem como Email. Atualizações em massa pela interface Support registram como `Web Services (API)`.
- "Ticket > Channel", "Channel name", "Integration account", "Received at". Esta última casa só endereços válidos do Zendesk (listas do Google e aliases podem não casar) e não checa canal, então pode casar com tickets que não são de email.
- "Ticket > Current user" (agente, end user ou agente específico). Não se aplica a tickets criados por voicemail nem por canal de mensageria.
- "Ticket > Assignee" (sem valor, requester, agente). "Ticket > Group" (sem grupo ou nome). Em views, ambos aceitam "current user" e "current user's group(s)". — [Ticket trigger conditions](https://support.zendesk.com/hc/en-us/articles/4408893545882-Ticket-trigger-conditions-and-actions-reference)
- "Ticket > Priority": Low, Normal, High, Urgent. Aceita comparação de maior e menor.
- "Ticket > Status" e "Ticket > Status category": New, Open, Pending, On-hold, Solved, Closed. Aceitam maior e menor. Quando status customizados estão ativos, as condições de status existentes são convertidas em condições de categoria. Tratar a forma "Status" como legado nesse cenário.
- "Ticket > Ticket status": lista de status de sistema ou customizados (contém ao menos um / não contém nenhum).
- "Ticket > Tags": contém ao menos uma / não contém nenhuma das tags listadas.
- Campos customizados: checagem de presença para todos os tipos. Campos de data usam dias corridos. Dropdown e lookup: "is" ou "isn't set". Multi-select: valores específicos selecionados ou não.
- "Ticket > CC": verifica se existem CCs no momento do disparo. Não verifica followers nem @mentions. Não suporta CCs legados.
- "Ticket > Satisfaction": Unoffered, Offered, Bad, Bad with comment, Good, Good with comment. Não disponível em plano Team.
- "Ticket > Type" (Question, Incident, Problem, Task), "Ticket > Privacy" (tem comentários públicos ou não tem), "Ticket > Attachment" (anexo na atualização; anexos inline de macro são excluídos), "Ticket > Due date", "Ticket > Number of incidents", "Ticket > Reopens" (contagem de Solved para Open/Pending; não Team), "Ticket > Assignee stations" e "Ticket > Group stations" (quantos agentes ou grupos distintos já tiveram o ticket; não Team), "Ticket > Agent replies" (não Team), "Ticket > Brand" (não Team), "Ticket > Form" (Growth e acima, ou Support Enterprise), "Ticket > Service catalog form", "Ticket > Routing channel" (omnichannel e mensageria/voz).
- Side conversations ("Ticket > Side conversation": Is Created, Is Closed, Is Replied to, Is Reopened; não Team). Aplicam-se ao ticket pai.
- Horário (ver seção Horários): "Within business hours?" (não Team), "On a holiday?" (Enterprise), "Within (schedule)" (Enterprise), "Ticket > Schedule" (Enterprise).
- Mensageria e IA: "Messaging session state", "Messaging session ended reason" (requer encerramento de sessão), "Messaging session transcript" (requer transcrição). Predições de IA (Intent, Language, Sentiment e suas confidências) exigem o add-on Copilot e não funcionam com `Created`.
- Outras: "Ticket sharing" (Sent to / Received from), "Lookup relationships" (registros de objetos customizados).
- Requester (condições): registro, idioma, papel (agent, admin, end-user e light agent se usado), fuso horário, campos customizados de usuário, "Verified by X Corp", número de seguidores e de tweets do X. — [Ticket trigger conditions](https://support.zendesk.com/hc/en-us/articles/4408893545882-Ticket-trigger-conditions-and-actions-reference)

**Ações de trigger (Set / Add / Remove)** — [Ticket trigger actions](https://support.zendesk.com/hc/en-us/articles/4408893545882-Ticket-trigger-conditions-and-actions-reference)
- Atribuição: "Assignee" (sem valor, requester, agente específico; triggers e macros também "current user"). "Group" (define ou remove; macros também aceitam grupos do usuário atual).
- Status e campos de ticket: "Priority", "Type", "Status" (New a Closed; `Solved` é aplicado mesmo com campos obrigatórios vazios, e o fechamento fica para automações), "Status category" (aplica o status padrão da categoria), "Ticket status" (system ou custom).
- Tags: "Add tags" e "Remove tags" (separadas por espaço). "Set tags" substitui todas as tags, inclusive as ligadas a campos de ticket.
- Campos: "Custom fields" (checkbox, dropdown, texto, número, data; data usa dias corridos), "Requester > Language", "Requester > Custom fields", "Organization > Custom fields" (não dispara se o ticket não tem organização), "Lookup relationship fields".
- Seguidores e CCs: "Add follower" substitui "Add CC" quando o modelo atualizado de CCs/followers está ativo. "Add CC" é legado.
- Comentários: "Internal note". "Autoreply" (adiciona comentário público; suprimido se o assignee não pode comentar publicamente, como light agents).
- Satisfação: "Satisfaction" oferecida ao requester (não funciona com mensageria).
- Outros: "Form" (Growth e acima, ou Support Enterprise), "Brand" (não Team), "Set schedule" (Enterprise), "Share ticket with" (Enterprise; exige acordo de compartilhamento), "Redact" (add-on Advanced Data Privacy; remove tipos de PII de comentários; exige sugestões de redação), "Set routing channel" (trata conversa ou chamada como ticket de email; consome capacidade de email; não combinar com encerramento de sessão de mensageria), "Messaging session" (encerra a sessão; só mensageria), "Set skills" e "Add skills" (omnichannel).
- Side conversations: "Side conversation via email" e "Side conversation via child ticket" (não Team; exigem o recurso habilitado). Ambas suprimem a condição "Side conversation Is Created". A variante por child ticket não aplica campos padrão de child ticket e, se o pai não tiver assignee, o requester do child vira o System User do Zendesk.

**Ações de notificação** — [Ticket trigger actions](https://support.zendesk.com/hc/en-us/articles/4408893545882-Ticket-trigger-conditions-and-actions-reference)
- "Active webhook": seleciona o webhook. Trocar o destino reseta o corpo do texto.
- "External target": seleciona um target externo de email. Trocar o destino reseta o corpo do texto.
- "Group email" e "User email": destinatários de grupo ou usuário (requester, assignee, usuário nomeado; em triggers e automações também current user, todos os agentes não restritos, e "requester and CCs"). Só envia se a atualização tiver comentário público. Com CCs ativos e envio só ao requester, o email do requester é omitido do comentário. Não envia ao próprio autor da atualização quando usa "requester and CCs".
- "Zendesk integration" (notifica usuários do Slack via integração Slack for Zendesk Support).
- "Tweet" (responde ao requester no X; inclui @mention e URL encurtada, então é preciso respeitar o limite de caracteres).
- "Group text" e "User text" (notificações Zendesk Text).
- "Request messaging satisfaction survey" (envia CSAT ao fim da conversa).
- "Autoreply with articles" (sugestões de artigos da central de ajuda, por email) e "Autoreply using generative AI" (só email, só como parte de um AI agent no canal email, não isolado).

**Semântica de condições** — [Ticket trigger conditions](https://support.zendesk.com/hc/en-us/articles/4408893545882-Ticket-trigger-conditions-and-actions-reference)
- Assignee, Group e Status disparam em qualquer mudança, inclusive quando o primeiro valor é definido.
- `Ticket > Ticket "Created"` dispara uma única vez, na criação. `"Updated"` dispara a cada modificação submetida.
- "(—)" significa que nenhum valor está definido (sem assignee, sem grupo, sem organização).
- Operadores negativos ("does not contain", "not present", "contains none of") são definidos caso a caso. A página não descreve regra geral de nullify para triggers.
- Campos de data customizados usam dias corridos e ignoram horário comercial e schedules.
- Combinações proibidas: "On a holiday?" não combina com "Within business hours?" nem com "Within (schedule)". Mensageria: "Messaging session" não combina com "Set routing channel".

**Legado**
- "Add CC" (ação e condição): substituído por "Add follower" quando CCs e followers atualizados estão ativos. — [Ticket trigger actions](https://support.zendesk.com/hc/en-us/articles/4408893545882-Ticket-trigger-conditions-and-actions-reference)
- Condições "Ticket > Status" (formas antigas): convertidas em categoria quando status customizados estão ativos. Ver condições acima.
- Ações e condições ligadas ao X ("Tweet", "Verified by X Corp", seguidores e tweets): status de depreciação não verificado nas fontes lidas.

### Inferences
- O modelo "all/any + ordem por posição + encadeamento" pode ser replicado com uma única linguagem de condições, reaproveitada por triggers, automações e views. Views têm condições específicas ("current user"), então o parser precisa aceitar esse conjunto menor.
- Como os triggers encadeiam, o motor precisa de uma proteção contra loops. As fontes não confirmam o comportamento exato do Zendesk, então a proteção (por exemplo, limitar passadas e impedir que a mesma regra dispare duas vezes na mesma transação) é uma escolha de design, não uma regra copiada.
- `Updated` disparando a cada submissão exige que a implementação distinga "submeteu uma atualização" de "algo mudou". Sem isso, regras de notificação disparam em toda edição.
- A condição `Update via` exige persistir o canal de origem de cada atualização (web, API, email, bulk, mensageria).
- A exclusão de tickets fechados precisa ser feita no ponto de entrada do motor de triggers, não em cada ação.
- Validar combinações proibidas (holiday com within) e tamanho máximo da regra (65 KB no Zendesk) na API, com 422, em vez de deixar o erro subir para o modelo.

### Gaps
- Não confirmado se cada trigger dispara no máximo uma vez por ciclo, nem o número máximo de ciclos. A página do artigo diz apenas que ações podem afetar os demais.
- Categorias de trigger: a API tem `category` e `category_id`, mas o comportamento (por exemplo, ordem entre categorias) não foi lido.
- Triggers padrão de contas novas: o artigo menciona que existem "standard ticket triggers" mas não os descreve. Não verificados.
- Limites de quantidade de triggers: existe o endpoint "Show Ticket Trigger Limits", mas os valores não foram lidos.
- Ações "Notify" em sequência, e a ordem exata de disparo entre ações de um mesmo trigger: não verificado.
- Lista de condições dos "Ticket > Subject text" e "Requester" em todos os operadores: lida apenas em resumo.

---

## Automações (automations)

### Takeaway
Automações são avaliadas periodicamente, sobre o estado do ticket, e não por evento. Cada regra precisa de uma condição "nullifying" para não rodar continuamente. As condições temporais medem horas decorridas desde a última atualização do ticket, em inteiros. A cadência de execução e o limite de tickets por execução não aparecem nas páginas oficiais lidas, então não devem ser tomados como fato.

### Cited Findings

**Condições temporais ("hours since" e relacionadas)** — [Automation conditions](https://support.zendesk.com/hc/en-us/articles/4408885654298-Automation-conditions-and-actions-reference)
- Hours since created; Hours since open; Hours since pending; Hours since on-hold; Hours since solved.
- Hours since status category [nome]; Hours since [status de sistema ou customizado].
- Hours since assigned (para um agente).
- Hours since update; Hours since requester update; Hours since assignee update.
- Hours since due date e Hours until due date (só tickets do tipo Task).
- Hours since last SLA breach; Hours until next SLA breach.
- Hours since last Group SLA breach e Hours until next Group SLA breach (Enterprise).

**Regras de tempo** — [Automation conditions](https://support.zendesk.com/hc/en-us/articles/4408885654298-Automation-conditions-and-actions-reference)
- O tempo conta "as horas decorridas desde que uma atualização do ticket foi feita".
- Só valores inteiros. Decimais são arredondados para baixo (1,5 vira 1).
- Condições "hours since" de status só disparam se o ticket permanecer naquele status ou categoria. Uma mudança de status reseta a condição.
- O operador "is" só casa dentro de uma janela estreita, e uma execução atrasada pode perder o alvo. "Greater than" ou "less than" costuma ser mais confiável.
- "Hours until ... less than" é inclusivo. Todas as outras condições temporais são exclusivas.
- "Hours since update" é resetado por qualquer atualização, inclusive a que a própria automação faz.
- "Due date" refere-se a 12:00 (meio-dia) no fuso horário da conta, na data indicada.
- Condições temporais não podem estar na seção "Meet any of these conditions".
- Automações precisam de condição nullifying: "Automations require a nullifying condition to ensure that they aren't running continuously."

**Tickets fechados** — [Automation conditions](https://support.zendesk.com/hc/en-us/articles/4408885654298-Automation-conditions-and-actions-reference)
- Automações não podem atualizar ou alterar tickets fechados.
- Não existe condição "Hours since closed". `Closed` continua disponível como valor de status.

**Outras condições de ticket em automações** — [Automation conditions](https://support.zendesk.com/hc/en-us/articles/4408885654298-Automation-conditions-and-actions-reference)
- Ticket: Status, Status category, Ticket status, Brand (não Team), Form (Enterprise), Type, Priority, Group, Assignee, Requester, Organization, Tags (contém ao menos um / contém nenhum), Description (contém ao menos um / contém nenhum), Channel, Integration account, Received at (is / is not), Satisfaction (não Team), Privacy (tem comentários públicos / não tem), campos customizados (date, dropdown, multi-select, e checkbox se definir uma tag), Ticket sharing (Sent to / Received from), Service catalog form.
- Requester: Language, Role, campos customizados. Organization: campos customizados.

**Ações de automação** — [Automation conditions](https://support.zendesk.com/hc/en-us/articles/4408885654298-Automation-conditions-and-actions-reference)
- Status, Status category, Ticket status, Form (Enterprise), Priority, Type, Group (para desatribuir, usar "(—)"), Assignee (—, requester, agente, current user), Satisfaction (oferecida ao requester).
- Tags: "Set tags" (substitui todas), "Add tags", "Remove tags".
- "Add cc" (quando CCs ativos; legado) e "Add follower" (quando CCs e followers ativos; substitui Add cc).
- Campos customizados (checkbox, dropdown, date, multi-select), "Share ticket with" (Growth/Professional e acima; exige acordo de compartilhamento), Requester: Language e campos customizados, Organization: campos customizados.
- Notificações: "Email user" (requester, assignee, usuário nomeado, current user, requester and CCs), "Email group" (grupo atribuído ou nomeado), "Notify active webhook", "Notify target", "Tweet requester".
- O email só é enviado se a atualização tiver comentário público.

**Cadência e limites: não confirmados nas páginas oficiais.** Um resumo de busca atribuído ao Zendesk afirmou que as automações rodam de hora em hora, que a primeira execução após a condição conta como zero horas e que há limite de 1000 tickets por ciclo. Essas afirmações não aparecem nas páginas oficiais lidas. A página de referência de automações lista explicitamente "how often automations run" e "any limit on how many tickets are processed per run" como não cobertos. — [Automation conditions](https://support.zendesk.com/hc/en-us/articles/4408885654298-Automation-conditions-and-actions-reference)

**Automações padrão.** O artigo sobre triggers diz apenas que existem triggers padrão e não menciona automações padrão. Não há fonte lida que confirme "fechar 4 dias após solved" ou lembretes de pending. — [Artigo sobre triggers](https://support.zendesk.com/hc/en-us/articles/203662246)

**Afirmação de terceiros, não confirmada.** O eesel.ai diz que automações têm lookback máximo de 28 dias (672 horas). Não foi confirmado na página oficial. — [eesel.ai, condições baseadas em horário](https://eesel.ai/blog/zendesk-automation-schedule-based-conditions) (secundário)

### Inferences
- Como as automações são periódicas, a implementação em Rails precisa de um job recorrente que varra apenas tickets elegíveis. Para isso, as condições temporais devem ser filtradas no SQL, com timestamps indexados (por exemplo, última atualização, última mudança de status, última atualização do requester e do assignee). Esta é uma sugestão de design.
- Para que "Hours since update" não entre em loop, a automação precisa de um critério que a própria escrita não reseta, ou precisa distinguir atualizações de requester e de assignee. As condições "Hours since requester update" e "Hours since assignee update" da lista oficial sugerem essa separação.
- A exigência de nullifying deve ser validada na criação da regra: pelo menos uma condição não temporal, e nenhuma condição temporal na seção `any`.
- Como o Zendesk trata "is" como janela estreita, a implementação não deve replicar essa semântica por padrão. Sugerir `greater than` e `less than` nas regras de exemplo.

### Gaps
- Não confirmado se "Hours since" usa horas corridas ou horas comerciais. A página cita um "(calendar)" em um exemplo, mas não descreve a regra. Este é o ponto mais importante para o requisito de horário comercial, e precisa de verificação direta na conta de teste.
- Cadência exata (hora em hora, ou outra) e limite de tickets por execução: não confirmados oficialmente.
- Como a primeira execução é contada (se "zero horas" ou outra regra): só em resumo de busca.
- Automações padrão e seu conteúdo: não verificados.

---

## Views

### Takeaway
Views são consultas de tickets (condições `all` e `any`) com configuração de colunas, agrupamento e ordenação, além de restrição de acesso (`restriction` nulo significa todos). Os limites documentados são de paginação (100 registros) e de contagem (aproximada, com cache de 24 horas acima de 100.000). Os valores exatos da restrição (personal, group, shared) e o modo "Play" não foram lidos.

### Cited Findings

**Objeto view** — [Views API](https://developer.zendesk.com/api-reference/ticketing/business-rules/views/)
- Campos: `title`, `description`, `conditions` (condições `all` e `any`; referência de condições não lida), `execution` (colunas e ordenação), `active`, `position`, `restriction` (nulo significa todos os usuários da conta), `default` (somente leitura).
- A página não define os valores de restrição como "personal", "group" ou "shared". O filtro `access` da listagem usa esses termos, mas os valores não estão definidos na página lida.

**Execução (colunas, agrupamento, ordenação)** — [Views API](https://developer.zendesk.com/api-reference/ticketing/business-rules/views/)
- `columns`: lista de campos de ticket. Campos customizados aparecem com `id`, `title`, `type` e `url`.
- `group_by` e `sort_by`: nome de uma coluna. As colunas `subject` e `submitter` não são suportadas.
- `group_order` e `sort_order`: `asc` ou `desc`.
- `group` e `sort`: presentes quando há agrupamento ou ordenação.

**Condições específicas de view** — [Ticket trigger conditions](https://support.zendesk.com/hc/en-us/articles/4408893545882-Ticket-trigger-conditions-and-actions-reference)
- Assignee, Group e Requester aceitam "current user" (e, em Group, "current user's group(s)") apenas em views.

**Endpoints e limites** — [Views API](https://developer.zendesk.com/api-reference/ticketing/business-rules/views/)
- `GET /api/v2/views`: lista views compartilhadas e pessoais. Filtros: `access`, `active`, `group_id`, `sort`, `sort_by`, `sort_order`. Até 100 registros por página. Paginação por cursor é a recomendada.
- `GET /api/v2/views/active`: views ativas, até 100 por página.
- `GET /api/v2/views/compact`: no máximo 32 registros, ignora `per_page`.
- `GET /api/v2/views/show_many?ids=...`: views por lista de IDs separada por vírgula. Não há máximo documentado de IDs.
- `GET /api/v2/views/count`: contagem aproximada. Acima de 100.000, a contagem é cacheada e atualizada a cada 24 horas. `count[refreshed_at]` pode vir nulo durante a atualização em segundo plano.
- A API lista também "Execute View", "List Tickets From a View", "Count Tickets in View" e "Export View", mas o conteúdo não foi lido.

### Inferences
- Uma view pode ser modelada como o mesmo JSON de condições dos triggers, mais uma configuração de colunas, agrupamento e ordenação, com `restriction` nulo significando público. Assim, o parser de condições é compartilhado.
- O cache de contagem acima de 100.000 é uma saída de performance que faz sentido replicar. O limite exato no Chatwoot seria uma decisão de produto.

### Gaps
- Lista completa de campos de condição de view: a referência de condições não foi lida.
- Modo "Play" (percorrer tickets da view em sequência) e exportação: não lidos.
- Valores exatos de `access` e `restriction` (personal, group, shared): não definidos na página lida.
- Limite de número de views por conta e de condições por view: não documentado nas fontes lidas.
- Ordem e tratamento de views sem resultados: não verificado.

---

## Macros

### Takeaway
Macros são pacotes de ações para aplicar em um ticket, com restrição por usuário ou grupo, ou acesso geral. Elas não avaliam condições. Atualizar as ações de uma macro substitui o array inteiro. Os tipos completos de ação e o comportamento de placeholders não foram confirmados.

### Cited Findings

**Objeto macro** — [Macros API](https://developer.zendesk.com/api-reference/ticketing/business-rules/macros/)
- Campos: `title` (obrigatório), `raw_title`, `actions` (array obrigatório; a referência de tipos de ação não foi lida), `active` (controla exibição), `default` (somente leitura), `description`, `position`, `restriction`.
- `restriction`: nulo significa acesso irrestrito a todos os usuários. Na criação, aceita `type` `"Group"` ou `"User"` com `id` ou `ids`. Omitido significa acesso para todos os agentes.
- Atualizar `actions` substitui o array inteiro, então é preciso enviar todas as ações ao alterar uma.
- A visualização administrativa da lista inclui as macros pessoais dos agentes. — [Macros API](https://developer.zendesk.com/api-reference/ticketing/business-rules/macros/)

**Ordenação e listagem** — [Macros API](https://developer.zendesk.com/api-reference/ticketing/business-rules/macros/)
- `sort_by`: alfabético (padrão), `created_at`, `updated_at` e campos de uso. Campos de uso exigem Support Professional ou Suite Growth e superior.
- `sort_order`: `asc` ou `desc`. Até 100 registros por página, com paginação por cursor recomendada.

**Permissões** — [Macros API](https://developer.zendesk.com/api-reference/ticketing/business-rules/macros/)
- Criar e atualizar é descrito como disponível para agentes.

**Ações de macro (compartilham o catálogo de triggers, com ressalva)** — [Ticket trigger actions](https://support.zendesk.com/hc/en-us/articles/4408893545882-Ticket-trigger-conditions-and-actions-reference)
- A página de triggers diz que macros e triggers aceitam "current user" em Assignee, e que macros aceitam grupos do usuário atual em Group. Não há confirmação de que o conjunto completo de ações de trigger vale para macros.

**Preview** — [Macros API](https://developer.zendesk.com/api-reference/ticketing/business-rules/macros/)
- A API lista endpoints "Show Changes to Ticket" e "Show Ticket After Changes", com conteúdo não lido.

**Secundário (não confirmado oficialmente)**: macros são aplicadas manualmente por agentes, e não disparam sozinhas. — [eesel.ai, visão geral de business rules](https://www.eesel.ai/blog/zendesk-business-rules-overview-and-setup) (resumo de busca)

### Inferences
- Uma macro pode reusar o executor de ações dos triggers, sem o avaliador de condições. Com isso, o mesmo código de ação serve aos dois motores.
- A semântica de "substituir o array inteiro" é um contrato de API. No Chatwoot, vale decidir conscientemente se a API interna segue esse modelo ou usa atualização por item.

### Gaps
- Lista de tipos de ação aceitos em macros (a referência de ações não foi lida): não verificado se coincide com a de triggers.
- Placeholders e Liquid no corpo de comentários de macros: não descritos na página lida.
- Aplicação de várias macros de uma vez: não verificado.
- Significado de "personal", "shared" e "group" para macros: a página não define os valores.

---

## Políticas de SLA

### Takeaway
Uma política de SLA combina um filtro (`filter`, com `all` e `any`) com metas por prioridade e por métrica. Cada meta tem um flag `business_hours` que escolhe horário comercial ou corrido. A API expõe sete métricas. A regra "só uma política aplica" e o comportamento de pausa e de cumprimento não foram confirmados nas fontes oficiais lidas.

### Cited Findings

**Objeto de política** — [SLA Policies API](https://developer.zendesk.com/rest_api/docs/core/sla_policies)
- `title` (obrigatório).
- `filter` (obrigatório): condições que o ticket precisa atender, com arrays `all` (E) e `any` (OU). Cada condição tem `field`, `operator` e `value`. A referência de campos aceitos não foi lida.
- `policy_metrics` (opcional): um item por prioridade, com `priority`, `metric`, `target` (minutos) ou `target_in_seconds`, e `business_hours` (booleano; `true` mede em horário comercial, `false` em horário corrido).
- `position` (opcional): ordem de avaliação. Se omitido, a política vai para o fim.
- `description` (opcional). `id`, `created_at`, `updated_at` e `url` são somente leitura.

**Métricas** — [SLA Policies API](https://developer.zendesk.com/rest_api/docs/core/sla_policies)
- `first_reply_time`, `next_reply_time`, `periodic_update_time`, `requester_wait_time`, `agent_work_time`, `pausable_update_time`, `total_resolution_time`.

**Endpoints** — [SLA Policies API](https://developer.zendesk.com/rest_api/docs/core/sla_policies)
- `GET /api/v2/slas/policies`, `POST /api/v2/slas/policies`, `GET /api/v2/slas/policies/{sla_policy_id}`, `PUT /api/v2/slas/policies/{sla_policy_id}`, `DELETE /api/v2/slas/policies/{sla_policy_id}`.
- Também listados, mas não lidos: reorder e métricas de SLA por ticket.

**Disponibilidade** — [SLA Policies API](https://developer.zendesk.com/rest_api/docs/core/sla_policies)
- Disponível em Support Professional ou Suite Growth e superior. Somente administradores.

**Condições de SLA em automações** — [Automation conditions](https://support.zendesk.com/hc/en-us/articles/4408885654298-Automation-conditions-and-actions-reference)
- Hours since last SLA breach; Hours until next SLA breach; Hours since/until last/next Group SLA breach (Enterprise).

**Ordem e casamento (secundário)**: "Zendesk evaluates SLA policies top-down and applies the first one whose conditions match." Não confirmado na página oficial lida, que diz apenas que `position` define a ordem de casamento. — [getmacha, SLA](https://www.getmacha.com/blog/zendesk-sla-explained) (resumo de busca)

**Horário comercial (secundário)**:
- Business hours contam apenas dentro do cronograma definido. O timer pausa fora desse horário. — [eesel.ai, SLA com calendário e horário comercial](https://www.eesel.ai/blog/zendesk-sla-calendar-business-hours) (resumo de busca)
- Metas em horário comercial exigem que o cronograma exista antes. — [eesel.ai, horário comercial](https://www.eesel.ai/blog/zendesk-business-hours) (resumo de busca)
- O exemplo do eesel.ai (meta de 8 horas, aberta sexta às 17h, cronograma seg-sex 9h-17h, vencimento na segunda às 9h) é internamente inconsistente. Com esse cronograma, a contagem começa na segunda às 9h, e 8 horas úteis vencem às 17h, não às 9h. Não usar esse exemplo como especificação.

### Inferences
- Modelar o SLA em três partes: (a) política com filtro, (b) tabela de metas por prioridade, métrica e flag de horário, e (c) timers por ticket. Os timers acumulam tempo corrido ou comercial e podem ser pausados. A pausa deve ser estado do timer, não só um cálculo no momento da leitura.
- As condições "Hours until next SLA breach" pedem que o próximo vencimento esteja materializado por ticket e métrica. Sem isso, a automação não tem como filtrar eficientemente.
- A ordem (`position`) precisa ser única e validada. Uma política sem `position` deve cair no fim.

### Gaps
- Semântica de breach, de cumprimento (fulfill) e de badges: não lida.
- Quando cada métrica começa e para (por exemplo, o que conta como primeira resposta): não verificado.
- Pausa (`pausable_update_time`): o nome da métrica existe, mas a regra de pausa não foi lida.
- Regra "uma única política por ticket": apenas em fonte secundária.
- Group SLAs (OLAs): aparecem como condições de automação em Enterprise, mas os detalhes não foram lidos.
- Referência de campos do `filter` de SLA: não lida.
- Escolha entre horário comercial e corrido para cada prioridade: a recomendação de terceiros (corrido para urgente, comercial para o restante) é só secundária.

---

## Horários comerciais (schedules) e feriados

### Takeaway
Horário comercial aparece em três lugares: no flag `business_hours` das métricas de SLA, nas condições de trigger ("Within business hours?", "On a holiday?", "Within (schedule)", "Ticket > Schedule") e na ação "Set schedule". Quase todas as variantes com schedule nomeado são Enterprise. A estrutura interna do schedule (dias, janelas, feriados) não foi lida.

### Cited Findings
- "Within business hours?": sim ou não. Não Team. Em Enterprise, usa o schedule aplicado ao ticket. Não combina com "On a holiday?". — [Ticket trigger conditions](https://support.zendesk.com/hc/en-us/articles/4408893545882-Ticket-trigger-conditions-and-actions-reference)
- "On a holiday?": sim ou não, o dia inteiro. Respeita os feriados do schedule aplicado. Enterprise. Não combina com "Within business hours?" nem com "Within (schedule)". — [Ticket trigger conditions](https://support.zendesk.com/hc/en-us/articles/4408893545882-Ticket-trigger-conditions-and-actions-reference)
- "Within (schedule)": compara o horário da atualização com qualquer schedule nomeado, não só o do ticket. Enterprise. — [Ticket trigger conditions](https://support.zendesk.com/hc/en-us/articles/4408893545882-Ticket-trigger-conditions-and-actions-reference)
- "Ticket > Schedule": nome do schedule aplicado ao ticket. Enterprise. — [Ticket trigger conditions](https://support.zendesk.com/hc/en-us/articles/4408893545882-Ticket-trigger-conditions-and-actions-reference)
- "Set schedule": aplica um schedule nomeado ao ticket. Enterprise. — [Ticket trigger actions](https://support.zendesk.com/hc/en-us/articles/4408893545882-Ticket-trigger-conditions-and-actions-reference)
- Campos de data customizados usam dias corridos e ignoram horário comercial e schedules. — [Ticket trigger conditions](https://support.zendesk.com/hc/en-us/articles/4408893545882-Ticket-trigger-conditions-and-actions-reference)
- Flag `business_hours` por meta de SLA. — [SLA Policies API](https://developer.zendesk.com/rest_api/docs/core/sla_policies)
- Business hours e SLA exigem Professional ou superior. — [SLA Policies API](https://developer.zendesk.com/rest_api/docs/core/sla_policies) (limite de plano do SLA); [eesel.ai, horário comercial](https://www.eesel.ai/blog/zendesk-business-hours) (secundário, para o caso de business hours)

### Inferences
- O schedule pode ser modelado como entidade própria, com fuso horário, janelas por dia e lista de feriados, referenciada pela conta, pelo ticket e pelas regras. O cálculo de minutos úteis decorridos deve ser uma função pura, testável isoladamente.
- As combinações proibidas (holiday com within) devem ser validadas na API, com 422.

### Gaps
- Estrutura interna do schedule (dias, múltiplas janelas por dia, feriados recorrentes), e como o schedule padrão da conta é escolhido: não lidos.
- Se o plano Team tem algum schedule, além da ausência das condições marcadas como "not Team": não verificado.
- Regra exata de pausa do timer fora do horário: só em fonte secundária.

---

## Placeholders e Liquid

### Takeaway
A sintaxe de placeholders (`ticket.*`, `ticket.requester.*`, `current_user.*`) e de Liquid condicional não foi verificada nas fontes lidas. A página de macros não descreve placeholders no corpo de comentários. Não replicar a sintaxe do Zendesk sem antes ler a documentação oficial de placeholders.

### Cited Findings
- A página de macros não descreve suporte a placeholders ou Liquid no corpo de comentários, e aponta apenas para a referência de ações. — [Macros API](https://developer.zendesk.com/api-reference/ticketing/business-rules/macros/)
- Nenhuma fonte oficial sobre placeholders foi lida nesta pesquisa.

### Inferences
- Placeholders em corpos de email e comentário são o ponto de maior risco de injeção de HTML. Recomenda-se escapar valores por padrão e usar uma lista branca de variáveis disponíveis (prática geral, não extraída das fontes).

### Gaps
- Lista de objetos e atributos disponíveis (`ticket.*`, `requester.*`, `current_user.*`, `assignee.*`, `organization.*`, conteúdo dinâmico): não verificada.
- Liquid condicional (`if`/`else`), filtros e loops suportados: não verificados.
- Onde placeholders são aceitos (triggers, automações, macros, notificações): não verificado.
- Próxima pesquisa sugerida: buscar no help center oficial do Zendesk a documentação de placeholders e de Liquid de business rules.

---

## Webhooks e targets como ações

### Takeaway
Triggers e automações podem notificar um webhook ativo ("Active webhook" em triggers, "Notify active webhook" em automações) ou um target externo ("External target" em triggers, "Notify target" em automações). Trocar o destino de uma notificação reseta o corpo do texto. Formato de payload, assinatura, retries e limites não foram lidos.

### Cited Findings
- "Active webhook": seleciona o webhook. Trocar o destino reseta o corpo do texto. — [Ticket trigger actions](https://support.zendesk.com/hc/en-us/articles/4408893545882-Ticket-trigger-conditions-and-actions-reference)
- "External target": seleciona um target externo de email. Trocar o destino reseta o corpo do texto. — [Ticket trigger actions](https://support.zendesk.com/hc/en-us/articles/4408893545882-Ticket-trigger-conditions-and-actions-reference)
- "Notify active webhook" e "Notify target" existem como ações de automação. — [Automation actions](https://support.zendesk.com/hc/en-us/articles/4408885654298-Automation-conditions-and-actions-reference)
- Notificações por email só são enviadas quando a atualização tem comentário público. — [Ticket trigger actions](https://support.zendesk.com/hc/en-us/articles/4408893545882-Ticket-trigger-conditions-and-actions-reference); [Automation actions](https://support.zendesk.com/hc/en-us/articles/4408885654298-Automation-conditions-and-actions-reference)

### Inferences
- Um webhook como ação de regra deve ser enfileirado como job assíncrono, para não bloquear a atualização do ticket. Com assinatura e retentativas, isso é prática geral, não extraída das fontes.

### Gaps
- Formato de payload, assinatura, retentativas e timeout dos webhooks do Zendesk: não lidos.
- Tipos de target além de email externo, e seus limites: não lidos.
- Não existe página de API de webhooks ou targets nas fontes lidas.
