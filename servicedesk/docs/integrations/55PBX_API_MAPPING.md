# Mapeamento de campos 55PBX → sd-ops / Chatwoot

Versão 1, de 2026-10-13 (agente A1). Fontes: F1 (manual REST V2.0, PDF), F2 (manual Webservice GET, PDF), F3 (api-55pbx.readme.io), F4 (central de suporte). Ver `PROVIDER_CAPABILITIES.md`.

**Nenhum payload real da conta do cliente foi recebido ainda.** Os nomes abaixo são os documentados. O parser deve ser tolerante (a pbx-bridge já é) e guardar o bruto.

---

## 1. Evento em tempo real ("Tempo real por URL")

Entrega: `PUT` ou `POST` com corpo JSON; header `token: <chave>` quando a chave é cadastrada (F1 p.5).

### 1.1 Campos documentados

Coluna "Onde": **PDF** = F1 p.4; **RM** = tabela do readme `objeto-de-resposta`; **EX** = só nos exemplos.

| Campo | Tipo doc. | Descrição oficial | Onde | Normalizado (`ops.call_events` / `ops.calls`) | Observação |
|---|---|---|---|---|---|
| `central_id` | String | Identificador do cliente na central | PDF, RM | `central_id` | Parte da chave de idempotência. Ex. "1000", "15" |
| `branch_mask` | Number (EX: string "5000") | Ramal do usuário | PDF, RM | `branch_mask` | Ramal curto (ex. 5005). Chave do mapa ramal→agente |
| `branch_email` | — | (sem descrição) | EX (RM) | `branch_email` | E-mail do ramal na 55PBX. Mesmo valor usado pela API de discagem |
| `branch_line_number` | — | (sem descrição) | EX (RM) | `branch_number` | Número completo (central+ramal, ex. "153401") — igual a `branch_number_agent` do Report02 |
| `call_id` | String | Identificador da ligação | PDF, RM | `provider_call_id` | Formato Asterisk `epoch.seq` ("1479477009.5199"). Chave da ligação |
| `call_date` | Date | Data da ligação | PDF, RM | `started_at` (UTC) | PDF: `ISODate("2012-05-01 12:30:00")` (**não é JSON válido**); RM: `Invalid Date`. Tratar como opcional; usar hora de recebimento como fallback, marcando `started_at_source='received'` |
| `call_terminal` | String | Número tronco de envio/recebimento | PDF, RM | `trunk_number` | |
| `call_type` | String | Tipo (ativo/receptivo/sms) | PDF, RM | `direction` ∈ {`outbound`,`inbound`,`internal`,`sms`} | **Valores divergentes:** descrição "ativo/receptivo/sms"; exemplos `"active"` (PDF) e `"receptive"` (RM). Aceitar ativo/active/outbound e receptivo/receptive/inbound. `sms` é descartado do fluxo de ligação |
| `call_number` | String | Número de chamada | PDF, RM | `remote_number_e164` | PDF: "987654321" (sem DDD); RM: "+5511987468223" (E.164). Normalizar com `call_area_code`/`call_country_code` |
| `call_area_code` | String | DDD | PDF, RM | (usado no E.164) | |
| `call_country_code` | String | DDI | PDF, RM | (usado no E.164) | RM envia número (55) |
| `call_document` | String | CPF/CNPJ digitado na URA | PDF, RM | `ura_document` (**cifrado / mascarado**) | Dado pessoal. Nunca em log aberto |
| `call_order` | String | Nº de pedido digitado na URA | PDF, RM | `ura_order` | Pode ser usado como protocolo digitado |
| `call_ura` | String | Opções escolhidas na URA | PDF, RM | `ura_path` | |
| `call_queue` | String | Fila de atendimento | PDF, RM | `queue_name` | Ex. "testePedro"; no Report02 vem como "1534-SUPORTE" (prefixo da central) |
| `call_status` | String | Status da ligação | PDF, RM | `provider_status` | RM: `"call_attended"`. Lista completa **não documentada** |
| `call_disconnection` | String | Origem da desconexão | PDF, RM | `hangup_side` ∈ {`agent`,`customer`,`unknown`} | Valores vistos: "externo" (cliente), "interno" (ramal) |
| `call_time` | Number | "Tempo em segundos **efetivo** da ligação" | PDF, RM | ver §3 | **Contradição** com os exemplos |
| `call_duration` | Number | "Tempo **total** de duração em segundos" | PDF, RM | ver §3 | **Contradição** com os exemplos |
| `call_total_time` | Number | Tempo total da ligação | RM | `total_seconds` | Só no readme |
| `call_time_waiting` | Number | Espera até o atendimento (s) | PDF, RM | `wait_seconds` | |
| `call_url_audio` | String | URL do áudio | PDF, RM | `recording.source_url` (restrito) | Host `sip1.55pbx.com`/`vsa19.55pbx.com`. Contém telefone e data. Ver §4 |
| `call_audio_file` | String | Nome do arquivo de áudio | PDF, EX | `recording.source_filename` | Extensão `.wav`/`.WAV` |
| `call_tax` | Number | Custo por minuto | PDF, RM | `cost_per_minute` | RM envia string "0.00" |
| `call_tax_type` | String | Tipo de custo | PDF, RM | `cost_type` | Ex. "VC2", "receptivo" (F4 151000180388: VC1/VC2/VC3, Receptivo, Receptivo_0800_*, Receptivo_4004, SMS) |
| `call_cost` | Number | Custo total | PDF, RM | `cost_total` | |
| `call_balance` | Number | Saldo após a ligação | PDF, RM | **não armazenar** (dado financeiro da conta, sem uso) | |
| `call_transfer_id` | String | Id da nova ligação gerada pela transferência | PDF | `transfer_to_provider_call_id` | Ausente no readme |
| `call_ticket_id` | — | — | EX (RM) | `provider_ticket_id` | Vazio no exemplo; é o id de ticket do integrador (Zendesk). Ignorar após o corte |
| `call_rating` | Number | Nota da pesquisa | RM | `csat.score` | |
| `call_rating_weight` | Number | Peso da pesquisa | RM | `csat.weight` | |
| `call_rating_type` | Number | Tipo da pesquisa | RM | `csat.type` | |
| `call_rating_yes` / `call_rating_no` | Number | Nota Sim/Não | RM | `csat.yes` / `csat.no` | |
| `call_rating_form_id` / `call_rating_name` | Number/String | Formulário da pesquisa | RM | `csat.form_id` / `csat.form_name` | |

### 1.2 Fases do evento

| Fase | Como reconhecer (hipótese a validar) | Fonte |
|---|---|---|
| `initial` (1º envio) | sem `call_url_audio`, `call_time`/`call_duration` vazios ou 0, `call_status` vazio | F1 p.6 |
| `final` (2º envio) | durações preenchidas e/ou `call_url_audio` | F1 p.6, RM |
| `transfer` (3º envio) | `call_transfer_id` preenchido | F1 p.6 |

Como não existe campo "tipo de evento", o sd-ops **classifica** a fase por conteúdo e guarda `phase_inferred=true`. Ver `EVENT_LIFECYCLE.md`.

---

## 2. Report02 (detalhe de ligações) — reconciliação

`GET https://reportapi02.55pbx.com:50500/api/pbx/reports/metrics/{date_start}/{date_end}/{queue}/{number}/{agent}/report_02/{quiz_id}/{interval}/{timezone}` com header `key`. Resposta: `{"data_report02":[...], "date_start", "date_end", "queue", "number", "agent", "reportCount", "uuid"}` (no exemplo do readme: `dateStart`/`dateEnd`).

| Campo Report02 | Tipo doc. | Descrição | Normalizado | Equivalente no evento |
|---|---|---|---|---|
| `call_id` | String | ID da ligação | `provider_call_id` | `call_id` |
| `call_id_origin` | String | ID de origem (transferidas) | `parent_provider_call_id` | inverso de `call_transfer_id` |
| `name` | String | Nome do usuário do ramal | `agent_name` | — (ex.: "2 Agentes rejeitaram" em abandonada) |
| `branch_number_agent` | String | Nº do ramal interno (completo) | `branch_number` | `branch_line_number` |
| `wy_branch_mask_agent` | String | Máscara do ramal | `branch_mask` | `branch_mask` |
| `wx_branch_number_agent`, `branch_number` | — | (só no exemplo) | — | — |
| `ws_ticket_id` | Number | ID do Ticket (integrador) | `provider_ticket_id` | `call_ticket_id` |
| `call_disconnection` | String | Interna (ramal) / Externa (cliente) | `hangup_side` | `call_disconnection` |
| `call_time_total_duration` | String `HH:MM:SS` | Duração total | `total_seconds` | ver §3 |
| `call_time_waiting` | String `HH:MM:SS` | Espera | `wait_seconds` | `call_time_waiting` (segundos) |
| `call_time_spoken` | String `HH:MM:SS` | Tempo falado | `talk_seconds` | ver §3 |
| `call_url_audio` | String | URL do áudio | `recording.source_url` | `call_url_audio` |
| `call_number`, `call_area_code`, `wg_country_code` | | Telefone, DDD, DDI | `remote_number_e164` | idem |
| `wf_states` | String | "País"/UF (ex. "Brazil08") | `region_code` | — |
| `call_date` | String `DD/MM/AAAA` | Data | `started_at` (com `wb_call_hour` e `timezone`) | `call_date` |
| `wb_call_hour` | String `HH:MM:SS` | Hora de entrada | idem | — |
| `week_day` | String | Dia da semana | — (derivável) | — |
| `queue_name` | String | Fila (ex. "1534-SUPORTE") | `queue_name` (sem prefixo numérico em `queue_key`) | `call_queue` |
| `wx_queue_id` | String | ID da fila | `queue_provider_id` | — |
| `wx_queue_overflow` | String `;` | Filas com transbordo | `overflow_queues[]` | — |
| `type_call` | String | Tipo/resultado (`call_attended`, `call_abandoned`, …) | `outcome` (§5) | `call_status` |
| `call_number_input` | String | Número de entrada (DID) | `did_number` | `call_terminal`? |
| `call_document`, `call_order` | String | CPF/CNPJ, pedido | `ura_document`, `ura_order` | idem |
| `way_ura` | String | "Tempo na URA" (exemplo: "Opcao - 1") | `ura_path` | `call_ura` |
| `call_time_URA` | String | (descrição errada no manual: "tempo máximo… (ativo)") | `ura_seconds` | — |
| `wk_ivr_<n>_name`, `wk_ivr_<n>_option`, `wk_ivr_<n>_option_name` | String | Passos da URA | `ura_steps[]` | — |
| `wl_time_attended` | String ISO `Z` | Data/hora do atendimento | `answered_at` | — |
| `wl_attended_date`, `wl_attended_hour` | | Data/hora do atendimento (local) | — | — |
| `wt_agents_called` | String `;` | Agentes chamados | `agents_rung[]` (recusas) | — |
| `wu_call_cost` | String | Custo | `cost_total` | `call_cost` |
| `wh_a_quiz_name`, `wh_question_<n>_<nome>` | String | Pesquisa de satisfação | `csat.*` | `call_rating*` |
| `wv_data_*` | String | Dados de discadora/callback/formulário | `dialer_meta` (bruto) | — |
| `totalCallAbandonedURA` | Number | (campo agregado listado no Report02) | — | — |

Report01/03/04/06: campos completos em F2 p.6–10 e no readme (`dados-da-ligação-report_01-ligações` etc.). Usados só pelos dashboards (sd-console/A3) e pelo WF12; os nomes são consumidos crus e as fórmulas (NS, abandono, produtividade) seguem F4 151000180391.

---

## 3. Divergências entre manuais (e decisão)

| # | Divergência | Evidência | Decisão no sd-ops |
|---|---|---|---|
| D1 | `call_time` "efetivo" × `call_duration` "total" contradizem os exemplos | PDF: `call_time 11`, `call_time_waiting 8`, `call_duration 3` → 11 = 8 + 3, logo **call_time = total** e **call_duration = falado**. RM: `call_time 44`, `call_total_time 44`, `call_duration 9`, espera 7 → também **call_time = total** | Mapear **pelos exemplos**: `total_seconds = call_total_time ?? call_time`; `talk_seconds = call_duration`. Guardar os dois brutos e validar com a 1ª ligação real (comparar com Report02 `call_time_total_duration`/`call_time_spoken`). A pbx-bridge já trata `call_time`→total e `call_duration`→falado |
| D2 | 1 envio (final) × 2 envios (inicial + final) × 3 (transferência) | F1 p.4 vs p.6; RM `objeto-de-resposta` ("a cada final de ligação atendida") | Máquina de estados aceita qualquer combinação; nada depende do inicial |
| D3 | Só atendidas × todas | RM ("atendida") vs F1 ("recebida ou efetuada") | Perdidas/abandonadas garantidas só pelo **Report02** (WF09/poller) |
| D4 | `call_type` "ativo/receptivo" × "active"/"receptive" | F1 p.4/p.5; RM | Normalizador aceita PT e EN |
| D5 | `call_date` `ISODate(...)` (inválido em JSON) e `Invalid Date` | F1 p.5; RM | Parser tolerante: tenta JSON, depois substitui `ISODate("...")` por string; data opcional |
| D6 | Tipos: números documentados como Number, exemplos em String | RM (`"call_time": "44"`) | Coerção numérica tolerante |
| D7 | `call_transfer_id` só no PDF; `call_rating*`, `call_total_time`, `branch_email`, `branch_line_number`, `call_ticket_id` só no readme | F1 × RM | Todos opcionais |
| D8 | Path do Report: 8 × 9 segmentos (`interval`) | OpenAPI `requisição-report_02` × exemplos | 9 segmentos (exemplos e PDF) |
| D9 | URL da discagem: `/api/webphone/dial` × `/api/pbx/webphone/dial` | RM `introdução-3` × OpenAPI `requisição-realizar-discagem` | Configurável (`PBX_DIAL_URL`), padrão o da introdução; confirmar com o fornecedor |
| D10 | Auth da discagem: só `client_code`+`api_key` (OpenAPI security) × + `Authorization: Bearer JWT` obrigatório (`autenticação-2`) | RM | Enviar os três; JWT por variável/segredo. Origem do JWT **não documentada** |
| D11 | Header do webhook: `token` (PDF) × "Chave (token)" sem nome (readme) | F1 p.5 | Aceitar `token` e, por compatibilidade, `key`/`Authorization`; validar em tempo constante |
| D12 | Ramal: `branch_mask` (curto) × `branch_number_agent`/`branch_line_number` (completo) | F1, RM, F2 | Mapa ramal→agente indexado por **máscara**; aceitar o número completo como alias (`branch_number` termina com a máscara? **não garantido**: ex. "153401" vs "5000") |

### 3.1 Lacunas da pbx-bridge atual (`normalize.py`) frente aos nomes oficiais do evento REST

> **Atualização (fim da rodada):** o sd-ops do A2 (`sd_ops/normalize55.py`, commit `2201722d35`) já lê `central_id`, `branch_mask`, `branch_email`, `call_status`, `call_transfer_id`, `call_total_time` e `call_rating*`. A tabela abaixo vale só para a pbx-bridge antiga (dormente), que o sd-ops substitui.

Encontradas na leitura do código (branch `feat/integracao-55pbx`, commit `29718aa6d9`). Repassado ao A2 para o sd-ops:

| Campo oficial | Situação na pbx-bridge | Efeito |
|---|---|---|
| `branch_mask` | **não reconhecido** (aliases de `branch` não incluem `branchmask`) | ramal vazio no evento em tempo real → sem responsável pelo mapa; só o poller (Report02, `branch_number_agent`) preenche |
| `central_id` | **não reconhecido** (`central` aceita `central`, `company`…, não `centralid`) | central "não disponível" na ficha |
| `call_transfer_id` | não tratado | transferência não relacionada |
| `call_status` | não tratado (`status` cai em `event`) | resultado da ligação perdido no tempo real |
| `call_queue` | **não reconhecido** (`queue` aceita `queuename`, `queue`, `fila`; `callqueue` não) | time pela fila só via poller |
| `call_total_time`, `call_rating*`, `branch_email` | não tratados | — |
| header `token` | não verificado (segredo só no caminho da URL) | aceitável; sd-ops deve verificar os dois |

---

## 4. Gravação

| Item | Valor |
|---|---|
| Origem | `call_url_audio` (evento final e Report02) |
| Hosts observados | `sip1.55pbx.com` (manuais), `vsa19.55pbx.com` (histórico do cliente, `webphone-3855`) |
| Padrão do nome | `audio-AAAA-MM-DD_HH-MM-SS-<ramal/central>-<telefone>-<call_id>.WAV` |
| Acesso | **bloqueado** a partir da VPS e do escritório (T3). Autenticação não documentada |
| Tratamento | download só de `*.55pbx.com`/`*.55pbx.com.br`, sem seguir redirecionamento, limite de tamanho, verificação de tipo (RIFF/WAVE ou GSM), duração com ffprobe; cópia para storage privado (S3 adapter) |

## 5. Resultado da ligação (`outcome`) — normalização

| `outcome` | Regra (evento ou Report02) | Gera ticket de callback? |
|---|---|---|
| `answered` | `call_status`/`type_call` = `call_attended` ou `talk_seconds > 0` | não (ticket normal) |
| `abandoned_queue` | `type_call=call_abandoned` com fila preenchida | **sim** |
| `abandoned_ivr` | retida na URA (sem fila, `ura_path` preenchido, sem atendimento) | **sim** (configurável) |
| `no_answer` | ativa sem atendimento (`talk_seconds=0`, `direction=outbound`) | não (tentativa do agente) |
| `refused_by_agent` | `wt_agents_called` com recusas e depois atendida | **não** — recusa de operador **não é perdida** (F4 151000093801) |
| `failed` / `out_of_hours` | valores ainda não documentados | pendente de exemplo real |

Valores não reconhecidos ficam `unknown` com o bruto preservado e alerta no health.
