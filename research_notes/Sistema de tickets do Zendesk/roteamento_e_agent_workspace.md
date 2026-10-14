# Roteamento de tickets e Agent Workspace no Zendesk (estado em 2026)

Pesquisa feita em 2026-10-13, para replicar UX e lógica de roteamento num fork do Chatwoot (Rails + Vue).

**Legenda de confiança**
- **[F]**: conteúdo lido por fetch no artigo oficial (support.zendesk.com ou developer.zendesk.com).
- **[S]**: trecho que apareceu em resultado de busca, com URL oficial, mas o artigo completo não foi lido (ou o fetch falhou).
- **[3P]**: blog, glossário ou guia de terceiros. Usar só como pista, não como fato.
- **[L]**: legado, ou recurso anterior ao omnichannel / Agent Workspace.

**Limitações desta rodada**
- O artigo de skills-based routing (`360000789788`) deu 404 no fetch, tanto com slug quanto só com o ID. Os dados sobre skills são de snippet.
- Não há doc oficial lido sobre detecção de colisão, toolbar, composer, menções, ticket sharing, Knowledge capture nem macros sugeridas. Esses pontos estão em Gaps.
- A pesquisa passou de ~15 chamadas, acima do guia de pesquisa, por causa da amplitude do tema.

---

## Roteamento omnichannel: canais, filas e prioridade

### Takeaway
O omnichannel routing atribui automaticamente tickets de e-mail (incluindo web form, side conversations e API), mensagens e chamadas, conforme status do agente, capacidade por canal e skills. Só entram tickets com status `new` ou `open`. Há uma fila padrão, sempre existente, e custom queues (Professional e acima), avaliadas depois dos triggers. O ticket entra na primeira fila cujas condições ele satisfaz.

### Cited Findings
- Omnichannel roteia e-mail (web form, side conversations, API), chamadas e mensagens para agentes disponíveis e com capacidade. Só tickets com status `new` ou `open` são roteados. [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- Canais de mensagem incluem nativo, LINE, Telegram, WhatsApp e outros. Chamadas incluem entrantes e saintes. [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- A fila padrão é o default. Sem custom queues, todo ticket vai para ela, e o ticket precisa ter grupo atribuído. [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- Custom queues são avaliadas depois dos triggers. O ticket entra na "primeira fila cujas condições atende". [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- E-mail entra na fila padrão só depois que uma tag de auto-roteamento é adicionada. Com custom queues, o e-mail é avaliado ao chegar, independentemente de tags. [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- Trabalho em custom queues tem precedência sobre a fila padrão, "regardless of the individual ticket priority". Custom queues usam grupos primários e, sem agentes disponíveis, grupos de fallback. [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- Ordenação da fila por plano:
  - Team: timestamp mais antigo elegível para roteamento.
  - Growth e acima: escolha entre timestamp mais antigo ou SLA mais próximo de estourar.
  - Professional e acima: escolha entre maior prioridade com timestamp mais antigo, ou SLA mais próximo de estourar. [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- Chamadas em linhas prioritárias são atribuídas primeiro, e seus tickets recebem prioridade High. [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- Planos: All Suites inclui Team, Growth, Professional, Enterprise e Enterprise Plus. Support inclui Team, Professional e Enterprise. [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- Custom queues exigem Professional ou acima. [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- Pré-requisito: Agent Workspace ativado na conta. [3P](https://www.eesel.ai/blog/zendesk-omnichannel)

### Inferences
- Modelo em duas camadas: primeiro a fila (qual grupo, por regra de condição), depois o agente (status, capacidade e skills). Para o Chatwoot, isso sugere separar "regra de fila" de "elegibilidade do agente". Não verifiquei no código como o auto-assignment atual está implementado.
- Uma custom queue é uma regra de condição com ordem (posição) e grupos primário e de fallback. Pode-se reaproveitar o formato de filtros de automação já existente.
- A ordenação por timestamp de elegibilidade é a forma mais simples (equivale ao plano Team). Prioridade e SLA são extensões dessa ordenação.

### Gaps
- Não li "Omnichannel routing resources" (`5061050408730`) nem a API de Omnichannel routing. Os endpoints ficaram de fora.
- Não confirmei como custom queues combinam prioridade e SLA dentro de uma mesma fila.

---

## Status do agente e capacidade por canal

### Takeaway
O agente tem um único status unificado para Support, Talk e Messaging: online, away ou offline. Mensagens e chamadas exigem online. E-mail aceita online ou away. A capacidade é configurada por canal: e-mail até 500 tickets abertos, mensagens até 20 (o chat compartilha o valor, mas conta separado), voz 0 ou 1. Ao atingir o limite, o roteamento para de atribuir automaticamente, mas o agente pode se atribuir mais tickets manualmente.

### Cited Findings
- Agentes usam um status unificado para Support, Talk e Messaging, em vez de um por canal. Com status unificado, o horário de operação não define o status automaticamente. [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- Admins em Professional e acima podem criar status customizados. [S](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- E-mail exige status online ou away. Mensagens e chamadas exigem online. [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- O agente fica away ou offline automaticamente após um limiar de inatividade definido pelo admin. Fica offline também quando o workspace fecha sem sign-out ou a conexão cai. Se o encaminhamento de chamadas estiver ligado e o agente ficar offline dessa forma, as chamadas deixam de ser encaminhadas para o telefone dele. [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- Capacidade de e-mail: número de tickets abertos (inclui web form, side conversation e API). Tickets pending ou on hold não contam. Máximo de 500. [F](https://support.zendesk.com/hc/en-us/articles/4776409839770-Creating-capacity-rules-to-balance-agent-workloads)
- Capacidade de mensagens: máximo de 20. Chat e mensagem compartilham o valor configurado, mas são aplicados separadamente. [F](https://support.zendesk.com/hc/en-us/articles/4776409839770-Creating-capacity-rules-to-balance-agent-workloads)
- Capacidade de voz: 0 ou 1. Com 0, o agente não recebe chamadas. [F](https://support.zendesk.com/hc/en-us/articles/4776409839770-Creating-capacity-rules-to-balance-agent-workloads)
- Ao atingir a capacidade, o roteamento não atribui novos tickets naquele canal até que haja espaço. [F](https://support.zendesk.com/hc/en-us/articles/4776409839770-Creating-capacity-rules-to-balance-agent-workloads)
- Capacidade limita só a atribuição automática. O agente pode ultrapassar o limite atribuindo manualmente, ou quando tickets inativos voltam a ficar ativos. [F](https://support.zendesk.com/hc/en-us/articles/4776409839770-Creating-capacity-rules-to-balance-agent-workloads)
- Conversa de mensagem é considerada inativa quando o usuário final não responde há 10 minutos. Admins podem mudar isso com as configurações de liberação de capacidade. Por padrão, a opção "Count inactive conversations towards an agent's capacity" fica desligada, então só tickets ativos contam. [F](https://support.zendesk.com/hc/en-us/articles/4776409839770-Creating-capacity-rules-to-balance-agent-workloads)
- Planos da capacidade: Support em Team, Professional ou Enterprise. All Suites em Team, Growth, Professional, Enterprise ou Enterprise Plus. [F](https://support.zendesk.com/hc/en-us/articles/4776409839770-Creating-capacity-rules-to-balance-agent-workloads)
- Conflito sobre os status padrão: um guia de terceiros lista Online, Away e Offline. Outro blog de terceiros fala em quatro padrões, incluindo "Transfers only", e diz que só Offline e Away removem trabalho do agente. Os dois são [3P](https://www.eesel.ai/blog/zendesk-omnichannel) e [3P](https://www.getmacha.com/blog/zendesk-omnichannel-routing-not-working). Não resolvido: conferir na tela "Agent statuses" de uma conta de teste.

### Inferences
- Para o Chatwoot, o status do agente precisa de regra por canal: e-mail aceita "away", chat e mensagem exigem "online". Verificar antes os status que o Chatwoot já tem.
- Capacidade é um contador de conversas abertas por canal, com teto configurável por inbox ou time. O padrão de contar só conversas "ativas" (sem resposta do cliente em 10 min) vale replicar, com flag.
- Auto-away por inatividade e offline por desconexão dependem de presença (heartbeat ou ActionCable). Essa parte é o que mais custa para implementar.
- A regra "capacidade bloqueia só a auto-atribuição" precisa viver no serviço de auto-assignment. Não deve ficar no modelo de assignment, senão a atribuição manual também seria bloqueada.

### Gaps
- Os valores padrão de capacidade não aparecem no artigo lido. O número 10 citado é só exemplo.
- Não encontrei o limiar padrão de inatividade (auto-away).
- A lista exata de status padrão continua em conflito, como descrito acima.

---

## Atribuição, reatribuição e casos de borda

### Takeaway
Pelo método padrão, o ticket vai para o agente com mais capacidade livre no canal, medida como número ou porcentagem. Em empate, vai para quem está há mais tempo sem receber ticket daquele canal. Round robin entrega ao agente disponível que está há mais tempo sem atribuição no canal, mas ainda exige capacidade livre. Em mensagens e chat, se o agente não aceitar dentro do limiar (30 segundos por padrão), a conversa pode ser reatribuída. Ticket de voz já atribuído não é reatribuído.

### Cited Findings
- Highest spare capacity (padrão): atribui ao agente com "the highest spare capacity for the relevant channel", medido como número ou porcentagem. Em empate, vale quem está há mais tempo sem ticket daquele canal. [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- Round robin: atribui ao "available agent who's gone the longest time without being assigned work for the channel". O agente ainda precisa de capacidade livre. [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- Mensagens e chat: se o agente não aceitar dentro do limiar (30 segundos por padrão, configurável em Enterprise e acima), a conversa pode ser reatribuída. Isso exige a configuração de reassignment timing ligada. Caso contrário, o motor continua tentando o mesmo agente. [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- Chamadas: se recusada ou não atendida em 30 segundos, a chamada volta para a fila. Ela é oferecida em round robin até expirar o "maximum queue waiting time". [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- Ticket de voz atribuído não é reatribuído pelo omnichannel, mesmo que fique sem agente ou volte a um grupo. [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- E-mail e mensagem já atribuídos: em Team e Growth, a reatribuição passa só pela fila padrão, nunca por custom queues. Em Professional e acima, o admin escolhe entre custom queue e fila padrão. [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- Ticket reaberto é tratado como evento de atribuição pelo omnichannel. [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- Ao ser atribuído, o ticket sai da fila. Chamada sai da fila quando termina. [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)

### Inferences
- O "aceitar em X segundos ou reatribuir" pede um estado intermediário, "pendente de aceite", separado de "atribuído". Um job com timer por conversa dispara a reatribuição. Verificar se o Chatwoot já tem esse estado.
- "Reabrir é evento de atribuição" significa rodar o motor de roteamento de novo na reabertura, sem manter o agente anterior por padrão. Isso é decisão de produto e precisa ser documentado.
- Atribuição manual e automática devem ser caminhos separados. A manual ignora capacidade. A automática respeita status, capacidade e skills.

### Gaps
- Não está documentado o que acontece com tickets de e-mail ou chat quando o agente fica offline depois de atribuído. Só a regra de voz está clara.
- Não confirmei se a reatribuição de ticket reaberto respeita o grupo original.

---

## Skills-based routing (skill types, skills e timeout)

### Takeaway
No modo omnichannel, o ticket só vai para agentes que têm todas as skills exigidas, status elegível e capacidade livre. Sem timeout, todas as skills são obrigatórias. Com timeout, depois de uma espera o ticket pode ir para agentes sem as skills opcionais. Disponível em Professional e acima. Existe também o modo standalone, em que o agente escolhe tickets em views e se atribui manualmente.

### Cited Findings
- No omnichannel, o agente precisa ter todas as skills do ticket, mais status elegível e capacidade. [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- Skills não mudam a ordem da fila, mas podem segurar tickets nela. Sem skills timeout, "all skills are treated as required". Com timeout, o ticket pode ir para agentes sem skills opcionais depois de uma espera. [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- Agentes podem ter skills de alta prioridade, que são checadas primeiro. [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- Skill types são criadas em Admin > Business Rules > Routing, pelo botão "New skill type". Limites: no máximo 10 skill types por organização, e nomes com até 96 caracteres. [S](https://support.zendesk.com/hc/en-us/articles/360000789788-Using-skills-based-routing)
- Skills são adicionadas aos tickets por triggers. Views limitam os agentes aos tickets compatíveis com as skills deles. [S](https://support.zendesk.com/hc/en-us/articles/360000789788-Using-skills-based-routing)
- Dois modos: no omnichannel, a atribuição é automática, com timeout opcional. No standalone, o agente escolhe tickets em views e se atribui. [S](https://support.zendesk.com/hc/en-us/articles/360000789788-Using-skills-based-routing)
- Exemplos de skill types dados por guia de terceiros: Languages (French, German), Product, Technical Level (Tier 1, 2, 3). [3P](https://www.eesel.ai/blog/zendesk-omnichannel)
- Existe uma API de skill-based routing com endpoints de routing attributes (`/api/v2/routing/attributes`). [S](https://developer.zendesk.com/api-reference/ticketing/ticket-management/skill_based_routing/)

### Inferences
- Modelo de dados sugerido: SkillType (nome) → Skill (nome, tipo) → vínculo agente-skill (com flag de alta prioridade) → vínculo ticket-skill (preenchido por trigger ou automação). A regra de elegibilidade é subconjunto: skills do ticket ⊆ skills do agente.
- Timeout é um job que, após N minutos, relaxa o filtro para as skills opcionais.
- As mesmas skills também funcionam como filtro de view. Vale reaproveitar o dado.
- No Chatwoot, labels já existem e podem servir de skills. Mas o subconjunto e o timeout exigem modelo próprio. Avaliar se labels bastam antes de criar um modelo novo.

### Gaps
- Não consegui ler a página de skills (404 no slug e no ID). O valor padrão do timeout não foi confirmado.
- Não li a página de API. Não confirmei os campos de skill type.

---

## Roteamento legado: round robin, Play mode e Guided mode

### Takeaway
[L] Antes do omnichannel, o Zendesk tinha round robin e um modo "Play" de pull, em que o agente clica num botão e recebe o próximo ticket de uma view. Guided mode (Enterprise) restringe o agente a acessar tickets só pelo botão Play. Round robin ainda existe, mas dentro do omnichannel. Não confirmei se a automação de round robin por trigger continua disponível.

### Cited Findings
- Play mode: o agente clica no botão play e é atribuído automaticamente ao próximo ticket disponível. Pode ser restrito a uma view específica. [S](https://support.zendesk.com/hc/en-us/articles/4408831658650-Routing-options-for-incoming-tickets)
- Guided mode (Enterprise): o admin pode configurar o acesso dos agentes para só usarem o botão Play. [S](https://support.zendesk.com/hc/en-us/articles/4408831658650-Routing-options-for-incoming-tickets)
- Round robin distribui tickets igualmente entre agentes, sem considerar complexidade ou expertise. [S](https://support.zendesk.com/hc/en-us/articles/4408831658650-Routing-options-for-incoming-tickets)
- Round robin também é um método dentro do omnichannel. [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- Um fornecedor de app afirma que o Guided mode só abre o ticket sem atribuir. É afirmação não verificada, de fornecedor. [3P](https://www.zendesk.com/se/marketplace/apps/support/1226340/agent-ticket-chat/)
- Há thread antiga da comunidade pedindo automação de round robin por trigger, o que sugere que ela nunca foi nativa no nível de regra. Data e resposta não foram lidas. [S](https://support.zendesk.com/hc/it/community/posts/4409222757786-Round-Robin-assignment?page=2)

### Inferences
- Play mode é um modelo pull: o agente pede a próxima conversa de uma fila ou filtro. No Chatwoot, isso equivale a um endpoint "próxima conversa", que atribui com lock (por exemplo, `SELECT ... FOR UPDATE SKIP LOCKED`) para evitar corrida entre agentes.
- Round robin pode ser um cursor por inbox ou time, ordenado por `last_assigned_at`. É mais simples que capacidade e serve de fallback.
- Como são modos legados, recomendo não tratar Play e Guided como padrão de 2026 sem confirmar no produto.

### Gaps
- Não li o artigo de routing options (`4408831658650`) por fetch. Detalhes de configuração ficaram de fora.
- Não confirmei a situação atual de automação de round robin por trigger.

---

## Agent Workspace: layout do ticket, painéis e composer

### Takeaway
O layout padrão mostra campos do ticket à esquerda, conversa no centro e painel de contexto à direita. O layout builder (drag-and-drop) permite escolher componentes, posição e tamanho. Em Professional há um layout ativo, que é o default, e até 20 layouts podem ser criados. Em Enterprise, vários layouts ficam ativos ao mesmo tempo, atribuídos por contextual workspace (marca, grupo ou formulário). Um ticket novo e não salvo sempre abre no layout padrão. O layout customizado só aplica depois do submit e da reabertura.

### Cited Findings
- O layout builder permite escolher componentes, organizar e redimensionar. Também permite mudar o fluxo da conversa e controlar os dados de cada componente. Vale para a interface principal e para o painel de contexto. [F](https://support.zendesk.com/hc/en-us/articles/5447690090138-About-custom-layouts-with-layout-builder)
- Componentes citados: conversas, propriedades do ticket (campos), customer context, apps de terceiros e "mais". [F](https://support.zendesk.com/hc/en-us/articles/5447690090138-About-custom-layouts-with-layout-builder)
- Layouts podem ser aplicados por condições do ticket ou como default da conta. [F](https://support.zendesk.com/hc/en-us/articles/5447690090138-About-custom-layouts-with-layout-builder)
- No layout padrão, o painel de contexto fica à direita. Agentes podem redimensionar o painel de contexto e o de propriedades. Admins escolhem quais apps aparecem no painel, em que ordem, ou movem apps populares para a área principal. [F](https://support.zendesk.com/hc/en-us/articles/5447690090138-About-custom-layouts-with-layout-builder)
- Limites: Professional e Enterprise criam até 20 layouts. Professional tem só um layout ativo, definido como default. Enterprise pode ter vários ativos por tipo de ticket. [F](https://support.zendesk.com/hc/en-us/articles/5447690090138-About-custom-layouts-with-layout-builder)
- Em Enterprise, contextual workspaces escolhem o layout por marca, grupo de agentes ou formulário de ticket. [F](https://support.zendesk.com/hc/en-us/articles/5447690090138-About-custom-layouts-with-layout-builder)
- Ticket novo, não salvo, sempre abre no layout padrão. Layout customizado e filtros de knowledge só aplicam depois do submit e da reabertura. [F](https://support.zendesk.com/hc/en-us/articles/5447690090138-About-custom-layouts-with-layout-builder)
- Layouts ficam em Admin Center > Workspaces > Agent tools. [S](https://support.zendesk.com/hc/en-us/articles/5447837546138-Creating-custom-layouts-to-improve-agent-workflow)
- Configurações de conversa (Professional e acima): mensagens mais novas no topo ou embaixo, posição do composer e início colapsado. [S](https://support.zendesk.com/hc/en-us/articles/6070249202202)
- Fixos ou opcionais: conversa, customer context e campos não são removíveis, mas podem ir para o painel de contexto. Knowledge, side conversations e apps podem ficar em qualquer lugar. [S](https://support.zendesk.com/hc/en-us/articles/5447690090138-About-custom-layouts-with-layout-builder). Não confirmado no conteúdo lido.

### Inferences
- Um layout pode ser um JSON ordenado de componentes, com zona (principal ou contexto) e largura. Fica numa tabela, com regra de seleção por condições (marca, grupo, formulário) e precedência. O Vue renderiza a partir desse JSON. Isso segue o padrão Tailwind-only do projeto, sem CSS customizado.
- Para o Chatwoot, o layout exige refatorar componentes da tela da conversa. Antes de desenhar, conferir o que já é componente em `components-next/`.

### Gaps
- Não pesquisei tabs de ticket, composer (alternância entre resposta pública e nota interna, seletor de canal), toolbar nem painel de apps. Estão em aberto.
- Os componentes fixos ou opcionais não foram confirmados no conteúdo lido.

---

## Side conversations, child tickets, followers e menções

### Takeaway
Side conversations são threads separadas dentro do ticket, para conversar com um grupo ou com pessoas específicas, inclusive sem conta no Zendesk. Slack e Teams entram por apps próprios. Child tickets são sub-tickets atribuíveis a agente ou grupo, e podem ser roteados pelo omnichannel. A exigência de plano conflita entre fontes. Followers são agentes ou admins que recebem notificações. O comportamento exato de @menção em nota interna não ficou confirmado.

### Cited Findings
- Side conversations são espaços dentro do ticket para conversar com um grupo específico ou tratar de um assunto. Ficam armazenadas separadas do thread principal e podem incluir usuários sem conta. [S](https://support.zendesk.com/hc/en-us/articles/360001449588)
- Side conversations de Slack e Teams abrem um chat que volta ao ticket. Cada uma exige seu app: Slack for Zendesk Support e Zendesk for Microsoft Teams, ambos atualizados. [S](https://support.zendesk.com/hc/en-us/articles/360001449588)
- Child tickets são criados como side conversations e atribuídos a um agente ou grupo. Podem ser roteados pelo omnichannel. [S](https://support.zendesk.com/hc/en-us/articles/360001449588)
- E-mail no omnichannel inclui side conversations. [F](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
- Na API de side conversations, o campo `external_ids.targetTicketId` traz o ID do child ticket. [S](https://developer.zendesk.com/rest_api/docs/support/side_conversation)
- Side conversations ficam desligadas por padrão. Admin ativa em Admin Center > Workspaces > Agent tools > Side conversations. [S](https://support.zendesk.com/hc/en-us/articles/360001449588)
- Conflito de plano: um guia de terceiros diz que side conversations são só para Suite Professional, Enterprise ou Enterprise Plus. Outro diz que é preciso o add-on Collaboration para Support. [3P](https://www.eesel.ai/blog/zendesk-side-conversations) e [3P](https://www.getmacha.com/blog/zendesk-side-conversations-explained)
- Cliente não vê as threads de side conversation. Afirmação de terceiro. [3P](https://www.eesel.ai/blog/zendesk-side-conversations)
- Followers são usuários internos (agentes ou admins) que recebem notificações do ticket. Agentes e admins podem adicioná-los. [S](https://support.zendesk.com/hc/en-us/articles/4408835971866)
- Conflito sobre menção: o artigo diz que @menção coloca o agente na lista CC. CC não pode ser adicionado a resposta com nota interna. CC só vê nota privada quando é nomeado nela. [S](https://support.zendesk.com/hc/en-us/articles/4408835971866). Um blog de terceiros diz que followers veem comentários públicos e privados. [3P](https://www.getmacha.com/blog/zendesk-followers-ccs-requesters)
- Um app de terceiros (Agent Ticket Chat) transforma menção em follower automático e salva o chat como nota interna. Afirmação do fornecedor. [3P](https://www.zendesk.com/se/marketplace/apps/support/1226340/agent-ticket-chat/)

### Inferences
- Side conversation é um thread filho do ticket, com lista de participantes e canal próprio, possivelmente externo. Child ticket é uma conversa filha com seu próprio assignee. No Chatwoot, avaliar se basta uma nota interna com menção mais uma conversa vinculada.
- Slack e Teams são integrações via webhook. Para o MVP, o e-mail externo basta.
- Menção em nota interna pode gerar notificação e follower automático. Decidir se follower recebe notas privadas, porque os dois comportamentos aparecem nas fontes.

### Gaps
- O comportamento de @menção em nota interna (follower ou CC) não ficou resolvido. Precisa de teste em conta trial.
- O plano exigido para side conversations (Suite Professional ou add-on Collaboration) não ficou resolvido.
- Ticket sharing entre contas não foi pesquisado.

---

## Detecção de colisão ("agent is viewing / typing")

### Takeaway
Não encontrei documentação oficial da Zendesk sobre detecção de colisão no Agent Workspace nesta rodada. Só há glossários de terceiros e uma thread de comunidade. Não afirmar o comportamento sem verificação em conta trial.

### Cited Findings
- Glossário de terceiro define o recurso como alerta quando outro agente está visualizando ou respondendo o mesmo ticket, para evitar respostas duplicadas. [3P](https://www.getmacha.com/glossary/agent-collision)
- Um blog de terceiros foca em prevenção: rotear por conteúdo e disponibilidade reduz sobreposição. Trata-se de opinião de fornecedor. [3P](https://www.eesel.ai/blog/zendesk-agent-collision-warning)
- Thread de comunidade: um moderador recomenda limpar cache e cookies, ou testar em janela privada, quando colisões não são detectadas. O moderador também cita extensões de navegador como causa possível. [S](https://support.zendesk.com/hc/ko/community/posts/4409507021722-How-do-we-avoid-two-agents-responding-to-client-at-the-same-time)

### Inferences
- Para replicar, usar presença efêmera: registro de "viewing" por conversa e usuário, com TTL, em Redis, e evento de "typing" sem persistência em banco. Essa é uma recomendação de design minha, não algo que a Zendesk documente.
- Verificar o que o Chatwoot já tem de presença e de indicador de digitação antes de criar algo novo.

### Gaps
- Quais indicadores a Zendesk mostra, quando aparecem e se bloqueiam o submit: não confirmado.

---

## Ações da toolbar, "Submit as" e atalhos de teclado

### Takeaway
Os atalhos de Agent Workspace documentados em release notes de 2025 cobrem aceitar conversa (Ctrl+Alt+Q), encerrar (Ctrl+Alt+E), trocar de tab (Ctrl+Shift+1 a 9) e Knowledge (Ctrl+Alt+K e Ctrl+Alt+L). Os atalhos de "submit as Pending/Solved" (Ctrl+Alt+P e Ctrl+Alt+S) vêm de um guia de 2014, anterior ao Agent Workspace. Não encontrei atalho de "Submit as" para o Agent Workspace. A lista completa fica no perfil do agente.

### Cited Findings
- Ctrl+Alt+Q aceita mensagem ou chat ao vivo. Ctrl+Alt+E encerra. Ctrl+Shift+1 a 9 troca de tab. Os atalhos foram criados para dar paridade com o Chat dashboard legado. [S](https://support.zendesk.com/hc/en-us/articles/9285444325914-Announcing-new-keyboard-shortcuts-in-Agent-Workspace)
- Ctrl+Alt+K mostra ou oculta a seção de Knowledge. Ctrl+Alt+L abre a busca de Knowledge. Fonte não confirmada, provavelmente o mesmo release note. [S](https://support.zendesk.com/hc/en-us/articles/9285444325914-Announcing-new-keyboard-shortcuts-in-Agent-Workspace)
- Ctrl+Alt+P (Pending) e Ctrl+Alt+S (Solved) para "submit ticket as": guia de 2014, anterior ao Agent Workspace. [3P](https://www.screensteps.com/articles/zendesk-keyboard-shortcuts)
- Comunidade (2022): a maioria dos atalhos legados não existia no Agent Workspace. A Zendesk respondeu que o assunto estava na lista de prioridades. [S](https://support.zendesk.com/hc/ja/community/posts/4482937748634-Keyboard-Shortcuts-Agent-Workspace)
- A lista completa de atalhos fica no perfil do agente, em "keyboard shortcuts". [S](https://support.zendesk.com/hc/ja/community/posts/4482937748634-Keyboard-Shortcuts-Agent-Workspace)

### Inferences
- Para o Chatwoot, os atalhos de ação (resolver, adiar, atribuir) devem ter escopo por tela e evitar colisão com atalhos do navegador. O prefixo Ctrl+Alt segue o padrão da Zendesk.

### Gaps
- Toolbar do ticket: merge, marcar como spam, criar follow-up e imprimir. Não pesquisado.
- "Submit as <status>" no Agent Workspace: não confirmado.

---

## Papéis, permissões e visibilidade por grupo

### Takeaway
Custom roles (controle granular de permissões) são um recurso de Enterprise, segundo a documentação de developer e de ajuda da Zendesk. Há conflito sobre o plano exigido. Os escopos de visibilidade de ticket (todos, grupo, organização, atribuídos) vêm de terceiros. Os roles predefinidos Staff, Team Leader e Advisor podem ser editados ou clonados.

### Cited Findings
- Contas Enterprise e acima podem dar acesso mais granular aos agentes por custom roles. [S](https://developer.zendesk.com/rest_api/docs/core/custom_roles)
- Escopo de visibilidade de ticket: todos, do grupo, da organização ou só atribuídos. [3P](https://www.getmacha.com/blog/zendesk-roles-permissions-explained)
- Agente com acesso restrito não vê tickets de grupos onde não está atribuído, mesmo com o título "agent". [3P](https://www.eesel.ai/blog/zendesk-roles-and-permissions)
- Roles Staff, Team Leader e Advisor podem ser editados ou clonados. [S](https://support.zendesk.com/hc/en-us/articles/203662026-Creating-custom-roles-and-assigning-agents-Enterprise-)
- A API de roles tem configurações para atribuir a qualquer marca ou grupo, e um nível de acesso a ações. Os valores exatos não ficaram claros no resultado. [S](https://developer.zendesk.com/rest_api/docs/core/custom_roles)
- Conflito de plano: Stitchflow diz que custom roles exigem Suite Professional ou acima, e que admins não podem ser restringidos. eesel diz que, em Enterprise, admins podem ser limitados. [3P](https://www.stitchflow.com/user-management/zendesk/manual) e [3P](https://www.eesel.ai/blog/zendesk-roles-and-permissions)

### Inferences
- No Chatwoot, roles (administrador e agente) e memberships de inbox e time já existem. Visibilidade "só atribuídos" é um filtro de escopo na consulta de conversas, dentro da policy. Verificar `app/policies` antes de desenhar.
- A regra de visibilidade deve ser aplicada no escopo da consulta, não só no front.

### Gaps
- A matriz completa de permissões (excluir, editar propriedades, gerenciar macros e views, comentário público) não foi lida.
- O plano exato para custom roles segue em conflito.

---

## IA: triage, Copilot e agentes (2026)

### Takeaway
O triage (Copilot) classifica tickets novos por topic (antes chamado intent), sentimento e idioma. Em junho de 2026, a Zendesk renomeou Intent para Topic e simplificou o setup. Fontes de terceiros relatam mudanças de empacotamento dos agentes de IA em 2026, incluindo a retirada do tier Essential. Esses pontos não foram confirmados em documento oficial.

### Cited Findings
- Mudanças do triage começam em 11 de junho de 2026. Intent passa a se chamar Topic. Contas que compraram Copilot antes dessa data mantêm o rótulo antigo até o fim de 2026. [S](https://support.zendesk.com/hc/en-us/articles/10879634516762-Announcing-intelligent-triage-that-s-simpler-to-start-scale-and-manage)
- Triage roda em tickets novos com comentário público e marca topic, sentimento e idioma. [3P](https://www.eesel.ai/blog/zendesk-ai-agents-intelligent-support-guide)
- Triage existe desde 2022, segundo a Zendesk. URL oficial do anúncio não confirmada. [S](https://futurumgroup.com/news/zendesk-announces-new-ai-intelligence-layer-to-power-seamless-interactions)
- Em 11 de maio de 2026, a Zendesk teria removido a divisão Essential e Advanced dos agentes de IA. O tier Essential teria fim em 31 de dezembro de 2026. O agente autônomo seria cobrado por resolução, e não por assento. [3P](https://www.eesel.ai/en/blog/zendesk-advanced-ai-use-cases). Não confirmado em fonte oficial.

### Inferences
- No Chatwoot, o triage poderia ser um job assíncrono que classifica a primeira mensagem pública e grava labels ou atributos customizados. Já existe o pipeline Captain no repositório (commits recentes de credenciais de custom tools). Vale conferir antes de criar algo novo.

### Gaps
- Não li documentação oficial de sugestão de macros, resumos, Knowledge capture nem preços.
- A pesquisa de IA foi superficial. Nada aqui é de fonte primária lida.

---

## Gaps globais e próximos passos

- Não lidos por fetch: developer.zendesk.com de Omnichannel routing e Agent Availability API; artigo de routing options (`4408831658650`); artigo de skills (`360000789788`, deu 404).
- Não pesquisados: composer e toolbar do ticket; tabs; merge; spam; follow-up; impressão; Knowledge capture; macros sugeridas; ticket sharing entre contas; matriz completa de permissões.
- Conflitos não resolvidos: lista de status padrão do agente; plano de side conversations; comportamento de @menção (follower ou CC); plano de custom roles.
- Recomendação de próxima rodada: (a) ler a API de omnichannel e de agent availability; (b) ler routing options e skills por outra URL, se houver; (c) testar em conta trial os status padrão, o comportamento de menção e a detecção de colisão; (d) mapear o código atual do Chatwoot para auto-assignment, presença e policies antes de propor implementação.
- Observação de escopo: o CLAUDE.md do projeto prevê overlay `enterprise/`. Segundo a memória do projeto, o fork não tem `enterprise/`. Recursos que o Zendesk limita a planos superiores (custom queues, custom roles, layouts ativos em paralelo) exigem decisão de produto sobre onde implementar.
