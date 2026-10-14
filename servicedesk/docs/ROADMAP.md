# Roadmap replanejado pelas dependências reais

Versão 1, de 2026-10-13 (agente A1). Base: cronograma do prompt mestre §18 (MVP no início de dezembro/2026) e o estado real levantado em `GAP_ANALYSIS.md`. As datas valem **se** as dependências externas chegarem nos prazos da coluna "precisa até".

## 1. Dependências externas (caminho crítico)

| # | Dependência | Quem | Precisa até | Bloqueia | Alternativa se atrasar |
|---|---|---|---|---|---|
| D1 | Chave **Webservice (API)** da 55PBX | cliente (painel 55PBX) | **20/10** | reconciliação (Report02), dashboards de telefonia, cenários 11/28 | sd-ops só com webhook; perdidas/abandonadas incompletas |
| D2 | Cadastro do **"Tempo real por URL"** + exemplo real do payload + IPs de origem | cliente + 55PBX | **24/10** | toda a telefonia em tempo real; divergências D1–D3 (`55PBX_API_MAPPING.md`) | só reconciliação a cada 10 min (sem pop-up em tempo real) |
| D3 | **Liberação do IP** da VPS em `vsa19.55pbx.com` + resposta sobre autenticação das gravações | 55PBX | **31/10** | gravação, transcrição, QA, teste A/B de STT | link da gravação na nota (como no Zendesk); QA só com dados de teste |
| D4 | **Discagem**: `client_code`, `api_key`, como obter o **JWT**, URL correta | 55PBX | **07/11** | click-to-call (cenário 12) | botão desabilitado com explicação; agente disca pelo webphone |
| D5 | **`frame-ancestors`** do `fone.55pbx.com` incluindo o domínio | 55PBX | opcional | webphone dentro do ticket | **extensão oficial do Chrome** (decisão B+A já prevê) |
| D6 | **Google OAuth** (login) e acesso admin ao Google Workspace (encaminhamento de e-mail) | cliente | 14/11 | login Google, e-mail (M8), WF06 real | login por senha + MFA; WF06 em dry-run |
| D7 | **VPS de produção** dedicada + domínio final (ex. `suporte.b2breservas.com.br`) | cliente | 14/11 | go-live | homologação na `ia4co-old` (não recomendado para produção) |
| D8 | **WhatsApp**: decisão Cloud API × manter Sunshine; templates aprovados; opt-in | cliente | 21/11 | WF05/WF07 reais, cenário 26 real | e-mail e CSAT nativo do Chatwoot |
| D9 | Mapa **ramal → agente** (e-mail do ramal na 55PBX) e fila → time | cliente | 24/10 | atribuição automática | atribuição pelo time da fila (WF01) |
| D10 | Política de **gravação/retenção** e validação jurídica (LGPD) | cliente/DPO | 14/11 | retenção de áudio, envio a STT externo | Whisper local; retenção mínima |
| D11 | Provedor de **STT/LLM** e credenciais (ou endpoint privado) | cliente | 07/11 | transcrição/QA reais | mocks (A3) |
| D12 | Conta/fila **de teste** na 55PBX e número para ligações de homologação | cliente + 55PBX | 24/10 | evidências reais | — |

## 2. Fases replanejadas

| Fase | Período | Entregas | Gate | Situação em 13/10 |
|---|---|---|---|---|
| **0. Auditoria e POC** | 13–20/10 | matriz de capacidades, mapeamentos, arquitetura, domínio de ticket, contratos, workflows n8n (A1); sd-ops esqueleto + contrato vinculante (A2); qa-pipeline e sd-console esqueleto (A3); **POC real**: `GET report_02` de 1 dia (D1) | D1 recebido e consulta real OK | documentação e workflows **entregues**; POC real **bloqueada** (D1) |
| **1. Telefonia e tickets** | 21/10–31/10 | sd-ops com webhook, merge de eventos, contato, ticket, conversa, outbox; captura de payload real (D2) | ligação real → conversa + ticket no DEV/homolog | depende de D2/D12 |
| **2. CTI e gravações** | 01–10/11 | sd-console no Dashboard App, gravações no storage, URL assinada, click-to-call (D4) | áudio real tocando com auditoria | depende de D3/D4 |
| **3. QA, IA e automações** | 11–20/11 | STT/LLM reais (D11), resumo revisável, QA, WF01–WF12 publicados em homologação | 30 gravações reais avaliadas; WF com dry-run validados | depende de D3/D11 |
| **4. SLA, dashboards, testes, segurança** | 21–30/11 | SLA (M6 no sd-ops), dashboards, carga, pentest, backup testado, treinamento | cenários 1–30 com evidência; aceite (`ACCEPTANCE_REPORT.md`) | — |
| **5. Go-live controlado** | 01–05/12 | VPS de produção (D7), ativação com desligamento simultâneo da integração 55PBX→Zendesk, hypercare | smoke de 30 min; rollback pronto | depende de D7 |

**Fora do caminho crítico da telefonia, mas necessário para desligar o Zendesk** (plano do `DESIGN-MIGRACAO.md`): API de compatibilidade para os 34 workflows de IA do n8n (M7), e-mail (M8), papéis M13, carga final e delta. Sugestão: tratar como trilha paralela com corte do Zendesk **depois** do go-live da telefonia (dezembro → janeiro), para não somar riscos.

## 3. Riscos de prazo

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| 55PBX demora em D2–D4 | alta | alto | pedir tudo num único chamado já (pacote de perguntas em `PROVIDER_CAPABILITIES.md` §5); seguir com mocks e reconciliação |
| Evento em tempo real só para atendidas (D3 do mapeamento) | média | médio | perdidas pelo Report02 a cada 10 min (WF09/poller) |
| Gravações inacessíveis (IP/autenticação) | média | alto para QA | manter link (paridade Zendesk); QA começa com amostra manual |
| `ia4co-old` sem folga (73% disco, 40 sistemas) | média | médio | produção em VPS dedicada (D7) |
| Agentes paralelos (A1/A2/A3) mudando contratos | média | médio | `WEBHOOK_CONTRACTS.md` §8 (A2) é vinculante; workflows gerados por script e revalidados |
