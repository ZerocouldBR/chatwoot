/** /qa/avaliacoes/:id — evidências com tempo, comparação IA × humano, revisão, contestação, histórico. */
import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Player } from '../components/Player';
import { useSession } from '../components/Session';
import { Badge, ErrorBox, Loading, Notice } from '../components/ui';
import { ALERT_LABEL, fmtClock, fmtDateTime, fmtNum, fmtPct, scoreClass, STATUS_LABEL } from '../lib/format';
import { errorText } from '../lib/http';
import { qaApi, type Criterion, type CritStatus, type EvalDetail } from '../lib/qa';

export default function QaEvaluation() {
  const { id } = useParams();
  const { me, isManager } = useSession();
  const [d, setD] = useState<EvalDetail | null>(null);
  const [error, setError] = useState('');
  const [seek, setSeek] = useState<{ t: number; n: number } | null>(null);
  const load = useCallback(() => {
    setError('');
    qaApi
      .evaluation(id!)
      .then(setD)
      .catch((e) => setError(errorText(e)));
  }, [id]);
  useEffect(load, [load]);
  if (error) return <div className="main"><ErrorBox error={error} onRetry={load} /></div>;
  if (!d) return <div className="main"><Loading /></div>;
  const human = d.human_reviews[d.human_reviews.length - 1];
  const hcrit = new Map((human?.criteria || []).map((c) => [c.key, c]));
  const own = d.agent_ref === me.email;
  return (
    <div className="main">
      <div className="card-head">
        <div className="stack" style={{ gap: 2 }}>
          <Link to="/qa" className="small">
            ← Console de QA
          </Link>
          <h1>
            Avaliação #{d.id} · {d.agent_name || d.agent_ref || 'agente não identificado'}
          </h1>
          <span className="small muted">
            {fmtDateTime(d.created_at)} · ligação {d.call_id || '-'} · ticket {d.ticket_id || '-'} · conversa {d.conversation_id || '-'}
          </span>
        </div>
        <div className="row">
          <Badge kind={scoreClass(d.ai_score)} title="Nota sugerida pela IA (recomendação)">
            IA {d.ai_score !== null ? fmtNum(d.ai_score) : 'sem nota'}
          </Badge>
          {d.human_score !== null ? <Badge kind={scoreClass(d.human_score)}>Humano {fmtNum(d.human_score)}</Badge> : null}
          <Badge>{d.review_state}</Badge>
        </div>
      </div>
      {d.status === 'insufficient_evidence' ? (
        <Notice kind="warn">Evidência insuficiente para nota automática. Avalie ouvindo a gravação.</Notice>
      ) : null}
      {d.transcription.status === 'partial' ? <Notice kind="warn">Transcrição parcial ({fmtPct(d.transcription.coverage_ratio, 0)} do áudio).</Notice> : null}
      <div className="grid cols-2">
        <section className="card">
          <h2>Gravação e transcrição</h2>
          <Player recordingId={d.recording_id} segments={d.segments} seekTo={seek} />
          <span className="small muted">
            STT {d.transcription.provider}/{d.transcription.model} · idioma {d.transcription.language || '?'} · confiança média{' '}
            {fmtPct(d.transcription.avg_confidence, 0)} · PII mascarada: {Object.entries(d.transcription.pii_counts || {}).map(([k, v]) => `${k} ${v}`).join(', ') || 'nenhuma'}
          </span>
        </section>
        <section className="card">
          <div className="card-head">
            <h2>Critérios: IA × revisão humana</h2>
            <span className="small muted">peso aplicável {d.applicable_weight}/100</span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Critério</th>
                  <th className="num">Peso</th>
                  <th>IA</th>
                  <th>Humano</th>
                </tr>
              </thead>
              <tbody>
                {d.criteria.map((c) => {
                  const h = hcrit.get(c.key);
                  const diverge = h && (h.status !== c.status || Math.abs((h.score ?? 0) - (c.score ?? 0)) > 15);
                  return (
                    <tr key={c.key}>
                      <td>
                        <strong>{c.label}</strong>
                        <div className="small muted">{c.justification}</div>
                        {c.evidence_text && c.evidence_start_s !== null && c.evidence_start_s !== undefined ? (
                          <button className="link small" onClick={() => setSeek({ t: c.evidence_start_s!, n: Date.now() })}>
                            {fmtClock(c.evidence_start_s)} “{c.evidence_text}”
                          </button>
                        ) : null}
                        {c.suggestion ? <div className="small">Sugestão: {c.suggestion}</div> : null}
                        {c.flags?.length ? <div className="small muted">sinais: {c.flags.join(', ')}</div> : null}
                      </td>
                      <td className="num">
                        {c.weight}
                        <div className="small muted">efetivo {fmtNum(c.effective_weight, 1)}</div>
                      </td>
                      <td>
                        {STATUS_LABEL[c.status]}
                        {c.score !== null ? ` · ${fmtNum(c.score)}` : ''}
                        <div className="small muted">conf. {fmtPct(c.confidence, 0)}</div>
                      </td>
                      <td>
                        {h ? (
                          <>
                            {STATUS_LABEL[h.status]}
                            {h.score !== null ? ` · ${fmtNum(h.score)}` : ''} {diverge ? <Badge kind="warn">diverge</Badge> : null}
                          </>
                        ) : (
                          '-'
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <details>
            <summary className="small">Regra de pontuação e redistribuição</summary>
            <p className="small">{d.redistribution?.resultado}</p>
            <p className="small muted">{d.redistribution?.regra}</p>
          </details>
          <span className="small muted">
            Rubrica {d.rubric.name} (v{d.rubric.version}) · prompt {d.prompt?.kind} {d.prompt?.version} ({d.prompt?.sha256.slice(0, 10)}…) · modelo{' '}
            {d.llm_provider}/{d.llm_model} · STT {d.stt_model}
          </span>
        </section>
      </div>
      <div className="grid cols-2">
        {isManager ? <ReviewForm d={d} onDone={load} /> : null}
        <ContestBox d={d} own={own} isManager={isManager} onDone={load} />
        <section className="card">
          <h2>Alertas e tarefas</h2>
          {d.tasks.length ? (
            <ul className="stack" style={{ paddingLeft: 16, margin: 0 }}>
              {d.tasks.map((t) => (
                <li key={t.id}>
                  <Badge kind={t.severity === 'alta' ? 'danger' : 'warn'}>{t.status}</Badge> {ALERT_LABEL[t.alert_type || ''] || t.title}
                  {t.evidence_text ? (
                    <button className="link small" onClick={() => t.evidence_start_s !== null && setSeek({ t: t.evidence_start_s || 0, n: Date.now() })}>
                      {' '}
                      {fmtClock(t.evidence_start_s)} “{t.evidence_text}”
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <span className="small muted">Nenhum alerta.</span>
          )}
        </section>
        <section className="card">
          <h2>Histórico</h2>
          <table>
            <thead>
              <tr>
                <th>Execução</th>
                <th className="num">Nota IA</th>
                <th>Modelo</th>
                <th>Rubrica</th>
                <th>Atual</th>
              </tr>
            </thead>
            <tbody>
              {d.history.map((h) => (
                <tr key={h.id}>
                  <td>{fmtDateTime(h.created_at)}</td>
                  <td className="num">{h.score !== null ? fmtNum(h.score) : '-'}</td>
                  <td className="small">{h.llm_model}</td>
                  <td>v{h.rubric_version_id}</td>
                  <td>{h.is_current ? 'sim' : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul className="small" style={{ paddingLeft: 16, margin: 0 }}>
            {d.events.map((e, i) => (
              <li key={i}>
                {fmtDateTime(e.created_at)} · {e.type} · {e.actor}
              </li>
            ))}
          </ul>
          {isManager ? <Reprocess rid={d.recording_id} /> : null}
        </section>
      </div>
    </div>
  );
}

function ReviewForm({ d, onDone }: { d: EvalDetail; onDone: () => void }) {
  const [vals, setVals] = useState<Record<string, { status: CritStatus; score: string; justification: string }>>(() =>
    Object.fromEntries(d.criteria.map((c: Criterion) => [c.key, { status: c.status, score: c.score !== null ? String(Math.round(c.score)) : '', justification: '' }])),
  );
  const [comment, setComment] = useState('');
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const criteria = d.criteria
      .map((c) => ({ key: c.key, ...vals[c.key] }))
      .filter((v) => {
        const o = d.criteria.find((c) => c.key === v.key)!;
        return v.status !== o.status || (v.score !== '' && Number(v.score) !== Math.round(o.score ?? -1)) || v.justification;
      })
      .map((v) => ({ key: v.key, status: v.status, score: v.status === 'observed' ? Number(v.score) : null, justification: v.justification || null }));
    try {
      const r = await qaApi.review(d.id, { criteria, comment });
      setMsg({ ok: true, text: `Revisão registrada. Nota final: ${r.score !== null ? Math.round(r.score) : 'sem nota'}.` });
      onDone();
    } catch (err) {
      setMsg({ ok: false, text: errorText(err) });
    }
  }
  return (
    <form className="card" onSubmit={submit} aria-label="Revisão humana">
      <h2>Revisão humana</h2>
      <span className="small muted">Altere só o que discordar. Não aplicável não conta como falha; o peso é redistribuído.</span>
      {d.criteria.map((c) => (
        <div key={c.key} className="row" style={{ alignItems: 'flex-end' }}>
          <span style={{ flex: '1 1 160px' }} className="small">
            {c.label}
          </span>
          <select
            aria-label={`Status de ${c.label}`}
            value={vals[c.key].status}
            onChange={(e) => setVals({ ...vals, [c.key]: { ...vals[c.key], status: e.target.value as CritStatus } })}
          >
            <option value="observed">observado</option>
            <option value="not_observed">não observado</option>
            <option value="not_applicable">não aplicável</option>
          </select>
          <input
            aria-label={`Nota de ${c.label}`}
            type="number"
            min={0}
            max={100}
            style={{ width: 72 }}
            disabled={vals[c.key].status !== 'observed'}
            required={vals[c.key].status === 'observed'}
            value={vals[c.key].score}
            onChange={(e) => setVals({ ...vals, [c.key]: { ...vals[c.key], score: e.target.value } })}
          />
        </div>
      ))}
      <label>
        Comentário para o agente
        <textarea value={comment} onChange={(e) => setComment(e.target.value)} />
      </label>
      <div className="row">
        <button className="primary" type="submit">
          Registrar revisão
        </button>
      </div>
      {msg ? <Notice kind={msg.ok ? 'info' : 'danger'}>{msg.text}</Notice> : null}
    </form>
  );
}

function ContestBox({ d, own, isManager, onDone }: { d: EvalDetail; own: boolean; isManager: boolean; onDone: () => void }) {
  const [reason, setReason] = useState('');
  const [comment, setComment] = useState('');
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const contested = d.status === 'contested';
  if (!own && !(isManager && contested)) {
    return (
      <section className="card">
        <h2>Contestação</h2>
        <span className="small muted">{d.status.startsWith('contest_') ? `Contestação resolvida (${d.status === 'contest_upheld' ? 'mantida' : 'revisada'}).` : 'Sem contestação.'}</span>
      </section>
    );
  }
  async function run(fn: () => Promise<unknown>, ok: string) {
    try {
      await fn();
      setMsg({ ok: true, text: ok });
      onDone();
    } catch (e) {
      setMsg({ ok: false, text: errorText(e) });
    }
  }
  return (
    <section className="card">
      <h2>Contestação</h2>
      {contested ? (
        isManager ? (
          <>
            <label>
              Decisão (comentário)
              <textarea value={comment} onChange={(e) => setComment(e.target.value)} />
            </label>
            <div className="row">
              <button onClick={() => run(() => qaApi.resolveContest(d.id, { decision: 'upheld', comment }), 'Avaliação mantida.')} disabled={comment.length < 3}>
                Manter avaliação
              </button>
              <span className="small muted">Para revisar a nota, use o formulário de revisão.</span>
            </div>
          </>
        ) : (
          <Notice kind="info">Sua contestação está com o supervisor.</Notice>
        )
      ) : (
        <>
          <label>
            Por que você discorda?
            <textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Cite o trecho e o horário da gravação" />
          </label>
          <div className="row">
            <button disabled={reason.trim().length < 5} onClick={() => run(() => qaApi.contest(d.id, reason), 'Contestação enviada.')}>
              Contestar avaliação
            </button>
          </div>
        </>
      )}
      {msg ? <Notice kind={msg.ok ? 'info' : 'danger'}>{msg.text}</Notice> : null}
    </section>
  );
}

function Reprocess({ rid }: { rid: string }) {
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  async function go(mode: 'full' | 'analysis') {
    const reason = window.prompt(mode === 'full' ? 'Motivo para transcrever e avaliar de novo:' : 'Motivo para reavaliar (sem nova transcrição):');
    if (!reason) return;
    try {
      const r = await qaApi.reprocess(rid, mode, reason);
      setMsg({ ok: true, text: `Reprocessamento na fila (execução ${r.run}, ${r.status}).` });
    } catch (e) {
      setMsg({ ok: false, text: errorText(e) });
    }
  }
  return (
    <div className="stack">
      <div className="row">
        <button onClick={() => go('analysis')}>Reavaliar</button>
        <button onClick={() => go('full')}>Transcrever de novo</button>
      </div>
      {msg ? <Notice kind={msg.ok ? 'info' : 'danger'}>{msg.text}</Notice> : null}
    </div>
  );
}
