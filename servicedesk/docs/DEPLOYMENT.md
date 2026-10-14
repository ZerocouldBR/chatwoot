# Implantação (Docker Swarm na VPS, padrão `infra/vps`) — sd-ops, sd-console, n8n

Versão 1, de 2026-10-13 (agente A1). **Nada aqui foi aplicado.** Segue o padrão já usado em `infra/vps/stack.yml` e `infra/vps/pbx-bridge.stack.yml`: stack separada, Traefik na rede `MRnet`, rede interna `servicedesk_internal`, segredos em arquivo `.env` 600 fora do git, nada de `docker service update` nos serviços da stack `servicedesk`.

## 1. Ambientes

| Ambiente | Onde | Banco | Redis | Uso |
|---|---|---|---|---|
| dev | `/opt/servicedesk-dev` (docker rootless do `victor`) | Postgres de dev | Redis de dev | desenvolvimento, e2e com mocks |
| homologação | `ia4co-old`, stack `servicedesk` (demo) + stack nova `servicedesk-ops` | `servicedesk_ops` no `servicedesk_postgres` | `servicedesk_redis` **DB 7** | homologação com 55PBX real (conta/fila de teste) |
| produção | VPS dedicada (a contratar) | idem | idem | operação |

## 2. Pré-requisitos (uma vez, com aval do responsável)

1. **Banco separado** no Postgres da stack (não é o banco `chatwoot`):
   ```bash
   # na VPS, como root (homologação); senha gerada na hora e gravada só no .env 600
   PGC=$(docker ps -q -f name=servicedesk_postgres)
   SENHA=$(openssl rand -hex 24)   # vai para o sd-ops.env (600) e não fica no histórico do shell
   docker exec -i "$PGC" psql -U postgres -v senha="$SENHA" <<'SQL'
   CREATE ROLE sd_ops LOGIN PASSWORD :'senha';
   CREATE DATABASE servicedesk_ops OWNER sd_ops;
   \c servicedesk_ops
   CREATE SCHEMA ops AUTHORIZATION sd_ops;
   CREATE SCHEMA qa AUTHORIZATION sd_ops;      -- o A3 pode usar um role próprio com GRANT só em qa
   REVOKE ALL ON DATABASE servicedesk_ops FROM PUBLIC;
   SQL
   ```
   Backup antes (`pg_dumpall --globals-only` + `pg_dump chatwoot`), como no `RUNBOOK-CARGA-DEMO.md`.
2. **Redis DB 7**: nada a criar; `REDIS_URL=redis://:<senha>@servicedesk_redis:6379/7`. Conferir que DB 7 está vazio (`SELECT 7; DBSIZE`).
3. **Storage**: volume `sd_ops_recordings` (padrão local). MinIO **não** compartilhar com `redetur_minio`/`contractmanager_minio` (outros clientes).
4. **Imagens** (CI, como `docs/CI-IMAGEM.md`): `ghcr.io/zerocouldbr/servicedesk-sd-ops:<sha>`, `ghcr.io/zerocouldbr/servicedesk-sd-console:<sha>`, `ghcr.io/zerocouldbr/servicedesk-qa:<sha>` (A3).
5. **Provisionamento no Chatwoot** (rails runner, idempotente, dormente — mesmo padrão do `provision_55pbx.rb`): inbox "Telefone (55PBX)", usuários de integração (sd-ops e n8n, papel agente), atributos `sd_*`, Dashboard App "CTI" apontando para `/sd-console/`, webhook de conta para `/sd-ops/api/v1/webhooks/chatwoot/<segredo>` com `secret`.

## 3. Stack `servicedesk-ops` (modelo)

Arquivo proposto: `infra/vps/sd-ops.stack.yml` (a versão final vem com o código do A2; este é o contrato de implantação).

```yaml
# sd-ops + workers + sd-console. Stack SEPARADA, DORMENTE por padrão (SDOPS_ENABLED=false).
# Deploy (só com aval): cd /opt/servicedesk && docker stack deploy -c sd-ops.stack.yml servicedesk-ops
x-sdops: &sdops
  image: ${SDOPS_IMAGE:-ghcr.io/zerocouldbr/servicedesk-sd-ops:latest}
  env_file: sd-ops.env                      # 600, fora do git (modelo: .env.example do sd-ops)
  environment:
    ENABLED: ${SDOPS_ENABLED:-false}
    CHATWOOT_URL: http://servicedesk_rails:3000
    DATABASE_URL_FILE: /run/secrets/sdops_db_url
    REDIS_DB: "7"
    SDOPS_STORAGE_BACKEND: local
    SDOPS_STORAGE_DIR: /data/recordings
  networks: [servicedesk_internal]
  read_only: true
  volumes:
    - sd_ops_recordings:/data/recordings
    - type: tmpfs
      target: /tmp
      tmpfs: { size: 268435456 }
  logging: { driver: json-file, options: { max-size: "10m", max-file: "5" } }

services:
  api:
    <<: *sdops
    command: ["python", "-m", "sd_ops", "api"]
    networks: [servicedesk_internal, MRnet]
    deploy:
      replicas: 1
      update_config: { order: start-first, failure_action: rollback }
      resources: { limits: { cpus: "0.75", memory: 512M } }
      labels:
        traefik.enable: "true"
        traefik.docker.network: MRnet
        traefik.http.routers.sdops.rule: Host(`helpdesk.ia4co.com`) && (PathPrefix(`/sd-ops`) || PathPrefix(`/integracoes/55pbx`))
        traefik.http.routers.sdops.priority: "100"
        traefik.http.routers.sdops.entrypoints: websecure
        traefik.http.routers.sdops.tls.certresolver: letsencryptresolver
        traefik.http.services.sdops.loadbalancer.server.port: "8080"
  worker:
    <<: *sdops
    command: ["python", "-m", "sd_ops", "worker"]   # normalização, Chatwoot, gravações, outbox, dispatcher n8n
    deploy: { replicas: 1, resources: { limits: { cpus: "0.75", memory: 512M } } }
  scheduler:
    <<: *sdops
    command: ["python", "-m", "sd_ops", "scheduler"] # poller Report02, SLA, retenção
    deploy: { replicas: 1, resources: { limits: { cpus: "0.25", memory: 256M } } }
  migrate:
    <<: *sdops
    command: ["alembic", "upgrade", "head"]
    deploy: { replicas: 0, restart_policy: { condition: none } }   # rodar sob demanda (ver §4)
  console:
    image: ${SDCONSOLE_IMAGE:-ghcr.io/zerocouldbr/servicedesk-sd-console:latest}
    networks: [MRnet]
    read_only: true
    deploy:
      replicas: 1
      resources: { limits: { cpus: "0.25", memory: 128M } }
      labels:
        traefik.enable: "true"
        traefik.docker.network: MRnet
        traefik.http.routers.sdconsole.rule: Host(`helpdesk.ia4co.com`) && PathPrefix(`/sd-console`)
        traefik.http.routers.sdconsole.priority: "100"
        traefik.http.routers.sdconsole.entrypoints: websecure
        traefik.http.routers.sdconsole.tls.certresolver: letsencryptresolver
        traefik.http.services.sdconsole.loadbalancer.server.port: "8080"

networks:
  servicedesk_internal: { external: true }
  MRnet: { external: true }
volumes:
  sd_ops_recordings:
```

Notas:
- A rota `/integracoes/55pbx` passa para o sd-ops (alias legado). **Não** subir a stack `servicedesk-pbx` (pbx-bridge) junto: são substitutos, não complementares.
- Os workers do QA (A3) entram numa stack própria ou neste arquivo, com o volume `sd_ops_recordings` montado **somente leitura**.
- Limites de CPU/memória pensados para a `ia4co-old` (4 vCPU, 15 GB, já com ~40 sistemas).
- Access log do Traefik: excluir os caminhos com segredo (`/sd-ops/api/v1/webhooks/*`).

## 4. Ordem de implantação (homologação)

1. Backups (Postgres inteiro + volume de storage do Chatwoot).
2. §2 itens 1–3 (banco, Redis, volume).
3. `sd-ops.env` preenchido a partir do `.env.example` (chmod 600).
4. Migrations: `docker run --rm --network servicedesk_internal --env-file sd-ops.env $SDOPS_IMAGE alembic upgrade head` (ou `docker service scale servicedesk-ops_migrate=1` e voltar a 0).
5. `docker stack deploy -c sd-ops.stack.yml servicedesk-ops` com `SDOPS_ENABLED` **ausente** (dormente) → `curl https://helpdesk.ia4co.com/sd-ops/api/v1/health` = `enabled:false`.
6. Provisionamento no Chatwoot (§2 item 5) em modo dormente.
7. n8n: importar os workflows (`servicedesk/integrations/n8n/README.md`), **inativos**; criar as credenciais; preencher os nós `config`.
8. Captura real (sem efeitos): `SDOPS_ENABLED=capture` (se o A2 implementar) ou webhook dormente que só grava `webhook_inbox` → ligações de teste → validar `55PBX_API_MAPPING.md`.
9. Ativação: `SDOPS_ENABLED=true docker stack deploy ...`; publicar WF01–WF04, WF08–WF12; WF05–WF07 com `dry_run=true` até aprovação.
10. Corte do Zendesk: desligar a integração 55PBX → Zendesk **no mesmo momento** em que o webhook da 55PBX passa a apontar para o sd-ops.

## 5. Rollback

| Situação | Ação |
|---|---|
| Problema no sd-ops | `docker stack deploy` sem `SDOPS_ENABLED` (volta a dormente) ou `docker stack rm servicedesk-ops`; os dados ficam no banco `servicedesk_ops`; o Chatwoot não é afetado |
| Migration ruim | `alembic downgrade -1` (toda migration tem downgrade testado) ou restaurar `pg_dump servicedesk_ops` |
| Workflow n8n com efeito indesejado | desativar (unpublish) o workflow; o sd-ops guarda o evento em `automation_executions` para reenvio |
| Voltar ao Zendesk | reapontar o "Tempo real por URL" da 55PBX para a integração Zendesk e reativá-la; as conversas criadas permanecem |

## 6. Variáveis (resumo; nomes finais no `.env.example` do A2)

`ENABLED`, `DATABASE_URL`, `REDIS_URL` (DB 7), `CHATWOOT_URL`, `CHATWOOT_API_TOKEN`, `CHATWOOT_ACCOUNT_ID`, `CHATWOOT_WEBHOOK_HMAC_SECRET`, `PBX_API_URL`, `PBX_API_KEY`, `PBX_DIAL_URL`, `PBX_DIAL_MODE`, `PBX_CLIENT_CODE`, `PBX_DIAL_API_KEY`, `PBX_DIAL_JWT`, `ALLOWED_IPS`, `SDOPS_SERVICE_TOKENS`, `SDOPS_ALLOWED_ORIGINS`, `RECORDING_URL_SECRET`, `RECORDING_URL_TTL_S`, `SDOPS_STORAGE_*`, `RETENTION_DAYS`, `SL_THRESHOLD_S`, `TZ`. Nenhuma tem valor real em documento ou commit.
