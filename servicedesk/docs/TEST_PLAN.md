# Plano de testes (30 cenários do prompt mestre §17)

Versão 1, de 2026-10-13 (agente A1). Responsáveis: **A2** = sd-ops (telefonia, tickets, SLA, outbox); **A3** = qa-pipeline e sd-console; **A1** = workflows n8n e homologação ponta a ponta. Situação atualizada no `ACCEPTANCE_REPORT.md`.

## 1. Níveis e ambientes

| Nível | Ferramenta | Onde | Dados |
|---|---|---|---|
| Unitário | pytest (sd-ops, qa-pipeline), Node (`tools/test_code_nodes.py` dos workflows), Vitest/RSpec (fork) | CI + dev | fixtures sintéticas |
| Integração | pytest + Postgres/Redis reais em container; respx/fake 55PBX; Chatwoot DEV | dev (`/opt/servicedesk-dev`) | contas "Teste 55PBX (dev)", agentes fictícios |
| Contrato | schemas dos payloads 55PBX (PDF e readme, inclusive as divergências D1–D12), OpenAPI do sd-ops, envelope `sd:events`, validador dos workflows | CI | exemplos dos manuais + exemplos reais mascarados quando existirem |
| Ponta a ponta (mock) | 55PBX falsa (webhook + Report02 + gravação WAV sintética) → sd-ops → Chatwoot DEV → qa-pipeline com STT/LLM falsos → n8n de teste | dev | fictícios |
| Ponta a ponta (real) | ligação real de teste em cada tipo | homologação | conta/fila de teste da 55PBX, número interno de teste |
| Carga | locust/k6 contra o webhook + workers | dev | sintéticos |

**Regra:** cada resultado registra se foi **mock** ou **real**. Nada é declarado homologado com o provedor sem evidência real (log mascarado, print, ID de chamada).

## 2. Matriz dos 30 cenários

Legenda da coluna "Hoje": ✅ passou (com evidência) · 🟡 passou só no mock da pbx-bridge (base reaproveitada) · ⏳ pendente · 🔒 bloqueado por dependência externa.

| # | Cenário | Responsável | Nível | Mock | Real | Critério de aprovação | Hoje |
|---|---|---|---|---|---|---|---|
| 1 | Cliente novo | A2 | integração, e2e | sim | sim | contato criado com E.164, 1 conversa, 1 ticket com protocolo | 🟡 (e2e pbx-bridge ligação 1) |
| 2 | Cliente existente | A2 | integração | sim | sim | reusa contato (com/sem 9º dígito), não duplica | 🟡 (pytest reuso de contato) |
| 3 | Chamadas sucessivas | A2 | integração | sim | sim | política `reuse_open`: 2ª ligação relacionada ao mesmo ticket; `new_occurrence`: ticket novo relacionado | ⏳ |
| 4 | Duas simultâneas | A2 | integração | sim | sim | 2 chamadas distintas, sem mistura de pernas; lock por `(central_id, call_id)` | ⏳ |
| 5 | Evento inicial duplicado | A2 | unitário | sim | — | 2º com mesma `dedupe_key` → 200 duplicate, nenhum efeito | 🟡 (idempotência por `call_id`) |
| 6 | Evento final duplicado | A2 | unitário, integração | sim | — | nenhuma nota/ticket duplicado; `source_id` idempotente | 🟡 (e2e ligação 5) |
| 7 | Final antes do inicial | A2 | unitário | sim | — | estado `ended` mantido; inicial atrasado só preenche vazios | ⏳ |
| 8 | Transferência entre ramais | A2 | integração | sim | sim | `call_legs` com origem/destino, mesmo ticket, histórico no CTI | 🔒 real (exemplo de `call_transfer_id`) |
| 9 | Transferência entre filas | A2 | integração | sim | sim | idem, time de destino registrado | 🔒 real |
| 10 | Perdida | A2 + A1 (WF03) | integração, e2e | sim | sim | `call.missed`, `callback_task`, WF03 sobe prioridade e etiqueta; recusa de operador **não** conta | ⏳ |
| 11 | Abandonada | A2 + A1 | integração | sim | sim | `abandoned_queue`/`abandoned_ura` via Report02 mesmo sem webhook | ⏳ |
| 12 | Click-to-call | A2 + A3 | integração, e2e | sim (`PBX_DIAL_MODE=mock`) | sim | resultado real exibido; `provider_call_id` liga a chamada ao ticket | 🔒 real (`client_code`/`api_key`/JWT) |
| 13 | Falha de autenticação | A2 + A1 | unitário | sim | sim | segredo errado 404, token errado 401, HMAC inválido 401, token n8n sem escopo 403; webhook n8n sem header recusado | 🟡 (segredo/IP/HMAC na pbx-bridge) |
| 14 | Chatwoot indisponível | A2 | integração | sim | — | evento fica `pending` com backoff, nada perdido, processa ao voltar | 🟡 (retentativa da fila) |
| 15 | 55PBX indisponível | A2 | integração | sim | — | Report02/gravação com backoff; health mostra `last_poll_error` | 🟡 |
| 16 | Áudio inexistente | A2 | integração | sim | sim | `recording.absent`, ticket segue, sem QA | 🟡 (ligação 4 sem áudio) |
| 17 | Áudio atrasado | A2 + A1 (WF02) | integração | sim | sim | retentativas até 6 h; WF02 alerta após 60 min | 🟡 (retentativa de áudio) |
| 18 | Falha de transcrição | A3 | integração | sim | sim | `failed` registrado, retentativa limitada, ticket intacto | ⏳ |
| 19 | Transcrição parcial | A3 | integração | sim | — | `partial` marcado; QA com critérios "não verificável" | ⏳ |
| 20 | QA sem evidência | A3 | unitário | sim | — | critério sem evidência = "não observado/não aplicável", peso redistribuído, nunca falha | ⏳ |
| 21 | Reprocessamento sem duplicação | A2 + A3 | integração | sim | — | reprocessar evento/gravação/QA não cria registros novos (chaves §3 do EVENT_LIFECYCLE) | 🟡 (recuperação sem estado local) |
| 22 | Mudança de status | A2 + A1 | integração | sim | — | máquina de estados (409 em inválida), sincronização conversa↔ticket, `zd_status` correto, `merge=true` | ⏳ |
| 23 | Reabertura | A2 + A1 (WF08) | unitário, integração | sim | — | protocolo citado pelo mesmo contato reabre; outro contato só gera nota | ✅ WF08 (mock: 5 casos unitários + e2e no n8n) · sd-ops: ver relatório do A2 |
| 24 | Telefone e e-mail associados | A2 | integração | sim | — | mesmo contato por telefone e e-mail, sem merge automático por nome | ⏳ |
| 25 | Acesso cruzado entre tenants | A2 + A3 | unitário | sim | — | 404 para recurso de outro tenant; URL de gravação amarrada ao tenant | ⏳ (A2 cita `test_cross_tenant`) |
| 26 | WhatsApp respeitando política | A1 (WF05/07) | unitário, e2e | sim | sim | sem opt-in/horário/template → não envia; 1 envio por ticket (Idempotency-Key) | ✅ política (mock, 2 casos) · 🔒 real (inbox WhatsApp) |
| 27 | Encerramento com CSAT | A1 (WF07) + A2 | e2e | sim | sim | CSAT 2 h após resolver, não envia se reabriu; pesquisa 55PBX registrada | ⏳ |
| 28 | Reconciliação histórica | A2 + A1 (WF09) | integração | sim | sim | período D-1: novas/atualizadas/divergentes contadas; alerta se divergente | 🟡 (poller/backfill pbx-bridge) · 🔒 real (chave Webservice) |
| 29 | Carga concorrente | A2 | carga | sim | — | 50 eventos/s por 5 min: p95 webhook < 300 ms, zero perda, zero duplicata | ⏳ |
| 30 | Recuperação após reinício | A2 | integração | sim | — | matar worker no meio: `XAUTOCLAIM` retoma, outbox reenvia, sem duplicata | 🟡 (perder SQLite não duplica) |

## 3. Testes dos workflows n8n (A1)

| Teste | Comando | Resultado (2026-10-13) |
|---|---|---|
| Estrutura de nós e conexões, versões compatíveis, segredos, headers de contrato, `node --check` | `python3 tools/validate_workflows.py --node-check` | **13 arquivos, 35 nós Code compilados, 0 erros** |
| Teste negativo do validador (conexão quebrada, segredo, versão, credencial real, nó solto, JS inválido) | arquivo adulterado | **6/6 erros detectados** |
| Lógica dos nós Code com dados sintéticos | `python3 tools/test_code_nodes.py` | **32/32 casos** (achou e corrigiu 1 bug: protocolo `B2B-…` não casava com o regex) |
| Reprodutibilidade | `python3 tools/build_workflows.py --check` | JSON idênticos ao gerador |
| Conferência com o OpenAPI do sd-ops (A2, `2201722d35`) | `validate_workflows.py --openapi` | **12/12 rotas existem**; corpos/respostas ajustados ao código |
| Importação e publicação no n8n | `n8n import:workflow` + `publish:workflow` em n8n **2.43.4** descartável (docker rootless do dev) | **13/13** (a instância do cliente não foi tocada) |
| e2e dos workflows | `tools/e2e/run_e2e.sh`: n8n 2.43.4 + mock do sd-ops/Chatwoot com as respostas do código real; 15 cenários | ver `ACCEPTANCE_REPORT.md` §3 |

## 4. Homologação real (roteiro, quando as dependências chegarem)

1. Chave Webservice → `GET report_02` de 1 dia (sem gravar): conferir campos com `55PBX_API_MAPPING.md` §2.
2. Webhook cadastrado apontando para o sd-ops **dormente com gravação do bruto** (modo `capture`): 1 ligação de cada tipo (receptiva atendida, abandonada na fila, retida na URA, ativa, interna, transferida). Resolver D1–D3, D11.
3. IP liberado → 1 gravação baixada e validada (tipo, duração).
4. Discagem → 1 click-to-call para o número de teste.
5. Ativar o fluxo completo em homologação → cenários 1–17, 21–22, 28 com evidência real.
6. Comparar 1 semana de ligações reais com o Report02 (WF09): divergência 0.
