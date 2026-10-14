# Relatório de aceite (critérios do prompt mestre §19)

Versão 1, de 2026-10-13 (agente A1). Esqueleto preenchido com o **estado real**. Regra: nenhum critério é "aceito" sem evidência; o que foi testado só com mock está separado do que foi homologado com o provedor real.

Legenda: **ACEITO-REAL** (homologado com 55PBX/Chatwoot reais) · **OK-MOCK** (passou só com simulação) · **PARCIAL** · **PENDENTE** · **BLOQUEADO** (dependência externa, ver `ROADMAP.md` §1).

## 1. Critérios

| # | Critério | Status | Evidência | Falta |
|---|---|---|---|---|
| 1 | Chamada gera registro correto | OK-MOCK | pbx-bridge: e2e DEV 39/39 com 55PBX simulada (5 ligações: receptiva, ativa, interna, sem áudio, repetida) — `INTEGRACAO-55PBX.md` §8 | sd-ops (A2) com `ops.calls`; **payload real** (D2) |
| 2 | Cliente identificado sem duplicar | OK-MOCK | pytest "reuso de contato com/sem 9º dígito" (pbx-bridge, 50 passed) | sd-ops; ligação real de número já cadastrado |
| 3 | Ticket criado ou relacionado | PENDENTE | domínio especificado (`TICKET_DOMAIN.md`); política de abertura | implementação/testes do A2 |
| 4 | Histórico visível no Chatwoot | OK-MOCK | notas privadas idênticas ao Zendesk + MP3 anexado no DEV (pbx-bridge) | homologação real |
| 5 | Perdidas aparecem para tratamento | PARCIAL | WF03 (prioridade, etiqueta, nota) **e2e em n8n 2.43.4 com mock: OK (15/15 na suíte)**; contrato `call.missed` (A2) | evento real de perdida (D2/D3 do mapeamento) e Report02 (D1) |
| 6 | Transferências preservam o vínculo | PENDENTE | regra em `EVENT_LIFECYCLE.md` §2 (`call_legs`) | exemplo real de `call_transfer_id`/`call_id_origin` |
| 7 | O evento final atualiza a chamada | OK-MOCK | pbx-bridge: chegada em 2 etapas (form/PUT) no e2e | sd-ops; evento final real |
| 8 | Áudio consultável | BLOQUEADO | download/validação/MP3 testados com WAV sintético; `vsa19.55pbx.com` **não responde** da VPS (teste T3) | liberação de IP (D3) |
| 9 | Transcrição processável | PENDENTE | A3 (qa-pipeline) | gravação real + provedor STT (D11) |
| 10 | Resumo IA como nota interna revisável | PENDENTE | A3 | — |
| 11 | QA para supervisão | PARCIAL | WF11 (nota com link do console, supervisor participante, registro no ticket) **e2e com mock: OK** | QA real (A3). A entrega do `qa.completed` ao n8n foi fechada na integração final: o sd-ops repassa ao WF11 o resultado recebido em `POST /analysis-results` (pytest `test_contracts.py`) |
| 12 | Click-to-call funcionando quando habilitado | BLOQUEADO | contrato do A2 (`/dial`, modo mock só em dev) | `client_code`/`api_key`/JWT (D4) |
| 13 | Ticket atribuível, acompanhável e encerrável | PARCIAL | Chatwoot (atribuição, status) + WF01 reserva por fila (**e2e OK**); máquina de estados especificada e implementada pelo A2 (`TICKET_DOMAIN.md` §8) | sd-ops (transições, auditoria) |
| 14 | Evento repetido não cria ticket | OK-MOCK | pbx-bridge: ligação repetida (webhook + Report02) sem duplicata; perder o estado local não duplica | sd-ops com `dedupe_key` |
| 15 | Permissões impedem acesso indevido | PARCIAL | `CTI_AUTH.md` (A2): RBAC e 404 entre tenants; webhook n8n recusa token errado (**e2e: 403**) | testes do A2 (cenário 25) |
| 16 | Falha temporária não perde evento silenciosamente | OK-MOCK | pbx-bridge: retentativa da fila (Chatwoot fora) e do Report02; WF00 e alertas WF02/WF09 | outbox/DLQ do sd-ops |
| 17 | Logs, dashboards e documentação disponíveis | PARCIAL | documentação desta rodada (`docs/` e `docs/integrations/`); logs mascarados na pbx-bridge | dashboards (A3), métricas do sd-ops |
| 18 | Evidência de testes em homologação | PENDENTE | — | homologação real após D1–D4, D12 |

## 2. Homologado com o provedor real

**Nada até 2026-10-13.** Testes reais feitos só de conectividade e leitura de documentação:

| Teste | Resultado |
|---|---|
| Hosts da API 55PBX (`ws.55pbx.com:20500`, `reportapi02.55pbx.com:50500`, `api1.55pbx.com:30901`) | respondem (404 na raiz), da VPS e do escritório |
| `fone.55pbx.com` `frame-ancestors` | não inclui o nosso domínio |
| `vsa19.55pbx.com` (gravações) | time-out da VPS e do escritório |
| n8n do cliente | `GET /healthz` e `GET /api/v1/workflows?limit=1` = 200 (só leitura) |

## 3. Testado só com mocks (detalhe)

| Componente | Testes | Resultado |
|---|---|---|
| pbx-bridge (base do sd-ops) | pytest 50; e2e DEV 39 verificações; vitest 5 | passou (`INTEGRACAO-55PBX.md` §8) |
| Workflows n8n | validador estrutural + `node --check` (13 arquivos, 35 nós Code); teste negativo 6/6; lógica dos nós Code 32/32; conferência com o OpenAPI do sd-ops 12/12 rotas; importação e publicação em n8n 2.43.4 13/13 | passou |
| Workflows n8n — e2e em n8n 2.43.4 descartável + mock do sd-ops/Chatwoot | 15 cenários (WF01–WF06, WF08–WF11, anti-loop, token errado, idempotência do envio) | 1ª execução: 14/15 — o WF01 revelou bug real (resposta em array vira vários itens no nó HTTP), corrigido no WF01 e no WF10. Depois do ajuste aos contratos reais do sd-ops (A2, `2201722d35`): **15/15** (execução final, 2026-10-13, log `/tmp/n8n-a1/e2e4.log` na VPS) |
| sd-ops, qa-pipeline, sd-console | — | relatórios do A2 e do A3 |

## 4. Assinaturas

| Papel | Nome | Data | Aceite |
|---|---|---|---|
| Responsável técnico | | | |
| Responsável pelo atendimento (B2B) | | | |
| Encarregado de dados (DPO) | | | |
