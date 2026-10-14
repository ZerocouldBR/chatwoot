# Segurança, LGPD e auditoria (telefonia, tickets, IA e automações)

Versão 1, de 2026-10-13 (agente A1). Complementa os controles S1–S14 de `DESIGN-MIGRACAO.md` §6 (plataforma) e `INTEGRACAO-55PBX.md` §10 (ponte). Aqui: o que muda com sd-ops, gravações, IA, URA e n8n. Texto para **validação jurídica** do cliente (não é parecer jurídico).

## 1. Inventário de dados pessoais (novos fluxos)

| Dado | Origem | Onde fica | Finalidade | Retenção proposta |
|---|---|---|---|---|
| Telefone (E.164) | 55PBX, Chatwoot | `ops.calls` (cifrado em repouso pelo volume/disco), contato Chatwoot | identificar o cliente, retorno | enquanto houver relação + 5 anos (prazo prescricional consumerista — validar) |
| CPF/CNPJ digitado na URA (`call_document`) | 55PBX | `ops.call_events` (campo **cifrado na aplicação**), nunca em log/stream | identificação na URA | 90 dias no bruto; depois só hash para correlação |
| Pedido digitado na URA | 55PBX | `ops.calls` | localizar reserva | igual ao ticket |
| Gravação de voz | 55PBX → storage privado | `recordings/<tenant>/...` (0600) ou bucket privado | qualidade, defesa em reclamações, QA | **proposta: 1 ano**, depois exclusão automática (configurável; o Zendesk guardava só o link) |
| Transcrição e resumo | qa-pipeline (A3) | schema `qa` | QA, histórico do atendimento | igual à gravação; resumo aprovado vira nota no ticket (retenção do ticket) |
| Avaliação de QA do agente | qa-pipeline | schema `qa` | gestão de desempenho (dado do **empregado**) | 2 anos; acesso restrito a QA/supervisor/o próprio agente |
| Payload bruto 55PBX | webhook | `ops.webhook_inbox` | auditoria e reprocessamento | 30 dias (`RETENTION_DAYS`), igual à pbx-bridge |
| Sessão CTI | sd-ops | `ops.cti_sessions` (só SHA-256) | autenticação | 8 h máx. |
| Logs técnicos | todos | stdout/arquivo com rotação | operação | 30 dias, **mascarados** |

## 2. Base legal (proposta para validação)

| Tratamento | Base legal sugerida (LGPD art. 7º) | Observação |
|---|---|---|
| Registro da ligação e ticket | execução de contrato / procedimentos preliminares (V) | atendimento ao cliente da B2B |
| Gravação de chamadas | legítimo interesse (IX) com aviso na URA, ou cumprimento de obrigação (II) se houver exigência setorial (Decreto do SAC 11.034/2022 trata de gravação para SAC regulado — **verificar aplicabilidade**) | **não depender só de consentimento**; aviso "esta ligação pode ser gravada" na URA |
| Transcrição/QA por IA | legítimo interesse (IX) com teste de balanceamento (LIA) | minimização, sem decisão automatizada sobre o cliente; a nota de QA é recomendação (art. 20 — revisão humana) |
| Avaliação do agente | legítimo interesse / execução do contrato de trabalho | transparência ao empregado (política interna) |
| WhatsApp pós-atendimento e CSAT | consentimento (opt-in) para mensagens ativas + política da Meta | atributo `sd_whatsapp_optin` obrigatório; WF05/WF07 não enviam sem ele |
| E-mail de protocolo | execução de contrato | só protocolo e status, sem dados sensíveis |

## 3. Controles técnicos

| # | Controle | Implementação / evidência esperada |
|---|---|---|
| L1 | HTTPS em todas as rotas públicas; HSTS | Traefik `websecure` + Let's Encrypt (padrão da VPS) |
| L2 | Tokens só no backend | credenciais 55PBX, Chatwoot, STT/LLM em variáveis/secret do Swarm; n8n só por *credentials*; validador dos workflows recusa segredo no JSON (`tools/validate_workflows.py`) |
| L3 | Rotação e revogação | tokens de serviço com hash e lista (`SDOPS_SERVICE_TOKENS`); segredo do webhook rotacionável (2 ativos durante a troca); token do usuário de integração do Chatwoot regenerável (`provision_55pbx.rb --rotate-token --show-token`, mostrado só no terminal); perfis de escopo do token de serviço (`new-service-token n8n`, `CTI_AUTH.md` §3) |
| L4 | Autenticação de entrada | 55PBX: segredo no caminho + header `token` + IP; Chatwoot: HMAC + timestamp; URA: token fixo + IP + rate limit; n8n→sd-ops: Bearer com escopo; sd-ops→n8n: Header Auth + HMAC |
| L5 | RBAC e tenant | `integrations/CTI_AUTH.md` §4–§5; acesso cruzado devolve 404; teste do cenário 25 |
| L6 | Gravações | storage privado; URL assinada de 300 s amarrada a usuário/tenant; registro `recording.url_issued`/`recording.accessed`; a URL da 55PBX nunca vai ao cliente nem ao n8n; agente só ouve as próprias chamadas/tickets |
| L7 | SSRF | download só de `*.55pbx.com`/`*.55pbx.com.br`, sem redirect, limite de tamanho, IPs privados bloqueados |
| L8 | Mascaramento | logs, stream `sd:events` (`number_masked`), alertas do n8n (sem telefone/CPF), mensagens ao n8n sem payload bruto |
| L9 | Rate limiting | webhook 55PBX, sessão CTI (10/min/IP), URA (por ANI/IP), API (por token) |
| L10 | Criptografia em repouso | disco da VPS cifrado (provedor) **ou** volume LUKS; campos sensíveis (`call_document`, URL original da gravação) cifrados na aplicação (chave em secret, rotação anual) |
| L11 | Backup e restauração | `pg_dump` diário do `servicedesk_ops` + storage de gravações; cópia off-site; **teste de restauração mensal** (RUNBOOK §5) |
| L12 | Eliminação | jobs de retenção (bruto 30 dias, gravação 1 ano, documento URA 90 dias) com relatório; pedido do titular: `DELETE` lógico + expurgo físico em 30 dias, registrado em `audit_events` |
| L13 | Auditoria | `ops.audit_events`: login CTI, falha de autenticação, emissão/uso de URL de gravação, mudança de estado, reprocessamento, exportação, consulta URA, alteração de regras/papéis |
| L14 | Revisão de webhooks | inventário dos webhooks (55PBX, Chatwoot, n8n) com dono, segredo e data de rotação; desligar o access log do Traefik nas rotas com segredo no caminho |
| L15 | Dashboard App | o Chatwoot envia contexto por `postMessage('*')`: o sd-console valida `event.origin` e não confia no `currentAgent` (sessão própria) |

## 4. IA: regras específicas

1. **Minimização:** antes do LLM, mascarar CPF, cartão, e-mail e telefone na transcrição (regex + revisão); não enviar dados financeiros sensíveis nem senhas. O áudio só vai a um provedor externo se a política aprovada permitir; alternativa local (Whisper) em `COST_ESTIMATE.md`.
2. **Sem treino:** usar planos pagos/API com "não uso para treino" (Gemini pago declara isso [verificado]; OpenAI: confirmar no contrato do cliente); registrar provedor, modelo, versão do prompt e da rubrica em cada avaliação.
3. **Sem inferências proibidas:** não inferir saúde, emoção, intenção ou características pessoais pela voz (prompt mestre §8.4); critérios não verificáveis = "não aplicável".
4. **Revisão humana:** resumo vira nota interna **revisável**; nota de QA é recomendação; contestação e reavaliação pelo console de QA.
5. **Transparência:** aviso ao cliente na URA (gravação e uso para qualidade) e política interna para os agentes.

## 5. n8n

- Credenciais apenas em *credentials* do n8n (placeholders `REPLACE_*` nos JSON).
- Workflows importados **inativos**; WF05/WF06/WF07 com `dry_run=true` até aprovação.
- Alertas de operação vão para uma conversa interna do ServiceDesk, sem dados pessoais.
- Anti-loop: `X-SD-Origin`, `caused_by`, `sd_origin`, `Idempotency-Key` (ver `integrations/WEBHOOK_CONTRACTS.md`).
- O webhook do WF08 (Chatwoot → n8n) usa segredo longo no caminho (o Chatwoot não envia header customizado); restringir por IP de origem no proxy do n8n se possível.

## 6. Fornecedores (operadores) a registrar no inventário/DPA

| Fornecedor | Dados | Pendência |
|---|---|---|
| 55PBX | telefonia, gravações, URA, contexto do Dashboard App (se o webphone for embutido) | DPA; autenticação e retenção das gravações; URL sem token com telefone no caminho (`INTEGRACAO-55PBX.md` §10 item 1) |
| Provedor de STT/LLM escolhido | áudio e/ou transcrição mascarada | DPA, região, não uso para treino |
| Provedor da VPS de produção | tudo | contrato, região (preferir Brasil ou adequação), criptografia de disco |
| Meta (WhatsApp) | mensagens | termos e templates |
| Google Workspace | e-mail | já operador hoje |

## 7. Riscos abertos

| Risco | Severidade | Tratamento |
|---|---|---|
| Gravação acessível por URL previsível sem autenticação (se a 55PBX liberar só por IP) | Alta | confirmar com a 55PBX; nossa cópia com acesso controlado; não exibir a URL original fora de nota privada |
| Token pessoal do Chatwoot colado no CTI (`CTI_AUTH.md`) | Média | só em memória, troca por sessão curta, rate limit; avaliar SSO futuro |
| Avaliação automatizada de empregados | Média | política interna, revisão humana, contestação |
| VPS compartilhada (`ia4co-old`) para homologação com dados reais | Alta | homologação com dados mínimos; produção em VPS dedicada |
