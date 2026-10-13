# Canais de entrada de tickets e experiência do cliente final no Zendesk (estado em 2026)

Data de referência: 2026-10-13. Legenda: **[LEGADO]** = recurso antigo ou substituído; **[EAP]** = early access program; **[BETA]** = beta.

Método e limites: 15 chamadas de busca/leitura em support.zendesk.com e developer.zendesk.com. Apenas duas páginas foram abertas com WebFetch (threading de e-mail), e essas leituras devolveram respostas resumidas ao prompt, não o texto integral. Os demais fatos vêm de resumos de busca. Quando um resumo não identificou com certeza o artigo de origem, a URL indicada é a do tópico mais próximo e está sinalizada como "resumo de busca". Vários artigos são antigos (a própria busca os marcou como de anos atrás). Antes de transformar um fato em requisito de implementação, abrir a página e confirmar. Itens sem fonte estão em "Gaps".

## 1. Canal de e-mail: endereços, threading e como respostas viram comentários

### Takeaway
O Zendesk associa uma resposta de e-mail a um ticket por dois mecanismos: (a) os cabeçalhos `In-Reply-To` e `References` comparados com os Message-IDs de tickets existentes; e (b) um ID codificado entre colchetes no corpo, ou um alias no endereço de destino (`support+id<ID>@...`). Os dados de threading por cabeçalho são retidos por 30 dias.

### Cited Findings
- Zendesk compara as linhas `References` e `In-Reply-To` com os message IDs de tickets existentes; havendo correspondência, o e-mail entra como resposta àquele ticket. O artigo exige valores únicos por mensagem enviada: cada mensagem deve ter seu próprio Message-ID, não um valor fixo — [How can I troubleshoot threading issues?](https://support.zendesk.com/hc/en-us/articles/4408821051034-How-can-I-troubleshoot-threading-issues-)
- Um ID codificado no formato de exemplo `[1G7EOR-0Q2J]` em qualquer corpo de e-mail pode vincular a resposta ao ticket; o ID precisa estar entre colchetes. As notificações geradas pelo Zendesk incluem esse ID por padrão — [How can I troubleshoot threading issues?](https://support.zendesk.com/hc/en-us/articles/4408821051034-How-can-I-troubleshoot-threading-issues-)
- O ID também pode vir no endereço de destino como alias, por exemplo `support+id1G7EOR-0Q2J@<subdomínio>.zendesk.com`. Funciona sem outras referências, mas só para endereços de suporte hospedados pelo próprio Zendesk, não para endereços externos — [How can I troubleshoot threading issues?](https://support.zendesk.com/hc/en-us/articles/4408821051034-How-can-I-troubleshoot-threading-issues-)
- Os dados de threading por cabeçalho são mantidos por "30 days"; uma resposta a uma thread mais antiga não é conectada por cabeçalho — [How can I troubleshoot threading issues?](https://support.zendesk.com/hc/en-us/articles/4408821051034-How-can-I-troubleshoot-threading-issues-)
- Causas de threading errado documentadas: Message-ID ou In-Reply-To fixo em sistema emissor (e-mails não relacionados caem no mesmo ticket); ID de outro ticket colado no corpo ou no template; resposta a uma mensagem antiga, frequentemente em um follow-up ticket, que cai no ticket original — [How can I troubleshoot threading issues?](https://support.zendesk.com/hc/en-us/articles/4408821051034-How-can-I-troubleshoot-threading-issues-)
- Correção recomendada: copiar o conteúdo para uma nova mensagem enviada ao mesmo endereço Reply-To; diagnosticar na aba "Source" do e-mail original (Message-ID, In-Reply-To, References) — [How can I troubleshoot threading issues?](https://support.zendesk.com/hc/en-us/articles/4408821051034-How-can-I-troubleshoot-threading-issues-)
- Cada brand tem um subdomínio e um e-mail de suporte padrão; é possível criar mais endereços de suporte por brand — [Adding email support addresses for multiple brands](https://support.zendesk.com/hc/en-us/articles/4408836507162-Adding-email-support-addresses-for-multiple-brands)
- Um e-mail enviado a vários endereços de suporte gera apenas um ticket (resumo de busca sobre multibrand) — [Adding email support addresses for multiple brands](https://support.zendesk.com/hc/en-us/articles/4408836507162-Adding-email-support-addresses-for-multiple-brands)
- Threading simplificado: o outbound não inclui mais imagens inline de e-mails anteriores do usuário. As notificações mostram só o comentário mais recente, via `{{ticket.latest_comment_html}}` (para agentes inclui comentários privados; para usuários final, só o último público) ou `{{ticket.latest_public_comment_html}}` (último público para ambos). Ambos incluem anexos. Contas criadas após 15/06/2022 já usam o threading simplificado — [Implementing simplified email threading for email applications](https://support.zendesk.com/hc/en-us/articles/4552860143514-Implementing-simplified-email-threading-for-email-applications)

### Inferences
- O padrão mais robusto documentado é o ID explícito no corpo ou no alias do endereço, com cabeçalhos como sinal secundário. Cabeçalhos sozinhos são frágeis por causa da janela de 30 dias e dos Message-IDs estáticos de sistemas externos.
- Para o fork: confirmar no código atual como o e-mail de entrada é associado a conversas antes de propor mudança. Essa checagem não foi feita nesta pesquisa.

### Gaps
- Encaminhamento (forwarding) de um domínio de cliente para o endereço do Zendesk versus endereço hospedado pelo Zendesk: não pesquisado.
- Formato exato do ID (alfabeto, tamanho) em documentação oficial: só há exemplo observado.
- Se o assunto (subject) participa do threading: a fonte lida não menciona.

## 2. Delimitador de resposta, templates HTML, CC e anexos

### Takeaway
O delimitador "##- Please type your reply above this line -##" (o Zendesk o chama de "email delimiter" ou "mail delimiter") é opcional e vem desligado por padrão. Um admin o ativa em Admin Center > Channels > Talk and email > Email e precisa incluir o placeholder `{{delimiter}}` no template HTML antes de `{{content}}`. Sem isso, as notificações novas trazem o thread inteiro. O ticket guarda só o texto acima da linha, e o e-mail completo fica acessível em "View original email".

### Cited Findings
- Delimitador desligado por padrão. Ativação: admin marca a opção "Mail delimiter" em Admin Center > Channels > Talk and email > Email — [Adding and removing the delimiter from email notifications](https://support.zendesk.com/hc/en-us/articles/4408821456922-Adding-and-removing-the-delimiter-from-email-notifications)
- O admin precisa adicionar `{{delimiter}}` no template HTML, antes de `{{content}}`. Zendesk avisa que pular esse passo faz as novas notificações incluírem o thread inteiro — [Adding and removing the delimiter from email notifications](https://support.zendesk.com/hc/en-us/articles/4408821456922-Adding-and-removing-the-delimiter-from-email-notifications)
- Texto do delimitador customizável, de 20 a 65 caracteres — [Adding and removing the delimiter from email notifications](https://support.zendesk.com/hc/en-us/articles/4408821456922-Adding-and-removing-the-delimiter-from-email-notifications)
- Notificações enviadas antes da ativação não têm o delimitador; respostas a elas continuam trazendo o thread inteiro — [Adding and removing the delimiter from email notifications](https://support.zendesk.com/hc/en-us/articles/4408821456922-Adding-and-removing-the-delimiter-from-email-notifications)
- O ticket mostra apenas o texto acima da linha, mas o Zendesk guarda o e-mail completo, acessível por "View original email" — [How can I remove the "Please type your reply above this line" from my outgoing email notifications?](https://support.zendesk.com/hc/en-us/articles/4408894166682-How-can-I-remove-the-Please-type-your-reply-above-this-line-from-my-outgoing-email-notifications)
- Para desligar: remover o `{{delimiter}}` e o CSS relacionado do template HTML — [How can I remove the "Please type your reply above this line" from my outgoing email notifications?](https://support.zendesk.com/hc/en-us/articles/4408894166682-How-can-I-remove-the-Please-type-your-reply-above-this-line-from-my-outgoing-email-notifications)
- Templates de notificação são customizados com placeholders de conteúdo do ticket (ex.: `{{ticket.latest_comment_html}}`, citado na seção 1) — [Customizing your email notifications](https://support.zendesk.com/hc/en-us/articles/203663236-Customizing-templates-for-your-email-notifications) (resumo de busca)
- CC em formulário web / Help Center: o admin habilita a opção CC por help center; um usuário logado pode incluir múltiplos e-mails separados por vírgula. Adicionar CC a ticket existente exige também um comentário no mesmo update — [Submitting and tracking requests in the help center Customer Portal](https://support.zendesk.com/hc/en-us/articles/4408846805530-Submitting-and-tracking-requests-in-the-help-center-Customer-Portal)
- A opção de CC é configurada em nível de conta e não pode ser restrita a usuários específicos, segundo resposta de engenharia em thread da comunidade (URL não capturada) — [Getting started with CC and followers for admins](https://support.zendesk.com/hc/en-us/articles/4408821501338-Getting-started-with-CC-and-followers-for-admins) (referência do tema; a resposta de engenharia não foi lida na íntegra)
- Anexos no outbound: o threading simplificado remove imagens inline de e-mails anteriores do usuário; os placeholders `latest_comment` incluem anexos — [Implementing simplified email threading for email applications](https://support.zendesk.com/hc/en-us/articles/4552860143514-Implementing-simplified-email-threading-for-email-applications)

### Inferences
- Como o delimitador depende de template, o corte do thread é uma decisão de configuração do admin, não um comportamento automático do parser. Para o fork, o equivalente seria tratar o corte no momento do parse do e-mail de entrada (usando o delimitador como marcador) e manter o e-mail original completo.
- CC de conta, sem restrição por usuário, sugere que a permissão de CC é uma configuração de conta, não de contato. Isso importa para B2B com muitos contatos por organização.

### Gaps
- Diferença detalhada entre followers e CC (artigo "Getting started with CC and followers for admins" não lido).
- Regras de anexos de entrada (tamanho, tipos, limites): não pesquisado.
- Layout HTML padrão do template (cabeçalho, rodapé, branding): não pesquisado.

## 3. Tickets suspensos e spam

### Takeaway
E-mails de remetentes não reconhecidos, bloqueados ou com alta probabilidade de spam são suspensos. Ficam como "held" (retidos), fora do Support, até um agente aceitar ou rejeitar. Itens não revisados são apagados após 14 dias. Acima de 99% de probabilidade de spam, o e-mail é rejeitado; abaixo disso, é suspenso.

### Cited Findings
- Um item retido "não é necessariamente spam", mas também não é ticket. Fica em limbo até alguém decidir; se ninguém revisar, é apagado automaticamente após 14 dias — [Understanding suspended tickets and spam](https://support.zendesk.com/hc/en-us/articles/4408889141146-Understanding-suspended-tickets-and-spam)
- Se o sistema exige cadastro de usuário, e-mails de remetentes não cadastrados são suspensos. A causa aparece como "Permission denied for unknown email submitter" em contas fechadas e como "Sender domain not on allowlist" em contas restritas — [Causes for ticket suspension](https://support.zendesk.com/hc/en-us/articles/4408828416282-Causes-for-ticket-suspension) (resumo de busca)
- Probabilidade de spam de 99% ou mais: o e-mail é rejeitado. Abaixo de 99%: suspenso para confirmação — [Understanding suspended tickets and spam](https://support.zendesk.com/hc/en-us/articles/4408889141146-Understanding-suspended-tickets-and-spam)
- Blocklist: remetentes bloqueados têm e-mails suspensos por padrão, mas é possível configurar para rejeitar. Allowlist não garante aceitação: se a autenticação do remetente falhar, entradas de allowlist (por domínio ou endereço) são ignoradas — [Setting your allowlist and blocklist to control email support requests](https://support.zendesk.com/hc/en-us/articles/4408886840986-Setting-your-allowlist-and-blocklist-to-control-email-support-requests) e [Understanding the allowlist and blocklist](https://support.zendesk.com/hc/en-us/articles/6136740916250-Understanding-the-allowlist-and-blocklist)
- Recuperar um e-mail retido ensina o filtro que o remetente é legítimo; pode ser preciso recuperar alguns antes de o sistema liberar os próximos automaticamente — [Understanding suspended tickets and spam](https://support.zendesk.com/hc/en-us/articles/4408889141146-Understanding-suspended-tickets-and-spam)
- Limitação relatada pela comunidade: a visão de suspensos não indica se um spammer reincidente já está bloqueado, então cada item "Detected as spam" precisa ser checado individualmente — [Feature Request: Suspended Ticket View - cause of suspension "Detected as spam"](https://support.zendesk.com/hc/en-us/community/posts/5469401090330-Feature-Request-Suspended-Ticket-View-cause-of-suspension-Detected-as-spam)
- Ticket recuperado de suspensos registra canal de auditoria `suspended_ticket` (ver seção 8) e não gera follow-up (ver seção 4) — [Ticket Audits](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_audits/) e [Creating a follow-up for a closed ticket](https://support.zendesk.com/hc/en-us/articles/4408883882522-Creating-a-follow-up-for-a-closed-ticket)

### Inferences
- Para B2B, a causa mais provável de suspensão é "remetente não cadastrado" em contas que exigem cadastro. O fluxo de suspensos funciona como fila de aprovação, não como descarte silencioso. Isso favorece uma fila de revisão com prazo de expiração.

### Gaps
- Lista completa de regras de spam (além do limiar de 99%) não confirmada.
- Ordem de avaliação entre allowlist, blocklist e autenticação de remetente (SPF/DKIM) não detalhada.
- Artigo de workflow para phishing com pedido de ação imediata (https://support.zendesk.com/hc/en-us/articles/9866500749850-Workflow-Managing-suspicious-phishing-tickets-asking-for-an-immediate-action) não lido.

## 4. Resposta a ticket fechado (follow-up)

### Takeaway
Zendesk não reabre um ticket fechado. Quando o solicitante responde, cria-se um follow-up ticket vinculado, com canal de relatório "Closed Ticket". Não encontrei opção oficial para desligar esse comportamento; a única referência é uma thread antiga da comunidade, que também sugere um workaround por trigger (não oficial).

### Cited Findings
- Ticket fechado mantém o status mesmo após resposta do cliente; o sistema abre um novo ticket de follow-up — [Creating a follow-up for a closed ticket](https://support.zendesk.com/hc/en-us/articles/4408883882522-Creating-a-follow-up-for-a-closed-ticket) e [Understanding follow-up tickets](https://support.zendesk.com/hc/en-us/articles/8421655952026-Understanding-follow-up-tickets)
- Copiados para o follow-up: tags e a maioria dos valores de campo. Não copiados: comentários, prioridade, tipo, assignee, organização, skills e external ID. Group e assignee não são copiados por padrão, mas o admin pode decidir copiá-los — [Including original group and assignee on follow-up tickets](https://support.zendesk.com/hc/en-us/articles/6937092811162-Including-original-group-and-assignee-on-follow-up-tickets) e [Understanding follow-up tickets](https://support.zendesk.com/hc/en-us/articles/8421655952026-Understanding-follow-up-tickets)
- Canal de relatório do follow-up: "Closed Ticket" — [Understanding follow-up tickets](https://support.zendesk.com/hc/en-us/articles/8421655952026-Understanding-follow-up-tickets)
- Resposta em side conversation de ticket fechado ou arquivado também gera follow-up, que começa com nota privada, então nada é enviado automaticamente ao solicitante — [Understanding follow-up tickets for side conversations](https://support.zendesk.com/hc/en-us/articles/4408837750170-Understanding-follow-up-tickets-for-side-conversations)
- Restaurar um ticket da visão de suspensos não gera follow-up — [Understanding follow-up tickets](https://support.zendesk.com/hc/en-us/articles/8421655952026-Understanding-follow-up-tickets) (resumo de busca)
- Agente pode criar o follow-up manualmente com o botão "Create follow-up" no Agent Workspace — [Creating a follow-up for a closed ticket](https://support.zendesk.com/hc/en-us/articles/4408883882522-Creating-a-follow-up-for-a-closed-ticket)
- Workaround de comunidade (não oficial, thread com cerca de 4,6 anos): trigger com condição "Update via Is Closed ticket" que define o follow-up como solved — [Disabling Re-open on Response to Closed Ticket?](https://support.zendesk.com/hc/en-us/community/posts/4420529320602-Disabling-Re-open-on-Response-to-Closed-Ticket)
- Diferença solved versus closed: fechado é o estado final; no portal do usuário, closed aparece como solved (ver seção 6) — [What is the difference between a solved ticket and a closed ticket?](https://support.zendesk.com/hc/en-us/articles/4408887712154-What-is-the-difference-between-a-solved-ticket-and-a-closed-ticket) (artigo não lido na íntegra)

### Inferences
- "Fechado é imutável, resposta vira ticket novo" preserva histórico e métricas do ticket original. O custo é que o follow-up não herda comentários, então o agente perde contexto sem ler o ticket anterior. Para o fork, essa é uma decisão de produto: herdar conversa, só vincular ou copiar resumo.

### Gaps
- Fechamento automático de tickets solved após N dias: não pesquisado.
- Artigo "What is the difference between a solved ticket and a closed ticket?" não lido na íntegra.

## 5. Formulário web ("Submit a request") e portal de requisições do usuário final

### Takeaway
O usuário final abre pedidos pelo Help Center ("Submit a request") e acompanha pelo Customer Portal: vê suas requisições, pode comentar, adicionar CC, reabrir um solved com follow-up e responder CSAT. Há visão de "Organization requests" (só para membros de organização compartilhada) e de requisições em que é CC, via API. A visibilidade pode ser limitada à brand ou unificada entre brands.

### Cited Findings
- Requesters abrem tickets pelo Help Center por padrão e depois tratam pelo Customer Portal. Podem acompanhar abertos e resolvidos, comentar, adicionar CC, reabrir solved com follow-up e enviar CSAT — [Submitting and tracking requests in the help center Customer Portal](https://support.zendesk.com/hc/en-us/articles/4408846805530-Submitting-and-tracking-requests-in-the-help-center-Customer-Portal)
- A visibilidade depende da configuração da conta: o usuário vê requisições de todas as brands no portal, ou só as da brand do help center em que está logado — [Submitting and tracking requests in the help center Customer Portal](https://support.zendesk.com/hc/en-us/articles/4408846805530-Submitting-and-tracking-requests-in-the-help-center-Customer-Portal)
- O link "Organization requests" em "My requests" aparece só para membros de uma organização compartilhada e mostra todas as requisições dessa organização. Com várias organizações, o usuário filtra por uma delas; filtros combinam em AND — [Submitting and tracking requests in the help center Customer Portal](https://support.zendesk.com/hc/en-us/articles/4408846805530-Submitting-and-tracking-requests-in-the-help-center-Customer-Portal)
- Botão "Follow organization" faz o membro receber notificações de requisições novas e alteradas da organização compartilhada; se o botão não existe, o admin precisa incluí-lo no tema — [Submitting and tracking requests in the help center Customer Portal](https://support.zendesk.com/hc/en-us/articles/4408846805530-Submitting-and-tracking-requests-in-the-help-center-Customer-Portal)
- Conceito de organização e grupo: [About organizations and groups](https://support.zendesk.com/hc/en-us/articles/4408886146842-About-organizations-and-groups) (não lido)
- Requests API para usuário final: `GET /api/v2/requests` é permitido a end users; ordenação por `updated_at` ou `created_at`; paginação por offset (`page`) ou por cursor (`page[size]`, `page[after]`, `page[before]`), não ambas — [Requests (ticket requests)](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket-requests/)
- `GET /api/v2/requests/ccd` lista as requisições em que o usuário autenticado é CC — [Requests (ticket requests)](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket-requests/)
- Usuário com identidade de e-mail não verificada, adicionada após 17/09/2017, recebe 403 ao acessar requisições — [Requests (ticket requests)](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket-requests/)
- Conflito de documentação: a página de Users sugere a Tickets API para listar tickets solicitados por um usuário, mas a Tickets API é para agentes e admins; a Requests API é para end users — [Users](https://developer.zendesk.com/api-reference/ticketing/users/users/) e [Tickets](https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/)
- Existe uma nova experiência de lista de requisições no portal, em [BETA] — [Using the new request list experience in the help center customer portal (Beta)](https://support.zendesk.com/hc/en-us/articles/4628113350170-Using-the-new-request-list-experience-in-the-help-center-customer-portal-Beta) (não lido)
- Doc de como fazer requisições em nome do usuário final: [Making API requests on behalf of end users](https://developer.zendesk.com/documentation/ticketing/using-the-zendesk-api/making-api-requests-on-behalf-of-end-users/) (não lido)

### Inferences
- "Organization requests" (ver os pedidos da organização, não só os próprios) é o requisito central de um portal B2B. É uma permissão de organização, não de contato individual. Isso casa com o modelo de organização que o fork já deve ter.
- O endpoint de listagem não filtra por canal (`via`), então filtros por canal seriam feitos no cliente. Esta última parte é inferência a partir dos parâmetros documentados.

### Gaps
- Lista exata do que o usuário final pode editar após o envio (campos, descrição, anexos): só há parcial (comentar, CC, follow-up, CSAT).
- Ticket forms (campos condicionais por formulário) e como o formulário escolhe o formato: não pesquisado.
- Confirmação de que o portal de requisições aparece igual em todas as brands: não verificado.

## 6. Status: visão do usuário final versus visão do agente

### Takeaway
O usuário vê um conjunto reduzido de rótulos. No mapeamento padrão do portal: Pending vira "Awaiting your reply"; New, Open e On-hold viram "Open"; Solved e Closed viram "Solved". Status customizados podem ter nome e descrição próprios para o solicitante, mas só se a opção de visão diferente estiver ativa para aquele status.

### Cited Findings
- Mapeamento no "My activities": Pending → "Awaiting your reply"; New, Open e On-hold → "Open"; Solved e Closed → "Solved". Status customizados podem aparecer na coluna de status ao lado dos do sistema — [What are the customer portal ticket statuses?](https://support.zendesk.com/hc/en-us/articles/4408825864858-What-are-the-customer-portal-ticket-statuses)
- Para um status customizado ter rótulo próprio para o usuário, o admin marca "Show end users a different view" e define nome e descrição para o solicitante. Se a opção estiver desligada, agentes e usuários veem o mesmo texto — [Creating custom ticket statuses](https://support.zendesk.com/hc/en-us/articles/4412575861018-Creating-custom-ticket-statuses)
- [LEGADO] On-hold aparecia como Open para o usuário. Hoje é possível criar status customizados na categoria On-hold para dar transparência ao cliente — [Adding the On-hold ticket status to Zendesk Support](https://support.zendesk.com/hc/en-us/articles/4408889282458-Adding-the-On-hold-ticket-status-to-Zendesk-Support) e [Creating custom ticket statuses](https://support.zendesk.com/hc/en-us/articles/4412575861018-Creating-custom-ticket-statuses)
- Ativação automática de status customizados foi anunciada — [Announcing automatic activation of custom ticket statuses](https://support.zendesk.com/hc/en-us/articles/7193972071834-Announcing-automatic-activation-of-custom-ticket-statuses) (não lido)
- Status de formulário (ticket forms) tem seu próprio artigo — [About form ticket statuses](https://support.zendesk.com/hc/en-us/articles/7755811560346-About-form-ticket-statuses) (não lido)

### Inferences
- O que determina o cálculo de métricas e a visão do usuário é a categoria do status (new, open, pending, on-hold, solved, closed), não o nome customizado. Para o fork, mapear status internos para três rótulos de usuário (aberto / aguardando você / resolvido) é o padrão confirmado pela Zendesk.

### Gaps
- A lista completa das categorias de status só foi inferida a partir da seção de métricas. O artigo "About the ticket lifecycle and ticket statuses" (https://support.zendesk.com/hc/en-us/articles/8263915942938-About-the-ticket-lifecycle-and-ticket-statuses) não foi lido.

## 7. Mensageria (Web Widget, Sunshine Conversations, WhatsApp)

### Takeaway
Mensagens de canais de messaging (web messaging e social messaging) viram tickets após ativação pelo admin. A conversa fica atrelada ao ticket e termina quando o ticket fecha, com possível atraso de até uma hora por causa de automações horárias. Não existe um status de ticket específico para messaging: usam-se Open, Solved e Closed.

### Cited Findings
- Após ativação por um admin, mensagens de canais de social messaging ou web messaging podem gerar tickets no Agent Workspace — [Routing messaging tickets and notifying agents](https://support.zendesk.com/hc/en-us/articles/4408829019162) (resumo de busca)
- Conversa iniciada com bot ou AI agent cria um "AI agent ticket" a partir da primeira mensagem do cliente. A saudação inicial do bot não entra no ticket. Enquanto a conversa com o bot continua, o ticket fica Open; ao escalar para humano, o histórico é inserido no ticket — [Understanding AI agent tickets for AI agent–only conversations](https://support.zendesk.com/hc/en-us/articles/9204149016346-Understanding-AI-agent-tickets-for-AI-agent-only-conversations)
- Pedido de atendente humano cria ticket sem atribuição, que aparece nas views "Unassigned tickets" e "All unsolved tickets". Ao fechar o ticket, o controle volta ao bot — [Understanding AI agent tickets for AI agent–only conversations](https://support.zendesk.com/hc/en-us/articles/9204149016346-Understanding-AI-agent-tickets-for-AI-agent-only-conversations)
- A conversa termina quando o ticket fecha. Automações de fechamento rodam de hora em hora, então a conversa pode continuar ativa até uma hora após o fechamento — [What happens when a user replies in messaging and the ticket is closed?](https://support.zendesk.com/hc/en-us/articles/5417918886426-What-happens-when-a-user-replies-in-messaging-and-the-ticket-is-closed) (resumo de busca)
- Relato de comunidade (sem resposta oficial): nova mensagem entra em ticket existente que não esteja Closed e tenha o mesmo conversationId e userId; caso contrário, cria novo ticket — resposta de comunidade, URL não capturada
- Usuário do Sunshine Conversations e usuário do Zendesk são entidades diferentes — [What is the difference between a user in Zendesk and a user in Sunshine Conversations?](https://support.zendesk.com/hc/en-us/articles/5851837582490-What-is-the-difference-between-a-user-in-Zendesk-and-a-user-in-Sunshine-Conversations) (não lido)
- Workaround documentado para obter o ticket a partir do conversation ID do Sunshine: guardar o ID em campo ou metadata via webhook, e limpar quando o ticket for solved ou closed — [Workflow: How to obtain a ticket ID from a Sunshine Conversation ID](https://support.zendesk.com/hc/en-us/articles/9677041375002-Workflow-How-to-obtain-a-ticket-ID-from-a-Sunshine-Conversation-ID) (resumo de busca)
- Relato de comunidade sem resposta: mensagens enviadas via API do Sunshine aparecem no chat, mas não no ticket — [Sunshine Conversation, how post message api to show that message in Zendesk Ticket](https://support.zendesk.com/hc/en-us/community/posts/4858249584282-Sunshine-Conversation-how-post-message-api-to-show-that-message-in-Zendesk-Ticket)
- Incidente de 25/10/2025 em Pods 15 e 19 (erros do SunCo e atrasos na criação de tickets de messaging), marcado como resolvido — [Service Incident - October 25, 2025](https://support.zendesk.com/hc/en-us/articles/9868796554394-Service-Incident-October-25-2025-Support-Agent-Workspace-Sunshine-Conversations-Pods-15-19-Errors-and-latency-with-ticket-creation-and-Messaging) (resumo de busca)
- [LEGADO] Web Widget (Classic), que coexiste com o messaging: [Providing omnichannel support using Web Widget (Classic) for Zendesk Suite](https://support.zendesk.com/hc/en-us/articles/4408844047898-Providing-omnichannel-support-using-Web-Widget-Classic-for-Zendesk-Suite) (não lido)
- Métricas e atributos de messaging: [Metrics and attributes for Zendesk messaging](https://support.zendesk.com/hc/en-us/articles/4724624097818-Metrics-and-attributes-for-Zendesk-messaging) (não lido)

### Inferences
- Para o fork, o modelo a replicar é a amarração conversa ↔ ticket por identificador de conversa e de usuário, com a regra de "ticket não fechado continua recebendo mensagens". Fechar o ticket encerra a conversa.
- O atraso de até uma hora no fechamento implica que a conversa pode aceitar mensagens depois do fechamento. Para o fork, vale avaliar fechamento síncrono.

### Gaps
- WhatsApp: não pesquisado especificamente; só o messaging genérico foi coberto.
- Voice e Talk em messaging: não pesquisados.
- SLA de messaging e tempo de resposta do usuário em messaging: só o nome da métrica foi visto.

## 8. Voz (Talk), API e metadado "via" (canal de origem)

### Takeaway
O objeto `via` registra o canal de origem de tickets, requisições e comentários. Valores confirmados nas fontes lidas: `mail`, `web`, `chat`, `web_service`, `system`, `rule` e `suspended_ticket`, além de um tipo `mobile`. Os valores literais para API e voz não foram confirmados.

### Cited Findings
- Via types: lista `mail` como exemplo e mostra `mobile` com via id 56 — [Via types reference](https://developer.zendesk.com/documentation/ticketing/reference-guides/via-types/)
- Exemplos de ticket com `"via": { "channel": "web" }` — [Tickets](https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/)
- Eventos de ticket com `"channel": "chat"` e `"channel": "web_service"` — [Ticket events](https://developer.zendesk.com/api-reference/webhooks/event-types/ticket-events/)
- Audits com `"channel": "suspended_ticket"` (ticket recuperado), `"system"` (notificações) e `"rule"` (mudanças automáticas via trigger, com a fonte do trigger) — [Ticket Audits](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_audits/)
- Comentários podem trazer um bloco `source` junto ao canal, por exemplo com origem de web widget (`"rel": "web_widget"`) — [Ticket Comments](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_comments/) (resumo de busca)
- A documentação de Tickets descreve as origens em prosa: e-mail, Help Center, chat, telefone, X, Facebook e API — [Tickets](https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/)

### Inferences
- Para o fork, manter um campo de canal de origem por ticket e por comentário, com subtipos de sistema (`system`, `rule`, `suspended_ticket`), permite relatórios e auditoria. Esse padrão é o que a própria API do Zendesk usa.

### Gaps
- Lista completa de valores (incluindo `api`, `voice`, `whatsapp`, `email`) não confirmada. A página de via types precisa ser lida na íntegra.
- Voz e Talk: não pesquisado. Não há fonte lida sobre como chamadas viram tickets.
- API: como tickets são criados pela API e se herdam `via` específico: não pesquisado.

## 9. Multi-brand (brands, help centers, endereços de suporte)

### Takeaway
Cada brand tem subdomínio, help center próprio (`<subdomínio>.zendesk.com/hc`) e endereço de e-mail de suporte padrão. Por padrão, a visibilidade de requisições fica restrita à brand, com opção de visão unificada. Os limites variam por plano.

### Cited Findings
- Ao criar uma brand, o subdomínio define a URL do help center e o endereço de e-mail de suporte padrão. Cada brand ganha seu endereço e pode ter mais — [Setting up multiple brands](https://support.zendesk.com/hc/en-us/articles/4408829476378-Setting-up-multiple-brands) e [Adding email support addresses for multiple brands](https://support.zendesk.com/hc/en-us/articles/4408836507162-Adding-email-support-addresses-for-multiple-brands)
- Limites por plano (resumo de busca sobre multibrand; conferir na página de planos): Suite Growth e Professional com 5 brands e 5 help centers; Suite Enterprise e Enterprise Plus com 300 de cada; Support Enterprise com Knowledge Professional com 5 brands e apenas 1 help center — [Creating a help center for one of your Support brands](https://support.zendesk.com/hc/en-us/articles/4408828794778-Creating-a-help-center-for-one-of-your-Support-brands) (artigo de origem não confirmado)
- Todos os help centers são acessíveis a todos os usuários finais, e o login pode ser obrigatório. Trocar de help center pede novo login, mas as credenciais são mantidas — [Setting up multiple brands](https://support.zendesk.com/hc/en-us/articles/4408829476378-Setting-up-multiple-brands) (resumo de busca)
- Brand sem help center: os links de ticket nas notificações quebram, então é preciso triggers separados para brands com e sem help center — [Multibrand resources](https://support.zendesk.com/hc/en-us/articles/4408833921306-Multibrand-resources) (resumo de busca)
- Visibilidade de requisições: por padrão restrita à brand do help center; contas com multibrand podem ativar visão unificada entre todos os help centers — [Submitting and tracking requests in the help center Customer Portal](https://support.zendesk.com/hc/en-us/articles/4408846805530-Submitting-and-tracking-requests-in-the-help-center-Customer-Portal)
- Conflito de fontes: um artigo diz que o usuário só vê tickets da brand do help center; outro diz que isso depende da configuração da conta. Vale a configuração real
- [LEGADO] Migração de Hub and Spoke para Multibrand: [Understanding the migration from Hub and Spoke to Multibrand](https://support.zendesk.com/hc/en-us/articles/4408829530266) (não lido)
- Template de e-mail com múltiplas brands: [Using the email template with multiple brands](https://support.zendesk.com/hc/en-us/articles/4408832356762) (não lido)

### Inferences
- Para B2B, visão unificada entre brands muda o modelo de isolamento. É preciso decidir se é requisito de produto antes de implementar.

### Gaps
- Triggers, formulários e views por brand: não pesquisados em detalhe.
- Web Widget por brand e configuração de canais por brand: não pesquisados.

## 10. CSAT (satisfação)

### Takeaway
Há dois modelos. O CSAT padrão, com automação que envia a pesquisa 24 horas após o status Solved, e o CSAT customizável, que estava em EAP para canais de ticket. O customizável exige desligar o CSAT legado e os triggers de CSAT customizados.

### Cited Findings
- A automação padrão envia a pesquisa 24 horas após o ticket ser marcado como Solved, não Closed — [Customizing when your customer satisfaction (CSAT) survey is sent](https://support.zendesk.com/hc/en-us/articles/4408886194202-Customizing-when-your-customer-satisfaction-CSAT-survey-is-sent) e [Workflow: How to send satisfaction surveys when tickets get solved](https://support.zendesk.com/hc/en-us/articles/4408887007386-Workflow-How-to-send-satisfaction-surveys-when-tickets-get-solved)
- Para trocar o atraso, edita-se a automação. Para substituí-la por trigger: desativar a automação de sistema e criar trigger com condições "status category changed to Solved" e "Satisfaction Unoffered", com ação "Satisfaction offered to requester" — [Workflow: How to send satisfaction surveys when tickets get solved](https://support.zendesk.com/hc/en-us/articles/4408887007386-Workflow-How-to-send-satisfaction-surveys-when-tickets-get-solved)
- Armadilha: usar "is" na condição de horas desde solved pode impedir o disparo; usar "greater than" ou "less than" — [Customizing when your customer satisfaction (CSAT) survey is sent](https://support.zendesk.com/hc/en-us/articles/4408886194202-Customizing-when-your-customer-satisfaction-CSAT-survey-is-sent)
- Por canal: e-mail recebe a pesquisa um dia após solved; web, mobile e social messaging exibem a pesquisa na interface logo após solved. A ação "offered to requester" não funciona com messaging — [Customizing when your customer satisfaction (CSAT) survey is sent](https://support.zendesk.com/hc/en-us/articles/4408886194202-Customizing-when-your-customer-satisfaction-CSAT-survey-is-sent)
- Janela de resposta padrão para e-mail: 28 dias — [Sending a CSAT survey to your customers](https://support.zendesk.com/hc/en-us/articles/7689997846554-Sending-a-CSAT-survey-to-your-customers)
- CSAT customizável [EAP]: o admin edita o título, escolhe escala de 2, 3 ou 5 pontos, escolhe resposta numérica, emoji ou texto livre, e define o rótulo de cada nota. Notas negativas podem disparar perguntas de follow-up. Pré-requisito: desligar o CSAT legado e triggers de CSAT customizados — [Using the customizable CSAT experience (EAP)](https://support.zendesk.com/hc/en-us/articles/6069688145306-Using-the-customizable-CSAT-experience-EAP) e [Announcing Customizable CSAT Configuration EAP](https://support.zendesk.com/hc/en-us/articles/6198976373530-Announcing-Customizable-CSAT-Configuration-EAP)
- Planos para o CSAT customizável: Suite Growth e acima, e Support Professional e acima (resumo de busca) — [Using the customizable CSAT experience (EAP)](https://support.zendesk.com/hc/en-us/articles/6069688145306-Using-the-customizable-CSAT-experience-EAP)
- Messaging: um artigo mais recente diz que pergunta, escala e rótulos podem ser customizados em messaging; um artigo mais antigo diz que o texto da pergunta não é configurável ali. O mais recente é provavelmente o atual — [About CSAT ratings in messaging](https://support.zendesk.com/hc/en-us/articles/4408832620570-About-CSAT-ratings-in-messaging) (conflito de fontes, verificar na Admin Center)
- Limitação relatada em comunidade (início de 2025): só é possível um survey para a instância inteira, não por brand. A Zendesk respondeu que pedidos de configuração e estilo por brand foram aceitos e estão no roadmap, sem data — [PRODUCT FEEDBACK: Customizable CSAT Survey](https://support.zendesk.com/hc/en-us/community/posts/8758471506714-PRODUCT-FEEDBACK-Customizable-CSAT-Survey)
- Em 2023, segundo relato da comunidade, a Zendesk declarou não ter planos de expandir a customização de CSAT e indicou apps de marketplace. URL da thread não confirmada; ver [CSAT Customization](https://support.zendesk.com/hc/en-us/community/posts/4408868188826-CSAT-Customization)
- Dashboard de surveys: [Accessing and viewing the Surveys dashboard](https://support.zendesk.com/hc/en-us/articles/7043759414042-Accessing-and-viewing-the-Surveys-dashboard) (não lido)
- Gestão de canais e regras de CSAT: [Managing your CSAT survey, channels, and rules](https://support.zendesk.com/hc/en-us/articles/8054625864602-Managing-your-CSAT-survey-channels-and-rules) (não lido)

### Inferences
- Para o fork, o padrão a replicar é o CSAT 24 horas após solved, disparado por trigger com flag de "oferecido" (Satisfaction Unoffered → Offered), para não reenviar a pesquisa. O atraso deve ser configurável.

### Gaps
- Comentário livre e motivos (reasons) de CSAT: não lidos. O artigo de CSAT para e-mail e messaging deve ser lido.
- Rótulos específicos do CSAT legado (good/bad): não confirmados nesta pesquisa.
- CSAT em views e relatórios: não pesquisado.
- Multilíngue de CSAT: artigo não lido (https://support.zendesk.com/hc/en-us/articles/4408885717402-Are-CSAT-surveys-multi-lingual).

## 11. Notificações padrão ao usuário final (recebido, comentário atualizado, solved)

### Takeaway
Não há fato verificado nesta pesquisa sobre os defaults de notificação ao usuário final (ticket recebido, comentário atualizado, solved). Só foram confirmados comportamentos correlatos: placeholders de template, delimitador e a pesquisa de CSAT.

### Cited Findings
- Notificações com link de ticket são geradas por triggers e automações padrão; o comportamento padrão dessas automações não foi lido — [About the standard Support automations](https://support.zendesk.com/hc/en-us/articles/4408835051546-About-the-standard-Support-automations) (não lido)
- Templates de notificação: [Customizing your email notifications](https://support.zendesk.com/hc/en-us/articles/203663236-Customizing-templates-for-your-email-notifications) (não lido)

### Inferences
- Nenhuma inferência confiável sobre os defaults de notificação. Não preencher com memória.

### Gaps
- Defaults de "ticket recebido", "comentário atualizado" e "solved" para o usuário final: não pesquisados. Ler os dois artigos acima antes de definir o padrão do fork.

## 12. Help Center integrado a tickets (sugestões de artigos, criação de artigos, autenticação, organizações)

### Takeaway
O formulário "Submit a request" sugere artigos conforme o usuário digita o assunto; a funcionalidade vem ativa, e o admin pode desligá-la no tema. Autoreplies de e-mail também podem incluir artigos. A criação de artigo a partir de ticket é uma ação do agente (article request), não do usuário final. Autenticação do usuário final não foi pesquisada.

### Cited Findings
- O formulário mostra artigos enquanto o usuário digita o assunto. Ele pode escolher um artigo em vez de enviar o pedido. A correspondência é feita pelo assunto, e a funcionalidade vem ligada por padrão; admins podem desligá-la nas configurações do tema — [Fine Tuning: Best Practices for Ticket Deflection](https://support.zendesk.com/hc/en-us/articles/4848867878682-Fine-Tuning-Best-Practices-for-Ticket-Deflection) (resumo de busca)
- Relatório de self-service: tickets desviados por um artigo sugerido no formulário contam como deflexão confirmada; visitas ao help center que terminam sem ticket contam como deflexão presumida. Só cobre tickets enviados pelo formulário do help center — [Fine Tuning: Best Practices for Ticket Deflection](https://support.zendesk.com/hc/en-us/articles/4848867878682-Fine-Tuning-Best-Practices-for-Ticket-Deflection) (resumo de busca; URL exata do dashboard não capturada)
- Ação de autoreply "Autoreply with articles": insere até três artigos mais relevantes no e-mail de resposta, com botões de feedback. Exige help center ativo. Respostas automáticas que tentam resolver a dúvida diretamente exigem o add-on Advanced AI — [Configuring email autoreplies to deflect requests](https://support.zendesk.com/hc/en-us/articles/4408825385242)
- Renomeações: Answer Bot passou a se chamar Zendesk bots; Article Recommendations passou a se chamar autoreplies. Artigos antigos ainda usam os nomes antigos — [Configuring email autoreplies to deflect requests](https://support.zendesk.com/hc/en-us/articles/4408825385242) (resumo de busca)
- Criação de artigo a partir de ticket: o agente, no painel de contexto, faz um "article request", que abre um novo ticket descrevendo o artigo desejado e com link para o ticket de origem. Esses tickets recebem prefixo no título e a tag `knowledge_request_article`, e começam sem atribuição. Elegível com Agent Workspace e Suite Growth ou Guide Professional e acima. O anúncio tem cerca de quatro anos — [Announcing Request an Article in Knowledge](https://support.zendesk.com/hc/en-us/articles/4972821936666-Announcing-Request-an-Article-in-Knowledge)
- Compartilhamento de requisições com organizações: ver seções 5 e 9

### Inferences
- Sugestão de artigo por assunto é o caminho de deflexão de menor custo para B2B. A métrica de deflexão depende de vincular visita sem ticket a ticket; para medir isso no fork, o registro de visita e o de ticket precisam ser associáveis.

### Gaps
- Autenticação do usuário final (login, SSO, JWT, sign-in obrigatório): não pesquisada. Só foi confirmado que o help center pode exigir login.
- Criação de artigo pelo próprio usuário final: nenhuma fonte encontrada. O que existe é a solicitação feita pelo agente.
- Sugestões de artigo dentro de messaging ou de AI agent: não pesquisadas.

## 13. Relatórios (Explore) e métricas de tempo

### Takeaway
Definições principais: First reply time (criação até a primeira resposta pública do agente); Full resolution time (criação até o último status Solved, sendo que reaberturas contam até o último solve); Requester wait time (soma do tempo em New, Open e On-hold, pausando em Pending); Agent wait time (soma do tempo em Pending). Existem variantes em horário comercial. As definições variam entre Explore, messaging e AI.

### Cited Findings
- First reply time: intervalo entre a criação do ticket e o primeiro comentário público do agente. Se o agente cria o ticket e já deixa um comentário público, o marco final passa para a próxima resposta pública — [About native Support time duration metrics](https://support.zendesk.com/hc/en-us/articles/4408834848154-About-native-Support-time-duration-metrics)
- Full resolution time: o ponto final é a última transição para Solved. Tickets reabertos medem até o último solve. Fechamento automático de um ticket não resolvido pode ser o ponto final; se o ticket for fechado por regra ou API, esse evento é o segundo marco — [About native Support time duration metrics](https://support.zendesk.com/hc/en-us/articles/4408834848154-About-native-Support-time-duration-metrics)
- Requester wait time: soma do tempo em New, Open e On-hold; pausa em Pending. Status customizados entram conforme a categoria a que pertencem — [About native Support time duration metrics](https://support.zendesk.com/hc/en-us/articles/4408834848154-About-native-Support-time-duration-metrics) e [What is the difference between first reply time and requester wait time metrics?](https://support.zendesk.com/hc/en-us/articles/4408843394842-What-is-the-difference-between-first-reply-time-and-requester-wait-time-metrics)
- Agent wait time: soma dos períodos em Pending — [About native Support time duration metrics](https://support.zendesk.com/hc/en-us/articles/4408834848154-About-native-Support-time-duration-metrics)
- Messaging: tempo entre cada mensagem do cliente e a resposta do agente, em segundos — [Metrics and attributes for Zendesk messaging](https://support.zendesk.com/hc/en-us/articles/4724624097818-Metrics-and-attributes-for-Zendesk-messaging) (resumo de busca)
- Variantes em horário comercial, em minutos (ex.: "Full resolution time - Business hours (min)") — [About native Support time duration metrics](https://support.zendesk.com/hc/en-us/articles/4408834848154-About-native-Support-time-duration-metrics)
- Exemplo de receita de Explore: tempo médio de resolução sem pending ou on-hold — [Explore recipe: Average ticket resolution time without pending or on-hold time](https://support.zendesk.com/hc/en-us/articles/4408830883610-Explore-recipe-Average-ticket-resolution-time-without-pending-or-on-hold-time) (não lido)
- Métricas de atividade e de desempenho do agente: [Analyzing your Support ticket activity and agent performance](https://support.zendesk.com/hc/en-us/articles/4408835846810-Analyzing-your-Support-ticket-activity-and-agent-performance) (não lido)

### Inferences
- Requester wait e agent wait só são corretos se o cálculo usar a categoria do status (não o nome). Para o fork, isso significa que o cálculo de tempo de espera do cliente depende do mapeamento de status em categorias, definido na seção 6.

### Gaps
- One-touch resolution, contagem de reaberturas e contagem de respostas do agente: não pesquisados com fonte.
- Fórmulas exatas (arredondamento, fuso horário, tratamento de reabertura parcial): não verificadas.
- Métricas de SLA e políticas de SLA: só listadas, não lidas.
