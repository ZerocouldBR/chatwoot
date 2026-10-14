# Runbook de operação: telefonia, tickets (sd-ops), QA e automações n8n

Versão 1, de 2026-10-13 (agente A1). Para a operação do dia a dia e incidentes. Implantação e rollback: `DEPLOYMENT.md`. Ponte antiga (dormente): `INTEGRACAO-55PBX.md` §11.

**Regras gerais:** na `ia4co-old` só mexer nas stacks `servicedesk*`; nunca `docker service update` em serviços de outros clientes; nada de reprocessar em massa sem backup; dados pessoais não vão para chat/ticket de incidente.

## 1. Saúde

| Verificação | Comando / onde | Esperado |
|---|---|---|
| API | `curl -s https://<domínio>/sd-ops/api/v1/health` | `200`, `enabled`, contadores sem dado pessoal |
| Prontidão | `curl -s .../sd-ops/api/v1/ready` | banco, Redis e migration `ok` |
| Métricas | `.../sd-ops/metrics` (Prometheus, token) | `webhook_latency`, `outbox_pending`, `dlq_size`, `recording_failed` |
| Fila de eventos | `redis-cli -n 7 XINFO GROUPS sd:events`; `XLEN sd:events:dlq` | `pending` baixo, DLQ 0 |
| Poller Report02 | health `last_poll_ok_at` | < 30 min |
| n8n | lista de execuções com erro; WF00 publica falhas na conversa interna de operações | sem falha recorrente |
| Logs | `docker service logs servicedesk-ops_worker --since 30m` | 1 linha por chamada, números mascarados |

## 2. Alertas e resposta

| Alerta | Causa provável | O que fazer |
|---|---|---|
| health ≠ 200 | container caiu, banco/Redis fora | `docker service ps servicedesk-ops_api`; ver logs; `ready` diz qual dependência falhou |
| Nenhum webhook da 55PBX há > 2 h em horário comercial | 55PBX parou de enviar, URL/segredo trocados, Traefik | ver `webhook_inbox` (último `received_at`); testar a URL com o segredo; abrir chamado na 55PBX. O poller cobre o intervalo |
| `events_unparsed` crescendo | formato do evento mudou | pegar 1 exemplo mascarado do `webhook_inbox`, atualizar `55PBX_API_MAPPING.md` e o normalizador; reprocessar (§4) |
| `recording_failed` crescendo | IP da VPS bloqueado em `vsa19.55pbx.com`, autenticação, URL expirada | `curl -sI` da VPS no host; pedir liberação; reprocessar as falhas depois |
| DLQ > 0 | Chatwoot fora, regra de negócio, bug | ler o motivo em `/admin/dlq`; corrigir; `POST /admin/dlq/{fila}/{id}/retry` |
| `last_poll_error` | chave Webservice inválida/expirada, 55PBX fora | testar a chave com 1 consulta curta; renovar no painel 55PBX (Integrações > Webservice) |
| WF09 alertou divergência | evento perdido ou duplicado | abrir o relatório da reconciliação; divergências "nova pelo relatório" são normais quando o webhook falhou |
| SLA violado em massa | fila parada, regra errada | conferir política e horário comercial; pausar alertas (desativar WF10) se for falso positivo |
| Sessões CTI falhando | token do Chatwoot revogado, CORS | `audit_events` `auth.failed`; conferir `SDOPS_ALLOWED_ORIGINS` |

## 3. Procedimentos frequentes

| Tarefa | Como |
|---|---|
| Cadastrar ramal → agente | `POST /sd-ops/api/v1/admin/agent-phone-mappings` (ramal/máscara, e-mail do ramal na 55PBX, usuário do Chatwoot) |
| Mudar política de abertura de ticket | `/admin/ticket-open-rules` (`TICKET_DOMAIN.md` §5); registrar a mudança |
| Conceder papel supervisor/QA | `POST /admin/user-roles` |
| Reconciliar um período | WF09 manual (`POST <n8n>/webhook/sd/wf09-reconciliar` com header) ou `POST /sd-ops/api/v1/reconciliations` |
| Revogar sessões de um usuário | `DELETE /admin/sessions?user_id=` |
| Rotacionar segredo do webhook 55PBX | gerar novo (`openssl rand -hex 32`), cadastrar como 2º segredo ativo, trocar no painel 55PBX, remover o antigo após 24 h sem uso |
| Rotacionar token de serviço do n8n | `python -m sd_ops new-service-token n8n`, atualizar a credencial no n8n, remover o hash antigo |
| Desligar uma automação | despublicar o workflow no n8n e desativar a rota em `/admin/automation-routes` |

## 4. Reprocessamento (sempre idempotente)

1. Identificar os itens (`webhook_inbox` com status `error`/`unparsed`, gravações `failed`, DLQ).
2. Backup lógico do `servicedesk_ops` se forem mais de 100 itens.
3. Reprocessar pela API admin (DLQ retry) ou pelo CLI do sd-ops; as chaves de idempotência (`EVENT_LIFECYCLE.md` §3) impedem duplicata no ticket, na conversa e nas notas.
4. Conferir contadores no health e uma amostra no Chatwoot.

## 5. Backup e restauração

| Item | Frequência | Retenção | Teste |
|---|---|---|---|
| `pg_dump -Fc servicedesk_ops` | diário 02:00 | 30 diários + 12 mensais, cópia off-site | restauração mensal num banco temporário + `alembic current` + contagens |
| Storage de gravações | diário (rsync/rclone incremental) | conforme política (1 ano proposto) | restaurar 5 gravações e tocar |
| Banco `chatwoot` | já coberto pelo procedimento da demo/produção | — | — |
| Workflows n8n | versionados no git (`servicedesk/integrations/n8n/workflows`) | — | `validate_workflows.py` e importação de teste |

Metas: RPO ≤ 24 h (sd-ops), RTO ≤ 2 h. Eventos do intervalo perdido são recuperados pelo Report02 (WF09).

## 6. Retenção (jobs automáticos)

| Dado | Prazo | Job |
|---|---|---|
| Payload bruto (`webhook_inbox`) | 30 dias | `RETENTION_DAYS` |
| Documento digitado na URA (texto) | 90 dias | retenção do sd-ops |
| Gravações e transcrições | 1 ano (proposta, validar com o jurídico) | retenção do sd-ops/qa |
| Sessões CTI | 8 h | expiração |
| Log de auditoria | 5 anos (proposta) | — |

## 7. Contatos e escalonamento

| Tema | Quem |
|---|---|
| Plataforma ServiceDesk / VPS | equipe técnica (Lucas / Victor) |
| 55PBX (webhook, chave, IP, discagem, webphone) | suporte@55pbx.com.br — usar o pacote de perguntas de `integrations/PROVIDER_CAPABILITIES.md` §5 |
| n8n do cliente | responsável pelo n8n da B2B |
| LGPD / incidentes com dados pessoais | encarregado (DPO) da B2B |
