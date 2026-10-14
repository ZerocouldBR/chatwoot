/**
 * /qa — Console de QA (Módulo 5, §8.5): pendentes, revisadas, contestadas, tarefas de revisão humana,
 * por agente (feedback e plano de treinamento), rubricas e prompts versionados.
 */
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useSession } from '../components/Session';
import { Badge, Empty, ErrorBox, Loading, Notice } from '../components/ui';
import { ALERT_LABEL, fmtDateTime, fmtNum, scoreClass } from '../lib/format';
import { errorText } from '../lib/http';
import { qaApi, type EvalRow, type Task } from '../lib/qa';

type Tab = 'pendente' | 'revisada' | 'contestada' | 'tarefas' | 'agentes' | 'rubricas';
const TABS: [Tab, string][] = [
  ['pendente', 'Pendentes'],
  ['revisada', 'Revisadas'],
  ['contestada', 'Contestadas'],
  ['tarefas', 'Revisão humana'],
  ['agentes', 'Por agente'],
  ['rubricas', 'Rubricas e prompts'],
];

export default function QaConsole() {
  const { isManager } = useSession();
  const [tab, setTab] = useState<Tab>('pendente');
  const tabs = isManager ? TABS : TABS.filter(([t]) => ['pendente', 'revisada', 'contestada'].includes(t));
  return (
    <div className="main">
      <div className="card-head">
        <h1>Qualidade (QA)</h1>
        {!isManager ? <span className="small muted">Você vê apenas as suas avaliações.</span> : null}
      </div>
      <div className="tabs" role="tablist" aria-label="Seções do QA">
        {tabs.map(([t, label]) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>
            {label}
          </button>
        ))}
      </div>
      <div role="tabpanel">
        {['pendente', 'revisada', 'contestada'].includes(tab) ? <EvalList review={tab as EvalRow['review_state']} /> : null}
        {tab === 'tarefas' ? <Tasks /> : null}
        {tab === 'agentes' ? <Agents /> : null}
        {tab === 'rubricas' ? <Rubrics /> : null}
      </div>
    </div>
  );
}

function EvalList({ review }: { review: EvalRow['review_state'] }) {
  const [rows, setRows] = useState<EvalRow[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState('');
  const [agent, setAgent] = useState('');
  const [page, setPage] = useState(1);
  const load = useCallback(() => {
    setError('');
    qaApi
      .evaluations({ review, agent: agent || undefined, page, per_page: 25 })
      .then((r) => {
        setRows(r.items);
        setTotal(r.total);
      })
      .catch((e) => setError(errorText(e)));
  }, [review, agent, page]);
  useEffect(load, [load]);
  if (error) return <ErrorBox error={error} onRetry={load} />;
  if (!rows) return <Loading />;
  return (
    <section className="card">
      <div className="row">
        <label style={{ flexDirection: 'row', alignItems: 'center' }}>
          Agente
          <input value={agent} onChange={(e) => setAgent(e.target.value)} placeholder="e-mail" />
        </label>
        <span className="small muted">{total} avaliação(ões)</span>
      </div>
      {rows.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Data</th>
                <th>Agente</th>
                <th>Equipe</th>
                <th className="num">IA</th>
                <th className="num">Humano</th>
                <th>Estado</th>
                <th>Tarefas</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link to={`/qa/avaliacoes/${r.id}`}>{r.id}</Link>
                  </td>
                  <td>{fmtDateTime(r.created_at)}</td>
                  <td>{r.agent_name || r.agent_ref || 'não identificado'}</td>
                  <td>{r.team || '-'}</td>
                  <td className="num">{r.ai_score !== null ? <Badge kind={scoreClass(r.ai_score)}>{fmtNum(r.ai_score)}</Badge> : <Badge kind="warn">sem nota</Badge>}</td>
                  <td className="num">{r.human_score !== null ? fmtNum(r.human_score) : '-'}</td>
                  <td>{r.status === 'insufficient_evidence' ? 'evidência insuficiente' : r.review_state}</td>
                  <td>{r.open_tasks ? <Badge kind="warn">{r.open_tasks}</Badge> : '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty>Nada por aqui.</Empty>
      )}
      {total > 25 ? (
        <div className="row">
          <button disabled={page === 1} onClick={() => setPage(page - 1)}>
            Anterior
          </button>
          <span className="small">Página {page}</span>
          <button disabled={page * 25 >= total} onClick={() => setPage(page + 1)}>
            Próxima
          </button>
        </div>
      ) : null}
    </section>
  );
}

const KIND: Record<string, string> = {
  alert: 'Alerta',
  qa_low_score: 'Nota baixa',
  qa_insufficient_evidence: 'Sem evidência',
  contest: 'Contestação',
  pipeline_failure: 'Falha no processamento',
  csat_low: 'CSAT baixo',
};

function Tasks() {
  const [items, setItems] = useState<Task[] | null>(null);
  const [status, setStatus] = useState('open');
  const [error, setError] = useState('');
  const load = useCallback(() => {
    qaApi
      .tasks({ status })
      .then((r) => setItems(r.items))
      .catch((e) => setError(errorText(e)));
  }, [status]);
  useEffect(load, [load]);
  async function close(t: Task, st: 'done' | 'dismissed') {
    try {
      await qaApi.patchTask(t.id, { status: st, resolution: st === 'done' ? 'tratado' : 'descartado' });
      load();
    } catch (e) {
      setError(errorText(e));
    }
  }
  if (error) return <ErrorBox error={error} onRetry={load} />;
  if (!items) return <Loading />;
  return (
    <section className="card">
      <div className="row">
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Situação">
          <option value="open">Abertas</option>
          <option value="done">Concluídas</option>
          <option value="all">Todas</option>
        </select>
        <span className="small muted">Alertas com evidência e casos que exigem decisão humana.</span>
      </div>
      {items.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Tipo</th>
                <th>Severidade</th>
                <th>Assunto</th>
                <th>Evidência</th>
                <th>Agente</th>
                <th>Criada</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((t) => (
                <tr key={t.id}>
                  <td>{KIND[t.kind] || t.kind}</td>
                  <td>
                    <Badge kind={t.severity === 'alta' ? 'danger' : t.severity === 'media' ? 'warn' : ''}>{t.severity}</Badge>
                  </td>
                  <td>
                    {t.alert_type ? ALERT_LABEL[t.alert_type] || t.title : t.title}
                    {t.detail ? <div className="small muted">{t.detail}</div> : null}
                  </td>
                  <td className="small">{t.evidence_text ? `“${t.evidence_text}”` : '-'}</td>
                  <td className="small">{t.agent_ref || '-'}</td>
                  <td className="small">{fmtDateTime(t.created_at)}</td>
                  <td>
                    <div className="row">
                      {t.evaluation_id ? <Link to={`/qa/avaliacoes/${t.evaluation_id}`}>abrir</Link> : null}
                      {t.status === 'open' ? (
                        <>
                          <button onClick={() => close(t, 'done')}>Concluir</button>
                          <button onClick={() => close(t, 'dismissed')}>Descartar</button>
                        </>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty>Nenhuma tarefa.</Empty>
      )}
    </section>
  );
}

function Agents() {
  const [items, setItems] = useState<any[] | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    qaApi
      .agents({})
      .then((r) => setItems(r.items))
      .catch((e) => setError(errorText(e)));
  }, []);
  if (error) return <ErrorBox error={error} />;
  if (!items) return <Loading />;
  return (
    <section className="card">
      <h2>Feedback por agente (30 dias)</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Agente</th>
              <th>Equipe</th>
              <th className="num">Avaliações</th>
              <th className="num">QA IA</th>
              <th className="num">QA humano</th>
              <th className="num">Divergência</th>
              <th className="num">Contestações</th>
              <th>Plano de treinamento (critérios com mais falhas)</th>
            </tr>
          </thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.agent_ref}>
                <td>{a.agent_name || a.agent_ref}</td>
                <td>{a.team || '-'}</td>
                <td className="num">{a.avaliacoes}</td>
                <td className="num">{fmtNum(a.qa_medio_ia, 1)}</td>
                <td className="num">{fmtNum(a.qa_medio_humano, 1)}</td>
                <td className="num">{a.divergencia_media !== null ? `${fmtNum(a.divergencia_media, 1)} pts` : '-'}</td>
                <td className="num">{a.contestacoes}</td>
                <td>{a.criterios_a_treinar?.length ? a.criterios_a_treinar.join(', ') : '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Rubrics() {
  const { has } = useSession();
  const [rubrics, setRubrics] = useState<any[] | null>(null);
  const [prompts, setPrompts] = useState<any[]>([]);
  const [error, setError] = useState('');
  const load = useCallback(() => {
    Promise.all([qaApi.rubrics(), qaApi.prompts()])
      .then(([r, p]) => {
        setRubrics(r.items);
        setPrompts(p.items);
      })
      .catch((e) => setError(errorText(e)));
  }, []);
  useEffect(load, [load]);
  if (error) return <ErrorBox error={error} />;
  if (!rubrics) return <Loading />;
  return (
    <div className="grid cols-2">
      <section className="card">
        <h2>Versões da rubrica</h2>
        {rubrics.map((r) => (
          <div key={r.id} className="stack" style={{ borderBottom: '1px solid var(--sd-border-soft)', paddingBottom: 8 }}>
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <strong>
                {r.name.replace(/\s*\(v\d+\)$/, '')} · versão {r.version}
              </strong>
              {r.active ? (
                <Badge kind="ok">ativa</Badge>
              ) : has('qa') ? (
                <button onClick={() => qaApi.activateRubric(r.id).then(load).catch((e) => setError(errorText(e)))}>Ativar</button>
              ) : null}
            </div>
            <table>
              <tbody>
                {r.criteria.map((c: any) => (
                  <tr key={c.key}>
                    <td>{c.label}</td>
                    <td className="num">{c.weight}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <span className="small muted">{r.redistribution_rule}</span>
            <span className="small muted">
              {r.evaluations} avaliação(ões) com esta versão · criada por {r.created_by} em {fmtDateTime(r.created_at)}
            </span>
          </div>
        ))}
        <Notice kind="info">Nova versão: POST /sd-qa/api/v1/rubrics (pesos somando 100). Avaliações antigas mantêm a versão usada.</Notice>
      </section>
      <section className="card">
        <h2>Prompts versionados</h2>
        <table>
          <thead>
            <tr>
              <th>Tipo</th>
              <th>Versão</th>
              <th>SHA-256</th>
            </tr>
          </thead>
          <tbody>
            {prompts.map((p) => (
              <tr key={p.id}>
                <td>{p.kind === 'qa' ? 'Avaliação de QA' : 'Resumo'}</td>
                <td>{p.version}</td>
                <td className="mono small">{String(p.sha256).slice(0, 16)}…</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
