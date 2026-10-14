# Estimativa de custos (infra, STT e LLM)

Versão 1, de 2026-10-13 (agente A1). **Separação obrigatória:** o que tem a marca **[VERIFICADO]** foi lido na página oficial de preços em 2026-10-13; o que tem **[ESTIMADO]** é cálculo ou suposição nossa e precisa ser confirmado. Valores em US$ (cobrança dos provedores); conversão para R$ pelo câmbio do dia do faturamento (não verificado aqui).

## 1. Volume de referência (dados do cliente)

| Item | Valor | Fonte |
|---|---|---|
| Ligações 2026 (1/1 a 13/10) | 17.609 | tickets com tag `55pbx` (`INTEGRACAO-55PBX.md` §1) |
| Gravações 2026 | ~9.500 | 67% das atualizações têm URL de áudio |
| Tempo falado 2026 | ~642 h (2,31 milhões de s; média 163 s) | tags `55pbx_call_time_*` |
| Projeção anual (×12/9,4 meses) | ~22,5 mil ligações; ~12,1 mil gravações; **~820 h ≈ 49.000 min de áudio** | [ESTIMADO] |
| Tickets/ano (todos os canais) | ~151 mil (151.732 linhas de 2026) | `CAMPOS.md` |
| Armazenamento de gravações | ~1 GB/mês em MP3 32 kbps (~12 GB/ano); original WAV PCM ~4× maior | `INTEGRACAO-55PBX.md` §9 [ESTIMADO] |

Para a IA, uso **49.000 min/ano** e **12.100 gravações/ano**. Também mostro o custo por minuto, que não depende da projeção.

## 2. Transcrição (STT)

| Opção | Preço oficial | Custo/ano (49 mil min) | Observações |
|---|---|---|---|
| OpenAI `gpt-4o-mini-transcribe` | **US$ 0,003/min** [VERIFICADO: developers.openai.com/api/docs/pricing] | **≈ US$ 147** | sem diarização; limite 25 MB/arquivo |
| OpenAI `gpt-4o-transcribe` | **US$ 0,006/min** [VERIFICADO] | ≈ US$ 294 | melhor precisão |
| OpenAI `gpt-4o-transcribe-diarize` | **US$ 0,006/min** [VERIFICADO] | ≈ US$ 294 | separa falantes (agente × cliente) |
| OpenAI `whisper-1` | **US$ 0,006/min** [VERIFICADO] | ≈ US$ 294 | legado |
| Deepgram Nova-3 pré-gravado, multilíngue | **US$ 0,0052/min** pay-as-you-go [VERIFICADO: deepgram.com/pricing] | ≈ US$ 255 | diarização incluída no pré-gravado [VERIFICADO]; suporte a pt-BR no modelo monolíngue **não confirmado** na página de preços |
| Deepgram Nova-3 pré-gravado, monolíngue | **US$ 0,0043/min** [VERIFICADO] | ≈ US$ 211 | idem |
| Whisper local (faster-whisper) na VPS | sem custo de API | custo de CPU/RAM [ESTIMADO] | ~2,2 h de áudio/dia útil: viável em CPU com modelo `small`/`medium` fora do horário; `large-v3` em CPU fica lento. Melhor privacidade (áudio não sai da VPS). Exige teste de qualidade em pt-BR com áudio de telefonia 8 kHz |
| Transcrição da própria 55PBX | não publicado | — | aparece no guia de relatórios ("Call Transcription"), sem API nem preço documentados [ESTIMADO: depende de licença] |

## 3. Resumo e QA com LLM

Suposição por ligação [ESTIMADO]: transcrição de 163 s ≈ 1.000 tokens + rubrica/instruções 1.500 tokens = **2.500 tokens de entrada**; resumo + QA em JSON ≈ **800 tokens de saída**.

| Modelo | Preço oficial (US$/1M tokens, entrada / saída) | Custo por ligação | Custo/ano (12,1 mil) |
|---|---|---|---|
| OpenAI `gpt-4.1-mini` | 0,40 / 1,60 [VERIFICADO] | ≈ US$ 0,0023 | ≈ US$ 28 |
| OpenAI `gpt-5-mini` | 0,25 / 2,00 [VERIFICADO] | ≈ US$ 0,0022 (+ tokens de raciocínio) | ≈ US$ 27–80 |
| OpenAI `gpt-4o-mini` | 0,15 / 0,60 [VERIFICADO] | ≈ US$ 0,0009 | ≈ US$ 11 |
| Google `gemini-2.5-flash` (pago) | 0,30 texto / 2,50 [VERIFICADO: ai.google.dev/gemini-api/docs/pricing] | ≈ US$ 0,0028 | ≈ US$ 33 |
| Google `gemini-2.5-flash-lite` (pago) | 0,10 / 0,40 [VERIFICADO] | ≈ US$ 0,0006 | ≈ US$ 7 |
| Gemini 2.5 Flash com **áudio direto** (sem STT separado) | áudio US$ 1,00/1M tokens [VERIFICADO] | ≈ US$ 0,005 + saída [ESTIMADO: 32 tokens/s de áudio] | ≈ US$ 85 | 

Privacidade: o plano pago do Gemini declara que o conteúdo **não** é usado para melhorar produtos [VERIFICADO]. Para OpenAI, a política de não uso para treino na API deve ser confirmada no contrato/DPA do cliente [ESTIMADO]. O cliente já usa OpenAI e Gemini/Vertex no n8n (credenciais `openAiApi`, `googlePalmApi`), o que facilita a contratação.

## 4. Custo total de IA por minuto e por ano

| Cenário | STT | LLM | US$/min de áudio | US$/ano (49 mil min) |
|---|---|---|---|---|
| Econômico | `gpt-4o-mini-transcribe` | `gemini-2.5-flash-lite` | ≈ 0,0032 | **≈ US$ 155** |
| Recomendado para o piloto | `gpt-4o-transcribe-diarize` | `gpt-4.1-mini` | ≈ 0,0068 | **≈ US$ 335** |
| Local | Whisper local | `gemini-2.5-flash-lite` | ≈ 0,0001 + CPU | ≈ US$ 7 + infra |

Reprocessamentos, avaliações duplas (IA × humano) e testes: somar 20% [ESTIMADO]. Mesmo no pior cenário, **IA fica abaixo de US$ 50/mês** no volume atual.

## 5. Infraestrutura

| Item | Situação | Custo |
|---|---|---|
| Homologação/demo na `ia4co-old` (4 vCPU, 15 GB RAM, 197 GB, 73% usado) | existente, compartilhada com ~40 sistemas | marginal; **não** recomendada para produção (`DESIGN-MIGRACAO.md` §3) |
| VPS dedicada de produção (4 vCPU / 16 GB / 200 GB NVMe) para Chatwoot + Postgres + Redis + sd-ops + sd-console | a contratar | **US$ 30–90/mês** conforme provedor [ESTIMADO, preços não verificados nesta rodada] |
| + 4 vCPU se Whisper local | opcional | +US$ 20–60/mês [ESTIMADO] |
| Storage de gravações | volume local (~12 GB/ano MP3; ~50 GB/ano se guardar o WAV original) | dentro do disco da VPS; backup externo (S3-compatível) ≈ US$ 1–5/mês [ESTIMADO] |
| Backup off-site do Postgres (151 mil tickets/ano + anexos) | a definir | US$ 5–20/mês [ESTIMADO] |
| n8n | instância do cliente | sem custo novo |
| Chatwoot | CE, **sem licença** (enterprise começa em US$ 19/agente/mês [VERIFICADO: developers.chatwoot.com/self-hosted/enterprise-edition]; ~50 agentes ≈ US$ 950/mês **evitados**) | 0 |
| 55PBX | contrato atual (minutos, ramais, gravação) | sem mudança; discagem e relatórios via API estão no contrato? **confirmar licença** com o fornecedor |

## 6. Resumo

| Bloco | Mensal [ESTIMADO] |
|---|---|
| IA (STT + LLM), volume atual (+20% de reprocessamento) | US$ 15–35 |
| Infra de produção dedicada | US$ 40–120 |
| Backup/armazenamento externo | US$ 5–25 |
| **Total adicional** | **≈ US$ 60–180/mês** |

Pendências para fechar o número: escolha do provedor de VPS, câmbio, decisão STT (API × local, depois de um teste A/B com 30 gravações reais — bloqueado até a 55PBX liberar o IP das gravações) e política de retenção (manter WAV original ou só MP3).
