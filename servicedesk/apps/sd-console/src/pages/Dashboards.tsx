/**
 * /dash — Dashboards (Módulo 9) para operador, supervisor, QA e admin. Telefonia e tickets vêm do sd-ops
 * (fórmulas em WEBHOOK_CONTRACTS.md §8.7 e docs/DASHBOARDS.md); qualidade vem do qa-pipeline.
 * Filtros numa linha acima dos gráficos; exportação CSV de cada tabela.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { BarChart, LineChart } from '../components/charts';
import { useSession } from '../components/Session';
import { Badge, ErrorBox, Kpi, Loading, Notice } from '../components/ui';
import { download, toCsv } from '../lib/csv';
import { fmtClock, fmtNum, fmtPct, isoDay } from '../lib/format';
import { errorText, http } from '../lib/http';
import { qaApi } from '../lib/qa';
import * as sdops from '../lib/sdops';

type View = 'operador' | 'supervisor' | 'qualidade' | 'admin';
interface Filters {
  from: string;
  to: string;
  team: string;
  queue: string;
  branch: string;
  agent_email: string;
  channel: string;
  category: string;
  priority: string;
}

const OUTCOME: Record<string, string> = {
  answered: 'atendida',
  abandoned_queue: 'abandono fila',
  abandoned_ura: 'abandono URA',
  missed: 'não atendida',
  after_hours: 'fora do horário',
  dropped: 'queda',
  unknown: 'sem dado',
};

const n = (v: unknown): number | null => (typeof v === 'number' && isFinite(v) ? v : v === null || v === undefined || v === '' ? null : isFinite(Number(v)) ? Number(v) : null);

/** Normaliza /metrics/telephony (chaves de §8.7; aceita variações de nome). */
export function normTelephony(d: Record<string, any> = {}) {
  const tma = d.tma_s ?? d.tma_receptivo_s ?? d.tma?.receptivo ?? d.tma;
  const motivos = d.motivos_desconexao || d.motivos || (d.por_resultado ? Object.entries(d.por_resultado).map(([motivo, total]) => ({ motivo, total })) : []);
  return {
    recebidas: n(d.recebidas),
    atendidas: n(d.atendidas),
    abandonadas: n(d.abandonadas),
    perdidas: n(d.perdidas),
    efetuadas: n(d.efetuadas),
    efetuadas_atendidas: n(d.efetuadas_atendidas),
    tma_s: n(tma),
    tma_ativo_s: n(d.tma_ativo_s ?? d.tma?.ativo),
    tme_s: n(d.tme_s ?? d.tme),
    tme_abandono_s: n(d.tme_abandono_s ?? d.tme_abandono),
    nivel_servico: n(d.nivel_servico),
    taxa_abandono: n(d.taxa_abandono),
    transferidas: n(d.transferidas),
    falado_s: n(d.falado_s ?? d.tempo_falado_s),
    retornos: d.retornos || {},
    por_fila: (d.por_fila || d.by_queue || []) as any[],
    por_ramal: (d.por_ramal || d.by_branch || []) as any[],
    motivos: motivos as any[],
    serie: (d.serie_diaria || d.series || []) as any[],
    custo: d.custo ?? null,
    fonte: d.fonte as string | undefined,
  };
}

const asList = (v: unknown, key: string, val = 'total') =>
  Array.isArray(v) ? v : v && typeof v === 'object' ? Object.entries(v as object).map(([k, x]) => ({ [key]: k, [val]: x })) : [];
const hours = (s: unknown) => (n(s) === null ? null : (n(s) as number) / 3600);

/** /metrics/tickets do sd-ops (§8.7): backlog_agora, tempo_resolucao_*_s, sla.{first_response,resolution}, fcr, por_* (dicionários). */
export function normTickets(d: Record<string, any> = {}) {
  const sla = d.sla || {};
  const vencidos =
    n(d.vencidos) ?? (sla.resolution || sla.first_response ? (n(sla.resolution?.vencidas) || 0) + (n(sla.first_response?.vencidas) || 0) : null);
  return {
    criados: n(d.criados),
    resolvidos: n(d.resolvidos),
    backlog: n(d.backlog ?? d.backlog_agora),
    vencidos,
    tempo_resolucao_h: n(d.tempo_resolucao_h ?? d.tempo_resolucao?.media_h) ?? hours(d.tempo_resolucao_medio_s),
    tempo_resolucao_mediana_h: n(d.tempo_resolucao_mediana_h ?? d.tempo_resolucao?.mediana_h) ?? hours(d.tempo_resolucao_mediana_s),
    sla_cumprido: n(d.sla_cumprido) ?? n(sla.resolution?.cumprimento),
    sla_primeira_resposta: n(sla.first_response?.cumprimento),
    reaberturas: n(d.reaberturas),
    fcr: n(d.fcr),
    por_canal: asList(d.por_canal, 'canal', 'criados') as any[],
    por_equipe: asList(d.por_equipe, 'equipe', 'criados') as any[],
    motivos: (d.motivos ? asList(d.motivos, 'motivo') : asList(d.por_categoria, 'categoria')) as any[],
  };
}

function defaultFilters(): Filters {
  const to = new Date();
  const from = new Date(Date.now() - 29 * 86400000);
  return { from: isoDay(from), to: isoDay(to), team: '', queue: '', branch: '', agent_email: '', channel: '', category: '', priority: '' };
}

export default function Dashboards() {
  const { me, has } = useSession();
  const views: [View, string][] = [['operador', 'Operador']];
  if (has('supervisor')) views.push(['supervisor', 'Supervisor']);
  if (has('qa', 'supervisor')) views.push(['qualidade', 'Qualidade e IA']);
  if (has('admin')) views.push(['admin', 'Administração']);
  const [view, setView] = useState<View>(views.length > 1 ? (views[1][0] as View) : 'operador');
  const [f, setF] = useState<Filters>(defaultFilters);
  const [mock, setMock] = useState(false);
  useEffect(() => {
    sdops.health().then((h) => setMock(!!h.mock)).catch(() => setMock(false));
  }, []);
  const [applied, setApplied] = useState<Filters>(f);
  const q = useMemo(() => {
    const base = { ...applied, to: applied.to };
    if (view === 'operador') base.agent_email = me.email;
    return base;
  }, [applied, view, me.email]);

  return (
    <div className="main">
      <div className="card-head">
        <h1>Dashboards</h1>
        <div className="tabs" role="tablist">
          {views.map(([v, l]) => (
            <button key={v} role="tab" aria-selected={view === v} onClick={() => setView(v)}>
              {l}
            </button>
          ))}
        </div>
      </div>
      {mock ? (
        <Notice kind="mock">sd-ops em MODO MOCK (DEV): telefonia e tickets com números FICTÍCIOS, só para validar a tela.</Notice>
      ) : null}
      <form
        className="card"
        onSubmit={(e) => {
          e.preventDefault();
          setApplied(f);
        }}
        aria-label="Filtros"
      >
        <fieldset>
          <label>
            De
            <input type="date" value={f.from} onChange={(e) => setF({ ...f, from: e.target.value })} />
          </label>
          <label>
            Até
            <input type="date" value={f.to} onChange={(e) => setF({ ...f, to: e.target.value })} />
          </label>
          <label>
            Equipe
            <input value={f.team} onChange={(e) => setF({ ...f, team: e.target.value })} />
          </label>
          <label>
            Fila
            <input value={f.queue} onChange={(e) => setF({ ...f, queue: e.target.value })} />
          </label>
          <label>
            Ramal
            <input value={f.branch} onChange={(e) => setF({ ...f, branch: e.target.value })} />
          </label>
          {view !== 'operador' ? (
            <label>
              Agente (e-mail)
              <input value={f.agent_email} onChange={(e) => setF({ ...f, agent_email: e.target.value })} />
            </label>
          ) : null}
          <label>
            Canal
            <select value={f.channel} onChange={(e) => setF({ ...f, channel: e.target.value })}>
              <option value="">todos</option>
              <option value="telefone">telefone</option>
              <option value="whatsapp">WhatsApp</option>
              <option value="email">e-mail</option>
              <option value="chat">chat</option>
            </select>
          </label>
          <label>
            Categoria
            <input value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} />
          </label>
          <label>
            Prioridade
            <select value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}>
              <option value="">todas</option>
              <option value="baixa">baixa</option>
              <option value="media">média</option>
              <option value="alta">alta</option>
              <option value="urgente">urgente</option>
            </select>
          </label>
        </fieldset>
        <div className="row">
          <button className="primary" type="submit">
            Aplicar filtros
          </button>
          <button type="button" onClick={() => { const d = defaultFilters(); setF(d); setApplied(d); }}>
            Limpar
          </button>
          <span className="small muted">
            Período em UTC. Hoje o sd-ops aceita fila, ramal e agente na telefonia e só o período em tickets; equipe e agente
            filtram a qualidade. Os demais filtros são enviados e passam a valer quando a API os aceitar.
          </span>
        </div>
      </form>
      {view === 'operador' ? (
        <>
          <Telephony q={q} compact />
          <Quality q={q} compact />
        </>
      ) : null}
      {view === 'supervisor' ? (
        <>
          <Telephony q={q} />
          <Tickets q={q} />
        </>
      ) : null}
      {view === 'qualidade' ? <Quality q={q} /> : null}
      {view === 'admin' ? (
        <>
          <Health />
          <Telephony q={q} />
          <Tickets q={q} />
          <Quality q={q} />
        </>
      ) : null}
    </div>
  );
}

function useLoad<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const load = useCallback(() => {
    setError('');
    setData(null);
    fn().then(setData).catch((e) => setError(errorText(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(load, [load]);
  return { data, error, load };
}

function CsvButton({ name, rows, cols }: { name: string; rows: any[]; cols: { key: string; label: string }[] }) {
  return (
    <button type="button" disabled={!rows.length} onClick={() => download(name, toCsv(rows, cols))}>
      Exportar CSV
    </button>
  );
}

function Telephony({ q, compact }: { q: Filters; compact?: boolean }) {
  const { data, error, load } = useLoad(() => sdops.metricsTelephony({ ...q, from: q.from, to: q.to }).then(normTelephony), [JSON.stringify(q)]);
  if (error) return <section className="card"><h2>Telefonia</h2><ErrorBox error={error} onRetry={load} /></section>;
  if (!data) return <section className="card"><h2>Telefonia</h2><Loading /></section>;
  const t = data;
  const kpiRows = [
    { key: 'Recebidas', v: t.recebidas },
    { key: 'Atendidas', v: t.atendidas },
    { key: 'Abandonadas', v: t.abandonadas },
    { key: 'Perdidas', v: t.perdidas },
    { key: 'Efetuadas', v: t.efetuadas },
    { key: 'TMA (s)', v: t.tma_s },
    { key: 'TME (s)', v: t.tme_s },
    { key: 'Nível de serviço', v: t.nivel_servico },
    { key: 'Taxa de abandono', v: t.taxa_abandono },
    { key: 'Transferidas', v: t.transferidas },
  ];
  return (
    <section className="card" aria-label="Telefonia">
      <div className="card-head">
        <h2>Telefonia (55PBX)</h2>
        <CsvButton name="telefonia_resumo.csv" rows={kpiRows} cols={[{ key: 'key', label: 'Métrica' }, { key: 'v', label: 'Valor' }]} />
      </div>
      <div className="grid cols-4">
        <Kpi label="Recebidas" value={fmtNum(t.recebidas)} hint={`${fmtNum(t.atendidas)} atendidas`} title="Chamadas lógicas receptivas no período" />
        <Kpi label="Abandonadas" value={fmtNum(t.abandonadas)} hint={`taxa ${fmtPct(t.taxa_abandono)}`} title="abandonadas (URA+fila) ÷ recebidas" />
        <Kpi label="Perdidas" value={fmtNum(t.perdidas)} hint="não atendida, fora do horário, queda" />
        <Kpi label="Efetuadas" value={fmtNum(t.efetuadas)} hint={`${fmtNum(t.efetuadas_atendidas)} completadas`} />
        <Kpi label="TMA" value={fmtClock(t.tma_s)} hint="média do tempo falado (atendidas)" />
        <Kpi label="TME" value={fmtClock(t.tme_s)} hint="espera média das atendidas" />
        <Kpi label="Nível de serviço" value={fmtPct(t.nivel_servico)} hint="atendidas ≤ 20 s ÷ (atendidas + abandonadas > 5 s)" />
        <Kpi label="Transferidas" value={fmtNum(t.transferidas)} hint={`retornos pendentes: ${fmtNum(n(t.retornos.pendentes))}`} />
      </div>
      {!compact && t.serie.length ? (
        <div className="grid cols-2">
          <div>
            <h3>Recebidas por dia</h3>
            <LineChart title="Chamadas recebidas por dia" data={t.serie.map((s) => ({ label: String(s.dia || s.date).slice(5), value: n(s.recebidas) }))} />
          </div>
          <div>
            <h3>Abandonadas por dia</h3>
            <LineChart title="Chamadas abandonadas por dia" data={t.serie.map((s) => ({ label: String(s.dia || s.date).slice(5), value: n(s.abandonadas) }))} />
          </div>
        </div>
      ) : null}
      {!compact && t.por_fila.length ? (
        <div className="stack">
          <div className="card-head">
            <h3>Por fila</h3>
            <CsvButton name="telefonia_por_fila.csv" rows={t.por_fila} cols={['fila', 'recebidas', 'atendidas', 'abandonadas', 'tma_s', 'tme_s', 'nivel_servico'].map((k) => ({ key: k, label: k }))} />
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Fila</th>
                  <th className="num">Recebidas</th>
                  <th className="num">Atendidas</th>
                  <th className="num">Abandonadas</th>
                  <th className="num">TMA</th>
                  <th className="num">TME</th>
                  <th className="num">NS</th>
                </tr>
              </thead>
              <tbody>
                {t.por_fila.map((r) => (
                  <tr key={r.fila}>
                    <td>{r.fila}</td>
                    <td className="num">{fmtNum(n(r.recebidas))}</td>
                    <td className="num">{fmtNum(n(r.atendidas))}</td>
                    <td className="num">{fmtNum(n(r.abandonadas))}</td>
                    <td className="num">{fmtClock(n(r.tma_s))}</td>
                    <td className="num">{fmtClock(n(r.tme_s))}</td>
                    <td className="num">{fmtPct(n(r.nivel_servico))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
      {!compact && t.por_ramal.length ? (
        <div className="stack">
          <div className="card-head">
            <h3>Por ramal / agente</h3>
            <CsvButton name="telefonia_por_ramal.csv" rows={t.por_ramal} cols={['ramal', 'agente', 'atendidas', 'efetuadas', 'tma_s', 'transferidas'].map((k) => ({ key: k, label: k }))} />
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Ramal</th>
                  <th>Agente</th>
                  <th className="num">Atendidas</th>
                  <th className="num">Efetuadas</th>
                  <th className="num">TMA</th>
                  <th className="num">Transferidas</th>
                </tr>
              </thead>
              <tbody>
                {t.por_ramal.map((r) => (
                  <tr key={r.ramal}>
                    <td>{r.ramal}</td>
                    <td>{r.agente || '-'}</td>
                    <td className="num">{fmtNum(n(r.atendidas))}</td>
                    <td className="num">{fmtNum(n(r.efetuadas))}</td>
                    <td className="num">{fmtClock(n(r.tma_s))}</td>
                    <td className="num">{fmtNum(n(r.transferidas))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
      {!compact && t.motivos.length ? (
        <div>
          <h3>Motivos de encerramento</h3>
          <BarChart
            title="Motivos de encerramento"
            data={t.motivos.map((m) => ({ label: OUTCOME[String(m.motivo || m.label)] || String(m.motivo || m.label), value: n(m.total ?? m.count) }))}
          />
        </div>
      ) : null}
      {t.custo === null ? <span className="small muted">Custo de telefonia: não informado pelo sd-ops (depende do contrato/tarifa da 55PBX).</span> : null}
      {t.fonte ? <span className="small muted">Fonte: {t.fonte}</span> : null}
    </section>
  );
}

function Tickets({ q }: { q: Filters }) {
  const { data, error, load } = useLoad(() => sdops.metricsTickets({ ...q }).then(normTickets), [JSON.stringify(q)]);
  if (error) return <section className="card"><h2>Tickets</h2><ErrorBox error={error} onRetry={load} /></section>;
  if (!data) return <section className="card"><h2>Tickets</h2><Loading /></section>;
  const t = data;
  return (
    <section className="card" aria-label="Tickets">
      <div className="card-head">
        <h2>Tickets</h2>
        <CsvButton name="tickets_por_equipe.csv" rows={t.por_equipe} cols={['equipe', 'criados'].map((k) => ({ key: k, label: k }))} />
      </div>
      <div className="grid cols-4">
        <Kpi label="Criados" value={fmtNum(t.criados)} />
        <Kpi label="Resolvidos" value={fmtNum(t.resolvidos)} />
        <Kpi label="Backlog (agora)" value={fmtNum(t.backlog)} hint={`${fmtNum(t.vencidos)} vencidos`} />
        <Kpi label="Tempo de resolução" value={t.tempo_resolucao_h !== null ? `${fmtNum(t.tempo_resolucao_h, 1)} h` : '-'} hint={`mediana ${fmtNum(t.tempo_resolucao_mediana_h, 1)} h (corridas)`} />
        <Kpi label="SLA de resolução" value={fmtPct(t.sla_cumprido)} hint={`1ª resposta ${fmtPct(t.sla_primeira_resposta)} · paradas sem violação ÷ paradas`} />
        <Kpi label="Reaberturas" value={fmtNum(t.reaberturas)} />
        <Kpi label="FCR" value={fmtPct(t.fcr)} hint="resolvidos sem reabertura e com ≤ 1 contato ÷ resolvidos" />
      </div>
      <div className="grid cols-2">
        {t.por_canal.length ? (
          <div>
            <h3>Criados por canal</h3>
            <BarChart title="Tickets criados por canal" data={t.por_canal.map((c) => ({ label: String(c.canal), value: n(c.criados) }))} />
          </div>
        ) : null}
        {t.motivos.length ? (
          <div>
            <h3>Principais motivos</h3>
            <BarChart title="Tickets por motivo" data={t.motivos.slice(0, 6).map((c) => ({ label: String(c.motivo || c.categoria).slice(0, 12), value: n(c.total) }))} />
          </div>
        ) : null}
      </div>
    </section>
  );
}

function Quality({ q, compact }: { q: Filters; compact?: boolean }) {
  const { data, error, load } = useLoad(
    () => qaApi.quality({ from: q.from, to: q.to, agent: q.agent_email || undefined, team: q.team || undefined }),
    [JSON.stringify(q)],
  );
  const [csvErr, setCsvErr] = useState('');
  async function exportServer() {
    setCsvErr('');
    try {
      const txt = await http<string>(qaApi.csvUrl({ from: q.from, to: q.to, agent: q.agent_email || undefined, team: q.team || undefined }));
      download('qa_avaliacoes.csv', txt.startsWith('﻿') ? txt : '﻿' + txt);
    } catch (e) {
      setCsvErr(errorText(e));
    }
  }
  if (error) return <section className="card"><h2>Qualidade e IA</h2><ErrorBox error={error} onRetry={load} /></section>;
  if (!data) return <section className="card"><h2>Qualidade e IA</h2><Loading /></section>;
  const d = data;
  return (
    <section className="card" aria-label="Qualidade e IA">
      <div className="card-head">
        <h2>Qualidade e IA</h2>
        {!compact ? (
          <button type="button" onClick={exportServer}>
            Exportar avaliações (CSV)
          </button>
        ) : null}
      </div>
      {csvErr ? <Notice kind="danger">{csvErr}</Notice> : null}
      <div className="grid cols-4">
        <Kpi label="Gravações transcritas" value={fmtNum(d.transcritas)} hint={`de ${fmtNum(d.gravacoes_recebidas)} · sucesso ${fmtPct(d.taxa_sucesso)}`} />
        <Kpi label="QA médio (final)" value={fmtNum(d.qa_medio_final, 1)} hint={`IA ${fmtNum(d.qa_medio_ia, 1)} · ${fmtNum(d.avaliacoes)} avaliações`} />
        <Kpi label="CSAT" value={d.csat?.media_pct !== null && d.csat?.media_pct !== undefined ? `${fmtNum(d.csat.media_pct, 0)}%` : '-'} hint={`${fmtNum(d.csat?.respostas)} respostas · satisfeitos ${d.csat?.satisfeitos_pct ?? '-'}%`} />
        <Kpi label="Divergência IA × humano" value={d.divergencia_ia_humano?.media_abs !== null && d.divergencia_ia_humano?.media_abs !== undefined ? `${fmtNum(d.divergencia_ia_humano.media_abs, 1)} pts` : '-'} hint={`${fmtNum(d.divergencia_ia_humano?.pares)} revisadas · cobertura ${fmtPct(d.cobertura_revisao)}`} />
        <Kpi label="Reclamações" value={fmtNum(d.reclamacoes)} hint={`retornos prometidos: ${fmtNum(d.retornos_prometidos)}`} />
        <Kpi label="Sem evidência" value={fmtNum(d.sem_evidencia_suficiente)} hint="avaliações sem nota automática" />
        <Kpi label="Processamento" value={d.tempo_proc_por_min_audio_s !== null ? `${fmtNum(d.tempo_proc_por_min_audio_s, 0)} s/min` : '-'} hint={`${fmtNum(d.minutos_audio, 0)} min de áudio · ${d.transcricoes_parciais} parciais`} />
        <Kpi label="Custo de IA" value={d.custo_ia?.estimado_brl === 0 ? 'R$ 0' : 'ver estimativa'} hint={`${d.custo_ia?.stt_provider} + ${d.custo_ia?.llm_provider}`} />
      </div>
      {d.custo_ia?.llm_provider === 'mock' ? (
        <Notice kind="mock">Avaliação automática em modo MOCK (regras, sem IA). Ligue um LLM local ou aprovado para notas de produção.</Notice>
      ) : null}
      <div className="grid cols-2">
        <div>
          <h3>Distribuição das notas</h3>
          <BarChart title="Distribuição das notas finais de QA" data={Object.entries(d.distribuicao || {}).map(([k, v]) => ({ label: k, value: v as number }))} />
        </div>
        {!compact && d.serie_diaria?.length ? (
          <div>
            <h3>Evolução do QA médio (IA)</h3>
            <LineChart title="QA médio por dia" yMax={100} data={d.serie_diaria.map((s: any) => ({ label: String(s.dia).slice(5), value: s.qa_medio }))} />
          </div>
        ) : null}
      </div>
      <div className="stack">
        <div className="card-head">
          <h3>Critérios com mais falhas</h3>
          <CsvButton name="qa_criterios.csv" rows={d.criterios || []} cols={['label', 'aplicavel', 'falhas', 'taxa_falha', 'nao_aplicavel', 'media'].map((k) => ({ key: k, label: k }))} />
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Critério</th>
                <th className="num">Aplicável</th>
                <th className="num">Falhas</th>
                <th className="num">Taxa</th>
                <th className="num">Não aplicável</th>
                <th className="num">Média</th>
              </tr>
            </thead>
            <tbody>
              {(d.criterios || []).map((c: any) => (
                <tr key={c.key}>
                  <td>{c.label}</td>
                  <td className="num">{c.aplicavel}</td>
                  <td className="num">{c.falhas}</td>
                  <td className="num">{c.taxa_falha !== null ? <Badge kind={c.taxa_falha > 0.3 ? 'danger' : c.taxa_falha > 0.1 ? 'warn' : 'ok'}>{fmtPct(c.taxa_falha, 0)}</Badge> : '-'}</td>
                  <td className="num">{c.nao_aplicavel}</td>
                  <td className="num">{fmtNum(c.media, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <span className="small muted">Falha = critério não observado ou com nota abaixo de 60. Não aplicável não conta como falha.</span>
    </section>
  );
}

function Health() {
  const [sd, setSd] = useState<any>(null);
  const [qa, setQa] = useState<any>(null);
  useEffect(() => {
    sdops.health().then(setSd).catch((e) => setSd({ status: 'erro', error: errorText(e) }));
    http('/sd-qa/health').then(setQa).catch((e) => setQa({ status: 'erro', error: errorText(e) }));
  }, []);
  return (
    <section className="card" aria-label="Saúde dos serviços">
      <h2>Saúde dos serviços</h2>
      <div className="grid cols-2">
        <dl className="kv">
          <dt>sd-ops</dt>
          <dd>{sd ? <Badge kind={sd.status === 'ok' ? 'ok' : 'danger'}>{sd.status || '?'}</Badge> : '…'} {sd?.mock ? <Badge kind="warn">mock</Badge> : null}</dd>
        </dl>
        <dl className="kv">
          <dt>qa-pipeline</dt>
          <dd>{qa ? <Badge kind={qa.status === 'ok' ? 'ok' : 'danger'}>{qa.status}</Badge> : '…'}</dd>
          <dt>Jobs</dt>
          <dd className="small">{qa?.jobs ? Object.entries(qa.jobs).map(([k, v]) => `${k}: ${v}`).join(' · ') : '-'}</dd>
          <dt>Eventos a publicar</dt>
          <dd>{qa?.outbox_pending ?? '-'} (stream) · {qa?.sdops_pending ?? '-'} (sd-ops)</dd>
          <dt>Provedores</dt>
          <dd className="small">{qa?.config ? `${qa.config.stt_provider}/${qa.config.whisper_model} + ${qa.config.llm_provider}` : '-'}</dd>
        </dl>
      </div>
    </section>
  );
}
