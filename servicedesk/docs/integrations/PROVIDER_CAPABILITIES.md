# Matriz de capacidades dos provedores (55PBX, Chatwoot CE, n8n)

Versão 1, de 2026-10-13 (agente A1). Insumo do A2 (sd-ops) e do A3 (sd-console). Atualizar a cada teste real.

**Regra:** nada aqui foi inventado. Cada linha tem fonte (manual oficial, página da referência ou teste nosso). O que não tem fonte está marcado como "não documentado" e vira pergunta para o fornecedor (§5).

## Legenda

| Código | Significado |
|---|---|
| **DOC** | Confirmada pela documentação oficial |
| **TESTE** | Confirmada por teste nosso (data e método na coluna Evidência) |
| **LIC** | Depende de licença ou plano |
| **FORN** | Depende de acesso, credencial ou liberação do fornecedor/cliente |
| **DEV** | Requer desenvolvimento nosso |
| **NS** | Não suportada / não documentada (não usar sem confirmação) |

Uma capacidade pode ter mais de um código (ex.: `DOC + FORN + DEV`).

## Fontes lidas

| # | Fonte | Como foi lida |
|---|---|---|
| F1 | Manual "Integração REST / Web Services" V2.0 — https://files.55pbx.com/manuais/integration_endpoint.pdf | PDF baixado em 2026-10-13, texto extraído (7 páginas) |
| F2 | Manual "Integração GET / Web Services" — https://files.55pbx.com/manuais/integration_webservice_get.pdf | PDF baixado, 16 páginas (resumo anterior em `docs/INTEGRACAO-55PBX.md`, revisado aqui) |
| F3 | Referência https://api-55pbx.readme.io (índice `llms.txt`, 54 páginas baixadas em Markdown/HTML) | Páginas citadas pelo slug: `getting-started-with-your-api`, `códigos-de-resposta`, `introdução` (discadora/auth), `introdução-3`, `objeto-de-envio-de-listas-1`, `autenticação-2`, `requisição-realizar-discagem`, `introdução-4`, `especificações-técnicas`, `objeto-de-resposta`, `introdução-1`, `autenticação`, `filtros-para-a-requisição`, `dados-da-ligação-report_0X`, `requisição-report_0X`, `introdução-5`, `especificação-técnica`, `especificação-técnica-get`, `introdução-6`, `ew`, `envio-de-mensagem`, `requisição-report_01-1` (SMS), `alvo-zendesk`, `criar-ticket-zendesk`, `atualizar-ticket-zendesk`, `requisição-whatsapp-api` |
| F4 | Central https://suporte.55pbx.com/support/solutions (artigos 151000180038 tokens, 151000179917 novo integrador, 151000180299 menu dinâmico, 151000180176 ramal, 151000180391 métricas, 151000180404 relatórios, 151000180054 pesquisa, pasta 151000407064 filas + 151000180387 callback, 151000180275 gravação de tela, 151000093801 recusada × abandonada, 151000180385 transferidas, 151000180137 tipos de transferência, 151000180388 tipos no extrato, 151000180229 webphone Chrome, 151000180008 uso por IP) | WebFetch em 2026-10-13 |
| F5 | Chatwoot: https://developers.chatwoot.com/llms.txt, API reference, Dashboard Apps, Voice Calling, Enterprise Edition | WebFetch + **código do fork v4.18.0** (`/opt/servicedesk-dev/chatwoot`), que prevalece sobre a doc online (a doc online acompanha versões mais novas) |
| F6 | n8n do cliente: exportação local de 219 workflows + `GET /healthz` e `GET /api/v1/workflows?limit=1` (só leitura) | 2026-10-13 |
| T  | Testes nossos (§4) | 2026-10-13 |

---

## 1. 55PBX

### 1.1 Eventos em tempo real ("Tempo real por URL")

| Capacidade | Status | Endpoint / configuração | Autenticação | Fonte | Risco / observação |
|---|---|---|---|---|---|
| Push HTTP para URL nossa a cada ligação | **DOC + FORN** | Painel: Integrações > Tempo real por URL. Método **PUT ou POST**, URL, "Chave (token)" opcional | Header **`token`** com a chave cadastrada (F1 p.5: "no headers o token (chave) de validação"; exemplo `{"token": "LKAG..."}`) | F1 p.3–5; F3 `especificações-técnicas`; F4 151000180038 | O nome do header só aparece no PDF (F1). O readme não repete. Confirmar com 1 evento real. Sem HMAC, sem timestamp: a chave é um segredo estático → combinar com segredo no caminho da URL + IP de origem |
| **Dois envios por ligação (inicial e final)** | **DOC (divergente)** | — | — | F1 p.6 "Fluxo de envio": "serão enviados obrigatoriamente dois push: 1º dados iniciais … 2º dados finais" | **Divergência:** F1 p.4 e F3 `objeto-de-resposta` dizem "a cada **final** de ligação (atendida)". Só um evento real dirá se o inicial existe. A máquina de estados aceita os dois cenários |
| Terceiro envio na transferência (`call_transfer_id` = id da nova ligação) | **DOC (só no PDF)** | — | — | F1 p.6 | `call_transfer_id` não aparece no readme (F3). Reconciliar pelo Report02 (`call_id_origin`) |
| Evento só para ligação **atendida** | **DOC (divergente)** | — | — | F3 `objeto-de-resposta` ("A cada final de ligação atendida") | Se for verdade, **perdidas/abandonadas não chegam em tempo real** → só pelo Report02 (poller). Testar com uma abandonada |
| Envio de SMS também gera push (`call_type` = sms) | **DOC** | — | — | F1 p.4 | Filtrar `call_type=sms` (não é ligação) |
| Campos de pesquisa de satisfação no evento (`call_rating*`) | **DOC** | — | — | F3 `objeto-de-resposta` | Não estão no PDF (F1). Validar no evento real |
| E-mail do ramal no evento (`branch_email`) | **DOC (só exemplo)** | — | — | F3 exemplo do `objeto-de-resposta` | Aparece no exemplo, não na tabela. É a melhor chave ramal→agente se vier |
| Política de retentativa da 55PBX se nosso endpoint falhar | **NS** | — | — | não documentado | Supor **sem retentativa**: responder 2xx rápido (só persistir) e reconciliar pelo Report02 |
| Assinatura/HMAC do corpo | **NS** | — | — | não documentado | Só token estático |
| IPs de origem dos webhooks | **FORN** | — | — | não documentado | Pedir à 55PBX para `ALLOWED_IPS` |
| Ordem garantida / ID de evento | **NS** | — | — | não documentado | Idempotência por chave determinística (`central_id`+`call_id`+fase+hash) — ver `EVENT_LIFECYCLE.md` |

### 1.2 Relatórios (Webservice GET / "Report")

| Capacidade | Status | Endpoint | Autenticação | Fonte | Risco |
|---|---|---|---|---|---|
| Report01 – métricas agregadas | **DOC + FORN** | `GET https://reportapi02.55pbx.com:50500/api/pbx/reports/metrics/{date_start}/{date_end}/{queue}/{number}/{agent}/report_01/{quiz_id}/{interval}/{timezone}` | Header **`key: <chave>`** (Integrações > Webservice (API) > + Adicionar, nome "key") | F2 p.4/11; F3 `autenticação`, `filtros-para-a-requisição`, `requisição-report_01` | Fórmulas de NS/abandono são da 55PBX (F4 151000180391) |
| Report02 – detalhe por ligação (reconciliação, perdidas, transferências) | **DOC + FORN** | mesmo path com `report_02` | `key` | F2 p.8/12; F3 `requisição-report_02` (OpenAPI: securityScheme apiKey header `key`) | **Divergência de path:** o OpenAPI do readme declara `/{date_start}/{date_end}/{queue}/{number}/{agent}/{report}/{quiz_id}/{timezone}` (sem `interval`) mas lista o parâmetro `interval`; o PDF e o exemplo usam 9 segmentos (com `interval`). Usar 9 segmentos (exemplo oficial) e testar |
| Report03 – operadores (logado, pausa, produtividade) | **DOC + FORN** | `report_03` | `key` | F2 p.9/13 | — |
| Report04 – ações de operador (login/pausa) | **DOC + FORN** | `report_04` | `key` | F2 p.10/14 | Dado repetido por fila do ramal (F2 obs.) |
| Report06 – intervalo detalhado | **DOC (só PDF)** | `report_06` + `interval` em minutos | `key` | F2 p.10 | Não há página no readme |
| Filtro por fila/agente específico | **DOC** | `queue_id`/`agent_id` no lugar de `all_queues`/`all_agent` | — | F3 `filtros-para-a-requisição` | IDs internos da 55PBX (não o nome) |
| Timeout recomendado 7200 s | **DOC** | — | — | F2 p.4; F3 `autenticação` | Consultas grandes são lentas → janelas curtas (≤ 3 h) no poller |
| Formato de data `Fri May 22 2020 00:00:00 GMT -0300` | **DOC** | — | — | F2/F3 | Datas de resposta em `DD/MM/AAAA` + hora local; `wl_time_attended` em ISO "Z" |
| Rate limit | **NS** | — | — | não documentado | Poller conservador (10 min) |
| Teste com chave real | **pendente (FORN)** | — | — | — | Sem chave ainda. Host responde (T1) |
| Transcrição de chamadas pela 55PBX | **DOC + LIC** | painel/relatórios | — | F4 151000180404 ("Call Transcription") | Sem API documentada. Não usar como fonte; STT nosso |

### 1.3 Discagem (click-to-call) e discadora

| Capacidade | Status | Endpoint | Autenticação | Fonte | Risco |
|---|---|---|---|---|---|
| Discar de um ramal logado no webphone para um número | **DOC + FORN** | `POST https://ws.55pbx.com:20500/api/webphone/dial` (texto da introdução) **ou** `.../api/pbx/webphone/dial` (campo `servers` do OpenAPI) | Headers **`client_code`**, **`api_key`** e **`Authorization: Bearer <JWT do cliente>`** | F3 `introdução-3`, `autenticação-2`, `requisição-realizar-discagem` | **Divergência de URL** (com/sem `/pbx`). **Origem do JWT não documentada** (não há endpoint de emissão para esta API). `client_code`/`api_key` só pelo suporte 55PBX. Testar com conta de homologação |
| Payload | **DOC** | `{"email": "<e-mail do ramal na 55PBX>", "phone": "+5511912345676"}` (E.164, ambos obrigatórios) | — | F3 `objeto-de-envio-de-listas-1` | E-mail **do ramal** (cadastro 55PBX), não do agente no Chatwoot → mapa ramal↔agente |
| Respostas | **DOC** | 200 `{"status":"OK","call_id":"...","message":"Ligação efetuada com sucesso"}`; 404 `{"status":"ERROR","email":"E-mail inválido."}` / `{"status":"ERROR","phone":"Telefone inválido"}`; 500 `{"error":"Usuário com requisição pendente."}` | — | F3 `requisição-realizar-discagem` | O `call_id` do 200 permite ligar a chamada ao ticket **antes** do evento do webhook |
| Pré-condição: ramal logado no webphone e sem pausa não-ativa | **DOC** | — | — | F3 `introdução-3` | UI do CTI deve mostrar o erro real |
| Discadora preditiva (listas/campanhas) | **DOC + FORN + LIC** | `https://ws.55pbx.com:20500/api/dialer/...` | `client_code` + `api_key` | F3 `introdução` (discadora), `inserção-de-contatos`… | Fora do escopo do MVP. Útil para callback em massa |
| Callback da fila (cliente digita opção) | **DOC + LIC** | painel (campanha de callback + lista) | — | F4 151000180387 | **Não documentado** se gera evento/relatório próprio. Callback nosso = tarefa + click-to-call |

### 1.4 URA / menu dinâmico (consulta de protocolo)

| Capacidade | Status | Detalhe | Fonte | Risco |
|---|---|---|---|---|
| URA chama API nossa (GET/POST/PUT/PATCH/DELETE) | **DOC + FORN** | Menu "Integração > Padrão 55PBX". Variáveis declaradas em "Configurar variáveis de envio", usadas na URL com `:nome`; corpo JSON simples ou form | F4 151000180299; F3 `especificação-técnica`, `especificação-técnica-get` | Configuração feita no painel pelo cliente |
| Autenticação da nossa API pela URA | **DOC** | Basic (`Authorization: Basic base64(user:pass)`), token fixo em header nomeado, Bearer, ou "token dinâmico" no corpo | F3 `especificação-técnica`; F4 151000180299 | Usar token fixo em header + IP de origem |
| Formato da resposta | **DOC** | 2xx com JSON; é "achatado" em 1 nível (`result_customer_firstName`); no menu as variáveis aparecem com prefixo `55pbx_` (`55pbx_nome`, `55pbx_email_0`) | F3; F4 | Respostas não-2xx = erro → URA segue rota de falha. Devolver só campos curtos e não sensíveis |
| Timeout da URA | **NS** | não documentado | — | Responder < 2 s |
| Bot de voz com streaming | **NS** | não há API de áudio em streaming | — | Fase posterior |

### 1.5 Gravações, webphone e outros

| Capacidade | Status | Detalhe | Fonte / evidência | Risco |
|---|---|---|---|---|
| URL da gravação no evento (`call_url_audio`) e no Report02 | **DOC** | Ex.: `https://sip1.55pbx.com/webphone/webphone-1534/AAAA/MM/DD/audio-...WAV`. No histórico do cliente: `vsa19.55pbx.com/webphone/webphone-3855/...` | F1, F2, F3; tickets Zendesk 2026 | URL **sem token** e com telefone no caminho (risco LGPD) |
| Download da gravação a partir do nosso servidor | **FORN** | `vsa19.55pbx.com` **não responde (time-out em 443/80)** da VPS nem do escritório | **TESTE T3** (2026-10-13) | Bloqueante para áudio/STT/QA. Pedir liberação do IP de saída da VPS |
| Autenticação da URL de gravação | **NS** | não documentado | — | Perguntar à 55PBX |
| Retenção/formato das gravações | **NS** | Ramal tem só "Gravar ligações" (liga/desliga) | F4 151000180176 | Copiar para storage nosso no evento final |
| Webphone `fone.55pbx.com` embutido em iframe no nosso domínio | **FORN** | CSP `frame-ancestors` lista Zendesk, Salesforce, Freshdesk, Movidesk… **não** `*.ia4co.com` nem o domínio final | **TESTE T2** (2026-10-13, `curl -I https://fone.55pbx.com`) | Pedir à 55PBX para incluir o domínio. Até lá: extensão oficial |
| Extensão oficial do Chrome ("55PBX Web Softphone", nova versão Lite) | **DOC** | Login com e-mail/senha da 55PBX; instalação pela Chrome Web Store ou Admin > Conta > Softphones | F4 151000180229 | Áudio fica 100% na 55PBX (caminho A) |
| Tipos de transferência (cega, assistida) | **DOC** | Webphone | F4 151000180137 | Sem detalhe de evento |
| Transferências identificáveis no relatório | **DOC** | `call_id_origin` ("ID Ligação de Origem") preenchido nas pernas transferidas | F4 151000180385; F2 p.8 | Base da reconciliação de pernas |
| Recusada × abandonada | **DOC** | Recusa = analista disponível recusou com o cliente na fila; abandono = cliente desistiu (pode ter havido recusas antes) | F4 151000093801 | **Recusa de operador não é perdida** |
| Valores de `type_call` no Report02 | **DOC parcial** | `call_attended`, `call_abandoned` aparecem nos exemplos | F2 p.12; F3 `requisição-report_02` | Lista completa **não documentada** (perguntar) |
| Pesquisa de satisfação telefônica (sim/não, nível, personalizado) | **DOC + LIC** | Resultados nos relatórios (`quiz_id`, `wh_question_*`) e `call_rating*` no evento | F4 151000180054; F3 | CSAT telefônico vem da 55PBX |
| Gravação de tela do agente | **DOC + LIC + FORN** | Admin > Ramais > Monitoria; app instalado com especialista 55PBX | F4 151000180275 | Opcional, fora do MVP |
| Restrição de uso por IP (conta 55PBX) | **DOC** | Admin > Configurações > Segurança > Habilitar uso por IP | F4 151000180008 | Pode explicar o bloqueio de `vsa19` |
| API de mensagens (WhatsApp/Chat/SMS via 55PBX) | **DOC + LIC** | `https://api1.55pbx.com:30901/ext/messages`; token de 1 h (`username`=central ID, `password`=token de API); limite 500 req/s | F3 `introdução-6`, `ew`, `envio-de-mensagem` | **Não usar**: WhatsApp fica no Chatwoot/Evolution (evita número duplicado) |
| "Criar/Atualizar Ticket Zendesk" (`https://api1.55pbx.com:30901/ext/incidents`) | **DOC** | Headers `Authorization` + `Integration` | F3 | Específico do Zendesk. Será desligado no corte |
| Novo integrador 55PBX (CRMs nativos) | **DOC** | Zendesk, Salesforce, HubSpot, SAP, Movidesk. **Sem Chatwoot e sem webhook genérico** | F4 151000179917 | Por isso a ponte própria |

---

## 2. Chatwoot (fork CE v4.18.0, sem `enterprise/`)

| Capacidade | Status | Endpoint / recurso | Autenticação | Fonte | Observação |
|---|---|---|---|---|---|
| API de aplicação (contatos, conversas, mensagens, atributos, etiquetas, atribuição, status) | **DOC + TESTE** | `/api/v1/accounts/{account_id}/...` (detalhe em `CHATWOOT_API_MAPPING.md`) | Header `api_access_token` (token de usuário ou de agent bot) | F5; e2e da pbx-bridge 39/39 (`INTEGRACAO-55PBX.md` §8) | Usuário de integração com papel **agente**, só na inbox 55PBX |
| Inbox do tipo API (canal "Telefone (55PBX)") | **DOC + TESTE** | `POST /inboxes` com `channel.type=api`; `Channel::Api` tem `webhook_url` e `secret` | idem | F5; provisionamento no staging (inbox 30) | — |
| Busca de contato por telefone | **TESTE (código)** | `GET /contacts/search?q=` faz `ILIKE` em nome, e-mail, **phone_number** e identifier | idem | `app/controllers/api/v1/accounts/contacts_controller.rb#search` | Busca por substring: conferir igualdade exata no cliente |
| Filtro de contatos/conversas por atributo | **DOC** | `POST /contacts/filter`, `POST /conversations/filter` | idem | F5 | Usado para achar conversa por `pbx_call_id` / `sd_ticket_id` |
| Webhooks de conta | **DOC + TESTE (código)** | Eventos: `conversation_status_changed`, `conversation_updated`, `conversation_created`, `contact_created`, `contact_updated`, `message_created`, `message_updated`, `webwidget_triggered`, `inbox_created`, `inbox_updated`, `conversation_typing_on/off` | Assinatura **HMAC-SHA256** em `X-Chatwoot-Signature: sha256=hex(HMAC(secret, "<ts>.<body>"))`, `X-Chatwoot-Timestamp`, `X-Chatwoot-Delivery` (quando o webhook tem `secret`) | `app/models/webhook.rb` (`ALLOWED_WEBHOOK_EVENTS`), `lib/webhooks/trigger.rb` | Sem retentativa no envio padrão (só erro tratado p/ bot/API inbox) → reconciliação periódica |
| Webhook da inbox API | **TESTE (código)** | `Channel::Api.webhook_url`, assinado com `inbox.channel.secret` | HMAC idem | `app/listeners/webhook_listener.rb` | Usado pela pbx-bridge (gatilho de atribuição) |
| Dashboard App (iframe na conversa) | **DOC + TESTE (código)** | Configurações > Integrações > Dashboard Apps (ou `dashboard_apps_controller`). Contexto via `postMessage` (`{"event":"appContext","data":{conversation, contact, currentAgent, customAttributes, theme}}`); o app pede com `chatwoot-dashboard-app:fetch-info` | Nenhuma: o iframe recebe dados do navegador; **o app precisa de sessão/autenticação própria** para chamar o sd-ops | F5; `Frame.vue` | `postMessage(..., '*')`: o app deve validar `event.origin`. `allow="microphone"` adicionado no fork (commit `3de5af7fa6`) |
| Voz nativa (Twilio Voice, WhatsApp Calling) | **LIC / NS** | Recurso premium ("Voice calling is a premium feature") | — | F5 artigo 1779863425 | **Não usar.** Sem SIP genérico/PBX de terceiros |
| SLA | **LIC (enterprise)** | — | — | F5 enterprise-edition ("SLA Management") | **Proibido** usar `enterprise/`. SLA no sd-ops (M6) |
| Papéis personalizados, auditoria, capacidade de agente | **LIC (enterprise)** | — | — | F5 | M13 próprio; auditoria no sd-ops para o domínio de ticket |
| Captain (IA) | **LIC** | — | — | F5 | IA no sd-ops/n8n |
| CSAT de conversa | **DOC (CE)** | Inbox > CSAT; `csat_survey_responses` | — | F5; código | CSAT de conversa ≠ CSAT telefônico |
| Relatórios de conversa (FRT, resolução) | **DOC (CE)** | `/api/v2/accounts/{id}/reports...` | admin | F5 | Telefonia vem da 55PBX |
| Central de ajuda (artigos) | **DOC + TESTE** | `POST /portals/{portal}/articles` | — | F5; 134 artigos importados | — |
| WhatsApp Cloud API (Meta) | **DOC + FORN** | Inbox WhatsApp | — | F5 | Migração do número (hoje Sunshine/Smooch no Zendesk). Evolution (`evolution_go`) já existe na VPS para outro sistema |
| E-mail (IMAP/SMTP, encaminhamento) | **DOC + FORN** | Inbox e-mail | — | F5 | 11 inboxes já criadas, dormentes |

## 3. n8n do cliente

| Capacidade | Status | Detalhe | Fonte |
|---|---|---|---|
| Instância acessível só desta máquina (Cloudflare) | **TESTE** | `GET /healthz` = 200 | T4 |
| API pública `X-N8N-API-KEY` (somente leitura neste projeto) | **TESTE** | `GET /api/v1/workflows?limit=1` = 200; workflows têm `activeVersionId`/`activeVersion` (versão 1.11x+/2.x do n8n). `/rest/settings` não expõe a versão | T4, F6 |
| Nós e versões em uso (base de compatibilidade dos WF01–WF12) | **TESTE (exportação)** | `webhook` 2/2.1, `httpRequest` 4.2–4.4, `code` 2, `if` 2.2–2.3, `switch` 3.2, `set` 3.4, `scheduleTrigger` 1.2, `respondToWebhook` 1.1–1.5, `executeWorkflow` 1.1, `postgres` 2.5–2.6 | F6 |
| Credenciais usadas hoje | **TESTE (exportação)** | `postgres` (722 nós), `zendeskApi` (115), `openAiApi`, `googleApi`, `googlePalmApi`, `httpHeaderAuth` (20), `telegramApi` | F6 |
| 55PBX no n8n | **TESTE (exportação)** | Só 1 workflow **inativo** cita 55PBX ("Tratamento Envio - V2"). A integração atual é 55PBX→Zendesk direta | F6 |

## 4. Testes executados (evidência)

| ID | Data | Teste | Resultado |
|---|---|---|---|
| T1 | 2026-10-13 | `curl https://{ws.55pbx.com:20500, reportapi02.55pbx.com:50500, api1.55pbx.com:30901}/` da VPS e do escritório | Todos respondem **404** (hosts vivos; rotas exigem path/credencial) |
| T2 | 2026-10-13 | `curl -I https://fone.55pbx.com` | 200; `frame-ancestors` **sem** nosso domínio |
| T3 | 2026-10-13 | `curl https://vsa19.55pbx.com/` da VPS e do escritório | **time-out** (000) |
| T4 | 2026-10-13 | n8n `GET /healthz`, `GET /api/v1/workflows?limit=1` | 200 / 200 |
| T5 | 2026-10-13 | pbx-bridge: pytest 50 passed, e2e DEV 39/39 (55PBX simulada) | ver `INTEGRACAO-55PBX.md` §8 — **mock**, não homologado com a 55PBX real |

**Nenhuma** capacidade da 55PBX foi homologada contra a conta real até agora (sem chave, sem webhook cadastrado, sem IP liberado).

## 5. Perguntas ao fornecedor 55PBX (pacote único, enviar ao suporte@55pbx.com.br)

1. "Tempo real por URL": há **dois** envios (inicial e final) ou só o final? Ligações **não atendidas/abandonadas** geram envio? Envio extra na transferência com `call_transfer_id`? Exemplo real de cada um (dados mascarados).
2. Nome exato do header da chave do webhook (o PDF diz `token`) e se há retentativa quando nosso endpoint responde erro/time-out.
3. IPs de origem dos webhooks e da URA dinâmica.
4. Semântica de `call_time` × `call_duration` × `call_total_time` (as descrições contradizem os exemplos — ver `55PBX_API_MAPPING.md` §3).
5. Lista completa de valores de `call_status`/`type_call`/`call_disconnection`.
6. Discagem: URL correta (`/api/webphone/dial` ou `/api/pbx/webphone/dial`), emissão de `client_code`, `api_key` e **como obter o Bearer JWT**.
7. Gravações: liberar o IP de saída da VPS em `vsa19.55pbx.com`; a URL exige autenticação? Por quanto tempo fica disponível? Formato (WAV PCM ou GSM)?
8. Incluir o domínio do ServiceDesk no `frame-ancestors` de `fone.55pbx.com`.
9. Timeout da URA dinâmica e limites de tamanho da resposta.
10. Rate limit do Report (reportapi02) e retenção máxima consultável.
