# Gap analysis: Zendesk Support + Talk (B2B Reservas) × ServiceDesk (Chatwoot CE + 55PBX + sd-ops)

Versão 1, de 2026-10-13 (agente A1, passo 3 do prompt mestre). Aproveita o que as rodadas anteriores já entregaram (documentos citados entre parênteses). Classificação:

- **CFG** configuração ou importação (já existe no Chatwoot CE ou nos nossos scripts);
- **INT** integração (55PBX, n8n, Google, Meta);
- **DEV** desenvolvimento (fork MIT, sd-ops, sd-console);
- **FORN/CLI** depende do fornecedor ou do cliente.

Estado: ✅ feito e testado · 🟡 feito, só staging/dev/mock · 🔨 em desenvolvimento nesta rodada · ⏳ não iniciado.

## 1. Atendimento e tickets

| Função Zendesk | Classe | Estado | Onde / evidência | Lacuna restante |
|---|---|---|---|---|
| Ticket com nº preservado | CFG+DEV | 🟡 | `display_id` = ID Zendesk (`IMPORTACAO.md`), staging | carga na demo (`RUNBOOK-CARGA-DEMO.md`) |
| 11 status personalizados | DEV | 🟡 | status canônico + `zd_status` (`CAMPOS.md` §2), tokens de status (L1), ação `set_ticket_status` (G2, `M5-MACROS-ACOES.md`) | máquina de estados de negócio (Novo→…→Encerrado) com auditoria: **sd-ops** (`TICKET_DOMAIN.md`) |
| Protocolo legível / digitável na URA | DEV | 🔨 | — | sd-ops (A2) + endpoint URA |
| Campos (67) e formulários (3) | CFG+DEV | 🟡 | 81 atributos, formulários estáticos e condicionais (L3) | formulário obrigatório ao resolver (M1) |
| Lista em tabela, views com contador | DEV | 🟡 | L2 (tabela), 83 filtros salvos (`REGRAS-VIEWS.md`) | views compartilhadas por time (M3) |
| Painel de propriedades / Agent Workspace | DEV | 🟡 | L3 + G1 (`LAYOUT-WORKSPACE.md`) | aprovação visual |
| Macros (325) | CFG+DEV | 🟡 | 143 macros + respostas prontas; macro preenche o editor; ações novas (G2) | conversões parciais (149) |
| Gatilhos (138) e automações por tempo (13) | CFG+DEV+INT | 🟡 | 29 completos, 81 parciais, 28 não convertíveis (`REGRAS-VIEWS.md`) | condições `update_type`/`role`/horário (M4); automações por tempo → job/n8n |
| SLA (3 políticas de 1ª resposta, horário comercial) | DEV | ⏳ | — | **sd-ops** (`ops.sla_*`) + WF10. Enterprise proibido |
| Tickets vinculados (pai/filho), N:N com chamadas | DEV | 🔨 | — | `ops.ticket_conversations`, `ops.ticket_calls` (sd-ops) |
| Auditoria de ticket | DEV | 🔨 | — | `ops.audit_events`/`ticket_events` (sd-ops) |
| Papéis (agente light, colaborador…) | DEV | ⏳ | especificação M13 (`PERMISSOES.md`) | implementação no fork |
| CSAT de e-mail/chat | CFG | ⏳ | nativo CE | ativação; WF07 para canal permitido |
| Central de ajuda (134 artigos) | CFG | 🟡 | importados em rascunho | publicação/segmentação |

## 2. Telefonia (Zendesk Talk via app 55PBX)

| Função | Classe | Estado | Onde | Lacuna |
|---|---|---|---|---|
| Registro de cada ligação como ticket (17,6 mil/ano) | INT+DEV | 🟡 | pbx-bridge (`INTEGRACAO-55PBX.md`), e2e mock 39/39 | migrar para sd-ops com ticket de negócio; campos oficiais `branch_mask`, `central_id`, `call_queue`, `call_transfer_id` não reconhecidos (`55PBX_API_MAPPING.md` §3.1) |
| Webhook em tempo real | INT+FORN | 🟡 | contrato `WEBHOOK_CONTRACTS.md` §1 | **cliente cadastrar URL; 55PBX informar formato/IPs** |
| Reconciliação por relatório | INT+FORN | 🟡 | poller Report02 (mock) | **chave Webservice** |
| Gravação tocando no ticket | INT+FORN | 🟡 | download+MP3 (mock) | **IP da VPS liberado em `vsa19.55pbx.com`** |
| Softphone dentro do helpdesk | FORN | ⏳ | Dashboard App + microfone no iframe (fork) | **`frame-ancestors` do `fone.55pbx.com`**; até lá extensão oficial |
| Pop-up/contexto CTI (cliente, tickets, histórico) | DEV | 🔨 | sd-console (A3) + `CTI_AUTH.md` (A2) | — |
| Click-to-call | INT+FORN+DEV | 🔨 | `POST /api/webphone/dial` documentado | **`client_code`, `api_key`, JWT** do suporte 55PBX |
| Perdidas/abandonadas com callback | DEV+INT | 🔨 | Report02 + WF03 | evento em tempo real de perdida **não garantido** (D3) |
| Transferências com histórico | DEV | 🔨 | `call_transfer_id` / `call_id_origin` | validar com ligação real |
| Pesquisa de satisfação telefônica | INT | ⏳ | `call_rating*`, Report02 `wh_question_*` | ativação no painel 55PBX |
| URA consultando protocolo | INT+DEV+FORN | ⏳ | contrato `WEBHOOK_CONTRACTS.md` §5 | configurar menu dinâmico (cliente) |
| Métricas de telefonia (TMA, TME, NS, abandono) | INT+DEV | 🔨 | Report01/02/03 → sd-console (A3) | chave Webservice |

## 3. IA e QA (não existe hoje no Zendesk; o n8n faz IA de atendimento)

| Função | Classe | Estado | Lacuna |
|---|---|---|---|
| Transcrição pt-BR com timestamps | DEV | 🔨 (A3) | gravações reais (IP) e decisão de provedor (`COST_ESTIMATE.md`) |
| Resumo IA como nota interna revisável | DEV | 🔨 (A3) | — |
| QA 0–100 com rubrica e evidência | DEV | 🔨 (A3) | — |
| Agentes de IA atuais (TNA, Cancelamento, Cobrança, CC) | INT | ⏳ | 34 workflows acoplados à API Zendesk (80 chamadas): API de compatibilidade M7 (`DESIGN-MIGRACAO.md`) — **fora do escopo desta rodada** |

## 4. Omnichannel

| Canal | Classe | Estado | Lacuna |
|---|---|---|---|
| E-mail (11 endereços via Google Workspace) | CFG+CLI | 🟡 (inboxes dormentes) | encaminhamento Google, SMTP de saída, DKIM/DMARC |
| WhatsApp (hoje Sunshine/Smooch no Zendesk) | INT+CLI | ⏳ | decisão: migrar número para Cloud API (nativo) ou manter durante transição; Evolution existe na VPS para outro sistema (não reaproveitar sessão de outro cliente) |
| Chat do site | CFG | ⏳ | widget nativo |
| Histórico WhatsApp/Messaging 2026 | DEV | 🟡 | `MENSAGERIA.md` (extração em curso) |
| Login Google (OAuth) | CFG+CLI | ⏳ | credenciais OAuth do Google Workspace do cliente |

## 5. Infra, segurança e operação

| Item | Estado | Lacuna |
|---|---|---|
| Imagem própria sem `enterprise/` (CI) | 🟡 (`CI-IMAGEM.md`) | push/visibilidade GHCR |
| Postgres/Redis da stack | ✅ (demo) | banco `servicedesk_ops` e Redis DB 7 a criar (`DEPLOYMENT.md`) |
| Storage de gravações | ⏳ | volume local (adapter); MinIO opcional |
| Backup testado, monitoração, LGPD | parcial | `SECURITY_LGPD.md`, `RUNBOOK.md` |
| VPS dedicada de produção | ⏳ CLI | `ia4co-old` é só demo/homologação (40 sistemas) |

## 6. Conclusão: o que é crítico para o MVP de dezembro

1. **Dependências externas** (sem elas nada de telefonia real é homologável): chave Webservice + exemplo de payload + cadastro do webhook; IP liberado para gravações; credenciais de discagem; `frame-ancestors` (opcional, há a extensão).
2. **Desenvolvimento**: sd-ops (domínio de ticket, chamadas, SLA, outbox) — A2; sd-console (CTI, QA, dashboards) e pipeline de QA — A3; workflows WF01–WF12 — A1 (esta rodada).
3. **Fora do caminho crítico da telefonia, mas crítico para o corte do Zendesk**: API de compatibilidade para os 34 workflows de IA (M7), e-mail (M8), M13 e carga final. Ver `ROADMAP.md`.
