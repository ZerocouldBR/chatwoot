# Autenticação do app CTI (Dashboard App) e RBAC do sd-ops

Versão 1, de 2026-10-13 (agente A2). Implementação: `sd_ops/auth.py` em `servicedesk/integrations/pbx-bridge/`. Consumidor principal: o `sd-console` do A3 carregado como **Dashboard App** do Chatwoot (iframe).

## 1. Problema

O Dashboard App recebe do Chatwoot, por `postMessage`, o contexto da conversa, do contato e do agente (`currentAgent`). Esse contexto vem do navegador e **não prova identidade**: qualquer página pode enviar um `postMessage` igual. O Chatwoot CE também não emite token assinado para Dashboard Apps. Por isso o sd-ops não confia no `currentAgent` e exige uma prova verificável no servidor.

## 2. Esquema escolhido: troca do token pessoal do Chatwoot por sessão curta

```
sd-console (iframe)                    sd-ops                                   Chatwoot
   │ 1. agente cola o "Token de acesso" (Perfil > Token de acesso) uma vez
   │ POST /sd-ops/api/v1/auth/session {chatwoot_token, account_id} ─►
   │                                      │ 2. GET /api/v1/profile (api_access_token) ─►
   │                                      │ ◄─ id, e-mail, accounts[{id, role}]
   │                                      │ 3. confere: conta existe em ops.tenants e o usuário pertence a ela
   │                                      │ 4. papel = role da conta + ops.user_roles
   │                                      │ 5. cria ops.cti_sessions (só o SHA-256 do token de sessão)
   │ ◄─ 200 {session_token, csrf_token, expires_at, user, tenant, roles}
   │     Set-Cookie: sdops_session=...; HttpOnly; Secure; SameSite=None; Path=/sd-ops; Max-Age=1800
```

- O **token pessoal do Chatwoot não é guardado** pelo sd-ops (só usado na validação, nunca em log) e o sd-console deve mantê-lo apenas em memória até receber a sessão. Não usar `localStorage`.
- A validação chama `GET {CHATWOOT_URL}/api/v1/profile` (API pública, header `api_access_token`). Token inválido → 401 `invalid_chatwoot_token`. Usuário fora da conta pedida, ou conta sem tenant → 403 `account_not_allowed`.
- **Sessão**: aleatória de 256 bits; expira após `SESSION_IDLE_MIN` (30) min sem uso e no máximo `SESSION_MAX_HOURS` (8) h. Revogação: `POST /auth/logout` ou `DELETE /admin/sessions?user_id=` (admin). Uma sessão vale para **uma** conta (tenant); trocar de conta = nova sessão.
- **Duas formas de apresentar a sessão** (mesmo token):
  1. cookie `sdops_session` (HttpOnly, Secure, SameSite=None, Path=/sd-ops);
  2. `Authorization: Bearer <session_token>`, para navegadores que bloqueiam cookie de terceiros em iframe. O sd-console guarda o token só em memória.
- **CSRF**: requisição que muda estado e se autentica por cookie exige o header `X-SD-CSRF` igual ao `csrf_token` da sessão. Com Bearer não precisa (não há credencial automática). `Origin`, quando presente, tem de estar em `SDOPS_ALLOWED_ORIGINS`.
- **CORS**: só as origens de `SDOPS_ALLOWED_ORIGINS`, com credenciais.
- **Implantação recomendada**: servir `sd-console` e `sd-ops` no **mesmo site** do Chatwoot (`helpdesk.ia4co.com/sd-console/`, `/sd-ops/`). Assim o cookie é primário e o bloqueio de cookies de terceiros não afeta. Em domínio separado, usar o Bearer.
- Limite: sem guardar o token do Chatwoot, o sd-ops não revalida o vínculo do usuário durante a sessão. Por isso ela é curta (30 min ociosa / 8 h). Removido do Chatwoot → no máximo 8 h até a sessão expirar, ou revogação imediata pelo admin.
- Tentativas de criação de sessão: `AUTH_RATE_LIMIT_PER_MIN` (10) por IP. Falhas vão para `audit_events` (`auth.failed`, sem o token).

### Alternativa avaliada e descartada

Confiar no `currentAgent` do `postMessage`, ou em um segredo compartilhado no iframe, é falsificável pelo navegador. Um SSO próprio (OIDC) exigiria alterar o Chatwoot. O token pessoal é o único mecanismo do Chatwoot CE verificável no servidor sem mexer no core.

## 3. Tokens de serviço (A3, n8n)

`Authorization: Bearer sdsvc_<aleatório>`. Configurados em `SDOPS_SERVICE_TOKENS` (JSON), guardando **só o SHA-256**:

```json
{"qa-pipeline": {"sha256": "<sha256 hex do token>", "tenants": ["b2b"],
                 "scopes": ["calls:read", "recordings:read", "analysis:write", "tickets:read"]},
 "n8n": {"sha256": "<sha256 hex do token>", "tenants": ["b2b"],
         "scopes": ["calls:read", "tickets:read", "tickets:write", "notify:send", "reconcile:run", "reports:read"]}}
```

**Perfis prontos** (`sd_ops/auth.py`, `SERVICE_PROFILES`), usados pelo `new-service-token`:

| Perfil | Escopos | Por quê (rotas chamadas) |
|---|---|---|
| `n8n` | `tickets:write`, `notify:send`, `reconcile:run`, `reports:read` + `tickets:read`, `calls:read` | WF04–WF08/WF10/WF11 leem e escrevem ticket (`GET /tickets/{id}`, `/reopen`, `/links`, `/notes`; `GET /sla/at-risk` exige `tickets:read`); WF05–WF07 registram o envio (`POST /notifications/log`); WF09 pede a reconciliação; WF12 lê `/reports/summary` e `/metrics/*`; WF02/WF11 leem `GET /calls/{id}`. **Sem** `tickets:close` (o n8n nunca encerra/cancela), `dial:write` e `callbacks:write`. A lista de rotas de cada workflow é gerada em `servicedesk/integrations/n8n/sdops_endpoints_used.json`, e o teste `tests/sdops/test_contracts.py::test_perfil_n8n_cobre_os_endpoints_dos_workflows` confere que nenhuma delas responde 401/403 com esse perfil |
| `qa-pipeline` | `calls:read`, `recordings:read`, `analysis:write`, `tickets:read` | A3: lê a chamada e a gravação, devolve resultados em `POST /analysis-results` |

Escopos: `calls:read`, `recordings:read`, `tickets:read`, `tickets:write`, `callbacks:write`, `reconcile:run`, `notify:send`, `reports:read`, `analysis:write`, `dial:write` (discagem em nome de `agent_email`), `tickets:close`. Token de serviço nunca encerra/cancela ticket sem `tickets:close`. Requisições de serviço aceitam `Idempotency-Key`; com `X-SD-Origin: n8n` e `X-SD-Workflow`, os eventos gerados levam `caused_by` (anti-loop, `WEBHOOK_CONTRACTS.md` §8.3).

Gerar (imprime o token **uma vez**, os escopos e a linha para `SDOPS_SERVICE_TOKENS`; só o SHA-256 vai para o `.env`):

```bash
python -m sd_ops new-service-token n8n                       # perfil n8n (o nome igual ao perfil já o aplica)
python -m sd_ops new-service-token qa-pipeline               # perfil qa-pipeline
python -m sd_ops new-service-token n8n-cliente --profile n8n --tenants b2b      # outro nome, mesmo perfil
python -m sd_ops new-service-token bi --scopes reports:read  # sem perfil: só os escopos pedidos
```

`--scopes` soma escopos ao perfil e é validado contra a lista acima (escopo desconhecido = erro, saída 2). `--tenants` padrão = `SDOPS_DEFAULT_TENANT` (`*` = todos; prefira o tenant explícito). Rotação: gerar o novo, somar a entrada ao `SDOPS_SERVICE_TOKENS`, trocar a credencial *Header Auth* no n8n, remover a entrada antiga.

## 4. Papéis (RBAC)

| Papel | Origem |
|---|---|
| `agente` | `role = agent` na conta do Chatwoot |
| `admin` | `role = administrator` na conta do Chatwoot |
| `supervisor`, `qa` | concedidos em `ops.user_roles` (por tenant e usuário do Chatwoot) por um admin (`POST /admin/user-roles`) |
| serviço (escopos) | tokens de serviço (§3) |

O usuário recebe a **união** dos papéis. `admin` inclui todas as permissões de `supervisor` e `qa`.

| Permissão | agente | supervisor | qa | admin | serviço (escopo) |
|---|:-:|:-:|:-:|:-:|:-:|
| contexto, chamadas, tickets (ler) | ✓ | ✓ | ✓ | ✓ | `calls:read`, `tickets:read` |
| criar/editar ticket, notas, transições não finais, escalonar, reabrir de `resolvido` | ✓ | ✓ | – | ✓ | `tickets:write` |
| encerrar (`encerrado`), cancelar, aprovar encerramento | – | ✓ | – | ✓ | `tickets:close` |
| click-to-call (só o próprio ramal) | ✓ | ✓ | – | ✓ | – |
| ouvir gravação | só das chamadas em que foi o agente ou de tickets atribuídos a ele | ✓ | ✓ | ✓ | `recordings:read` |
| métricas/dashboards | – | ✓ | ✓ | ✓ | `reports:read` |
| retornos: concluir os próprios / atribuir | ✓ / – | ✓ / ✓ | – | ✓ / ✓ | `callbacks:write` |
| `POST /analysis-results` | – | – | – | – | `analysis:write` |
| `/admin/*` (ramais, regras, papéis, DLQ, reconciliação, sessões) | – | – | – | ✓ | `reconcile:run` só para `POST /reconciliations` |

## 5. Isolamento por tenant

- Tenant = conta do Chatwoot (`ops.tenants.chatwoot_account_id`). Toda tabela de negócio tem `tenant_id` e toda consulta filtra pelo tenant da sessão.
- Recurso de outro tenant responde **404** (não revela existência). Testado no cenário 25 (`tests/sdops/test_api.py::test_cross_tenant`).
- Token de serviço só acessa os tenants listados.
- URL de gravação assinada amarra `recording_id + user_id + tenant + exp`.
