/**
 * /cti — Dashboard App do Chatwoot (Módulo 3): cabeçalho CTI, contexto, registro/disposição e
 * pós-atendimento (gravação, transcrição, resumo IA, QA, CSAT, próximos passos).
 * Ações só ficam ativas quando o sd-ops reporta a capacidade; resultado mostrado é sempre o real.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Player } from '../components/Player';
import { SessionGate, useSession } from '../components/Session';
import { Badge, CapButton, Empty, ErrorBox, Loading, Notice } from '../components/ui';
import { useAppContext, type AppContext } from '../lib/chatwoot';
import { ALERT_LABEL, CALL_OUTCOME, CALL_STATE, fmtClock, fmtDateTime, scoreClass, STATUS_LABEL } from '../lib/format';
import { errorText } from '../lib/http';
import { qaApi, type RecordingAnalysis, type SummaryItem } from '../lib/qa';
import * as sdops from '../lib/sdops';

export default function Cti() {
  const { ctx, embedded } = useAppContext();
  return (
    <SessionGate accountId={ctx?.conversation?.account_id}>
      <CtiInner ctx={ctx} embedded={embedded} />
    </SessionGate>
  );
}

function useTick(active: boolean) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

export function CtiInner({ ctx, embedded }: { ctx: AppContext | null; embedded: boolean }) {
  const { me } = useSession();
  const params = new URLSearchParams(window.location.search);
  const conversationId = ctx?.conversation?.id ?? (params.get('conversation_id') ? Number(params.get('conversation_id')) : undefined);
  const contact = ctx?.contact || ctx?.conversation?.meta?.sender;
  const contactId = contact?.id;
  const phone = contact?.phone_number || undefined;

  const [caps, setCaps] = useState<sdops.Capabilities | null | undefined>(undefined);
  const [health, setHealth] = useState<sdops.Health | null>(null);
  const [data, setData] = useState<sdops.Context | null>(null);
  const [calls, setCalls] = useState<sdops.CallRef[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!conversationId && !contactId && !phone) return;
    setLoading(true);
    setError('');
    try {
      const [c, cl] = await Promise.all([
        sdops.context({ conversation_id: conversationId, contact_id: contactId, phone }),
        sdops.calls({ conversation_id: conversationId }).catch(() => [] as sdops.CallRef[]),
      ]);
      setData(c);
      setCalls(cl.length ? cl : c.last_calls);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoading(false);
    }
  }, [conversationId, contactId, phone]);

  useEffect(() => {
    sdops.health().then(setHealth).catch(() => setHealth(null));
  }, []);
  // Capacidades: só o GET /capabilities do sd-ops (por usuário: ramal, papel, credenciais da 55PBX). Sem
  // sondagem nem heurística; o que não vier fica desabilitado com explicação. Recarrega com o contexto.
  useEffect(() => {
    let alive = true;
    sdops
      .capabilities()
      .catch(() => null)
      .then((c) => {
        if (alive) setCaps(c);
      });
    return () => {
      alive = false;
    };
  }, [data]);
  useEffect(() => {
    load();
  }, [load]);

  if (!conversationId && !contactId) {
    return (
      <div className="main compact">
        {embedded ? (
          <Loading label="Aguardando o contexto do Chatwoot" />
        ) : (
          <Notice kind="info">
            Abra esta tela pela aba <strong>CTI</strong> de um ticket no ServiceDesk (Dashboard App). Fora do Chatwoot, informe
            <code> ?conversation_id=</code> na URL.
          </Notice>
        )}
      </div>
    );
  }

  return (
    <div className="main compact">
      {health?.mock || caps?.dial?.mode === 'mock' ? (
        <Notice kind="mock">sd-ops em MODO MOCK (DEV): dados fictícios, nenhuma ligação real.</Notice>
      ) : null}
      {caps === null ? (
        <Notice kind="warn">O sd-ops não informou as capacidades disponíveis. Discar, webphone e retorno ficam desabilitados.</Notice>
      ) : null}
      {error ? <ErrorBox error={error} onRetry={load} /> : null}
      <CtiHeader contactName={contact?.name} phone={phone} data={data} caps={caps} conversationId={conversationId} onChanged={load} />
      <div className="grid cols-2">
        <ContextCard data={data} loading={loading} />
        <RegisterCard data={data} conversationId={conversationId} onSaved={load} />
      </div>
      <PostCall calls={calls} agentEmail={me.email} />
    </div>
  );
}

function CtiHeader({
  contactName,
  phone,
  data,
  caps,
  conversationId,
  onChanged,
}: {
  contactName?: string;
  phone?: string;
  data: sdops.Context | null;
  caps: sdops.Capabilities | null | undefined;
  conversationId?: number;
  onChanged: () => void;
}) {
  const call = data?.active_call || null;
  const ticket = data?.tickets?.[0];
  const now = useTick(!!call && !call.ended_at);
  const since = call?.answered_at || call?.started_at;
  const elapsed = since ? (now - new Date(since).getTime()) / 1000 : null;
  const [dialMsg, setDialMsg] = useState<{ kind: 'info' | 'warn' | 'danger' | 'mock'; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [cbOpen, setCbOpen] = useState(false);
  const target = phone || data?.contact?.phone;

  async function doDial() {
    if (!target) return;
    setBusy(true);
    setDialMsg(null);
    try {
      const r = await sdops.dial({ phone: target, ticket_id: ticket?.id, conversation_id: conversationId, contact_id: data?.contact?.id });
      if (r.simulated || r.status === 'mock') setDialMsg({ kind: 'mock', text: r.message || 'MODO MOCK: nenhuma ligação foi feita.' });
      else if (r.status === 'accepted') setDialMsg({ kind: 'info', text: `${r.message || 'Ligação solicitada à 55PBX.'} Atenda no seu webphone.` });
      else setDialMsg({ kind: 'warn', text: r.message || `Resposta da 55PBX: ${r.status}` });
    } catch (e) {
      setDialMsg({ kind: 'danger', text: `Discagem não realizada: ${errorText(e)}` });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-label="Cabeçalho CTI">
      <div className="cti-head">
        <div className="stack" style={{ gap: 2 }}>
          <span className="who">{contactName || data?.contact?.name || 'Contato sem nome'}</span>
          <span className="mono muted">{target || 'sem telefone'}</span>
          {data?.identification === 'ambiguous' ? (
            <Badge kind="warn" title="Mais de um cadastro com este telefone: confirme a identidade antes de mesclar">
              identificação ambígua
            </Badge>
          ) : null}
        </div>
        <dl className="kv">
          <dt>Ramal</dt>
          <dd>{call?.branch || '-'}</dd>
          <dt>Fila</dt>
          <dd>{call?.queue || '-'}</dd>
          <dt>Estado</dt>
          <dd>{call ? <Badge kind={call.ended_at ? '' : 'ok'}>{call.ended_at ? 'encerrada' : CALL_STATE[call.status || ''] || call.status || 'em andamento'}</Badge> : 'sem chamada ativa'}</dd>
          <dt>Tempo</dt>
          <dd className="mono">{elapsed !== null ? fmtClock(elapsed) : '-'}</dd>
          <dt>Protocolo</dt>
          <dd className="mono">{ticket?.protocol || '-'}</dd>
        </dl>
      </div>
      <div className="row" style={{ alignItems: 'flex-start' }}>
        <CapButton cap={target ? caps?.dial : { enabled: false, reason: 'Contato sem telefone.' }} capName="dial" busy={busy} onClick={doDial} primary>
          Discar
        </CapButton>
        <CapButton cap={caps?.webphone} capName="webphone" onClick={() => caps?.webphone?.url && window.open(caps.webphone.url, 'sd-webphone', 'noopener,width=420,height=720')}>
          Abrir webphone
        </CapButton>
        <CapButton cap={caps?.callbacks} capName="callbacks" onClick={() => setCbOpen((v) => !v)}>
          Registrar retorno
        </CapButton>
      </div>
      {dialMsg ? <Notice kind={dialMsg.kind}>{dialMsg.text}</Notice> : null}
      {cbOpen ? <CallbackForm ticketId={ticket?.id} phone={target} callId={call?.id || data?.last_calls?.[0]?.id} onDone={() => { setCbOpen(false); onChanged(); }} /> : null}
    </section>
  );
}

function CallbackForm({ ticketId, phone, callId, onDone }: { ticketId?: string; phone?: string; callId?: string; onDone: () => void }) {
  const [due, setDue] = useState('');
  const [reason, setReason] = useState('');
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    try {
      if (!phone) throw new Error('sem telefone');
      await sdops.createCallback({ number_e164: phone, ticket_id: ticketId, call_id: callId, due_at: new Date(due).toISOString(), reason });
      setMsg({ ok: true, text: 'Retorno registrado no sd-ops.' });
      setTimeout(onDone, 800);
    } catch (err) {
      setMsg({ ok: false, text: errorText(err) });
    }
  }
  return (
    <form className="stack" onSubmit={save} aria-label="Registrar retorno">
      <fieldset>
        <label>
          Retornar em
          <input type="datetime-local" required value={due} onChange={(e) => setDue(e.target.value)} />
        </label>
        <label>
          Motivo
          <input required value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} />
        </label>
      </fieldset>
      <div className="row">
        <button className="primary" type="submit">Salvar retorno</button>
      </div>
      {msg ? <Notice kind={msg.ok ? 'info' : 'danger'}>{msg.text}</Notice> : null}
    </form>
  );
}

function ContextCard({ data, loading }: { data: sdops.Context | null; loading: boolean }) {
  const last = data?.last_calls?.[0];
  const ura = data?.active_call?.ura || last?.ura;
  return (
    <section className="card" aria-label="Contexto do cliente">
      <h2>Contexto</h2>
      {loading && !data ? <Loading /> : null}
      {data ? (
        <>
          <div>
            <h3>Tickets abertos</h3>
            {data.tickets.length ? (
              <ul className="stack" style={{ listStyle: 'none', padding: 0, margin: '6px 0 0' }}>
                {data.tickets.map((t) => (
                  <li key={t.id} className="row">
                    <span className="mono">{t.protocol || t.id}</span>
                    <Badge>{t.status || '-'}</Badge>
                    {t.sla_state ? <Badge kind={t.sla_state === 'violado' ? 'danger' : t.sla_state === 'em_risco' ? 'warn' : 'ok'}>SLA {t.sla_state.replace('_', ' ')}</Badge> : null}
                    <span className="muted small">{t.subject || t.category || ''}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>Nenhum ticket aberto.</Empty>
            )}
          </div>
          <dl className="kv">
            <dt>Último atendimento</dt>
            <dd>{last ? `${fmtDateTime(last.started_at)} · ${last.direction || ''} · ${CALL_OUTCOME[last.outcome || ''] || last.outcome || ''}` : '-'}</dd>
            <dt>Responsável</dt>
            <dd>{data.owner || data.tickets[0]?.assignee || '-'}</dd>
            <dt>Canal preferido</dt>
            <dd>{data.contact?.preferred_channel || '-'}</dd>
            <dt>Assuntos recorrentes</dt>
            <dd>{data.recurring_subjects?.length ? data.recurring_subjects.map((s) => `${s.label} (${s.count})`).join(', ') : '-'}</dd>
            <dt>Retornos pendentes</dt>
            <dd>{data.callbacks.length ? data.callbacks.map((c) => fmtDateTime(c.due_at)).join(', ') : 'nenhum'}</dd>
            {ura
              ? Object.entries(ura).map(([k, v]) => (
                  <Fragment2 key={k} k={`URA: ${k}`} v={v} />
                ))
              : null}
          </dl>
        </>
      ) : null}
    </section>
  );
}

function Fragment2({ k, v }: { k: string; v: string }) {
  return (
    <>
      <dt>{k}</dt>
      <dd>{v}</dd>
    </>
  );
}

const DISPOSITIONS = ['resolvido_na_ligacao', 'encaminhado', 'aguardando_cliente', 'retorno_agendado', 'sem_contato', 'improcedente'];

function RegisterCard({ data, conversationId, onSaved }: { data: sdops.Context | null; conversationId?: number; onSaved: () => void }) {
  const ticket = data?.tickets?.[0];
  // Registro = nota/disposição no ticket aberto (POST /tickets/{id}/notes). Não é capacidade do provedor:
  // depende só de haver ticket; a autorização continua no servidor (tickets:write / papel agente).
  const cap: sdops.Capability = ticket ? { enabled: true } : { enabled: false, reason: 'Nenhum ticket aberto para este contato.' };
  const [f, setF] = useState({ category: '', reason: '', description: '', actions: '', result: '', disposition: '', pending: '', schedule_at: '', internal_note: '', close: false });
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setF({ ...f, [k]: e.target.type === 'checkbox' ? (e.target as HTMLInputElement).checked : e.target.value });

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!ticket) return;
    setBusy(true);
    setMsg(null);
    try {
      // NoteIn do sd-ops: kind (registro|disposicao|nota_interna), body, disposition{...}, call_id, post_to_chatwoot
      await sdops.ticketNote(ticket.id, {
        kind: 'registro',
        body: [f.description, f.internal_note ? `Nota interna: ${f.internal_note}` : ''].filter(Boolean).join(' / ') || null,
        disposition: {
          categoria: f.category,
          motivo: f.reason,
          disposicao: f.disposition,
          acoes: f.actions,
          resultado: f.result,
          pendencias: f.pending,
          agendamento: f.schedule_at ? new Date(f.schedule_at).toISOString() : null,
          conversation_id: conversationId,
        },
        call_id: data?.active_call?.id || data?.last_calls?.[0]?.id,
        post_to_chatwoot: true,
      });
      if (f.close) await sdops.ticketTransition(ticket.id, 'resolvido', f.disposition || 'registro do atendimento');
      setMsg({ ok: true, text: f.close ? 'Registro salvo e ticket marcado como resolvido.' : 'Registro salvo no ticket.' });
      onSaved();
    } catch (err) {
      setMsg({ ok: false, text: `Não salvo: ${errorText(err)}` });
    } finally {
      setBusy(false);
    }
  }

  const disabledWhy = !ticket ? 'Sem ticket aberto neste contexto.' : !cap ? 'O sd-ops não informou a capacidade de registrar no ticket.' : !cap.enabled ? cap.reason || 'Registro desabilitado no sd-ops.' : '';
  return (
    <form className="card" onSubmit={save} aria-label="Registro do atendimento">
      <div className="card-head">
        <h2>Registro e disposição</h2>
        {ticket ? <span className="mono small muted">{ticket.protocol}</span> : null}
      </div>
      <fieldset disabled={!!disabledWhy || busy}>
        <label>
          Categoria
          <input value={f.category} onChange={set('category')} placeholder="ex.: Reservas" />
        </label>
        <label>
          Motivo
          <input value={f.reason} onChange={set('reason')} placeholder="ex.: Voucher não recebido" />
        </label>
        <label>
          Disposição
          <select value={f.disposition} onChange={set('disposition')} required>
            <option value="">Selecione…</option>
            {DISPOSITIONS.map((d) => (
              <option key={d} value={d}>
                {d.replace(/_/g, ' ')}
              </option>
            ))}
          </select>
        </label>
        <label>
          Agendamento
          <input type="datetime-local" value={f.schedule_at} onChange={set('schedule_at')} />
        </label>
      </fieldset>
      <fieldset disabled={!!disabledWhy || busy} style={{ gridTemplateColumns: '1fr' }}>
        <label>
          Descrição
          <textarea value={f.description} onChange={set('description')} />
        </label>
        <label>
          Ações realizadas e resultado
          <textarea value={f.actions} onChange={set('actions')} />
        </label>
        <label>
          Pendências
          <input value={f.pending} onChange={set('pending')} />
        </label>
        <label>
          Nota interna
          <textarea value={f.internal_note} onChange={set('internal_note')} />
        </label>
        <label style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <input type="checkbox" checked={f.close} onChange={set('close')} style={{ minHeight: 0 }} /> Marcar o ticket como resolvido
        </label>
      </fieldset>
      {disabledWhy ? <span className="small muted">{disabledWhy}</span> : null}
      <div className="row">
        <button className="primary" type="submit" disabled={!!disabledWhy || busy}>
          {busy ? 'Salvando…' : 'Salvar registro'}
        </button>
      </div>
      {msg ? <Notice kind={msg.ok ? 'info' : 'danger'}>{msg.text}</Notice> : null}
    </form>
  );
}

function PostCall({ calls, agentEmail }: { calls: sdops.CallRef[]; agentEmail: string }) {
  const recs = useMemo(
    () => calls.flatMap((c) => (c.recordings || []).map((r) => ({ ...r, call: c }))),
    [calls],
  );
  const [rid, setRid] = useState<string | null>(null);
  useEffect(() => {
    if (!rid && recs.length) setRid(recs[0].id);
  }, [recs, rid]);
  return (
    <section className="card" aria-label="Pós-atendimento">
      <div className="card-head">
        <h2>Pós-atendimento</h2>
        {recs.length > 1 ? (
          <select aria-label="Gravação" value={rid || ''} onChange={(e) => setRid(e.target.value)}>
            {recs.map((r) => (
              <option key={r.id} value={r.id}>
                {fmtDateTime(r.call.started_at)} · {fmtClock(r.duration_s)}
              </option>
            ))}
          </select>
        ) : null}
      </div>
      {rid ? <Analysis rid={rid} agentEmail={agentEmail} /> : <Empty>Nenhuma gravação autorizada para este ticket.</Empty>}
    </section>
  );
}

function Analysis({ rid, agentEmail }: { rid: string; agentEmail: string }) {
  const [a, setA] = useState<RecordingAnalysis | null>(null);
  const [error, setError] = useState('');
  const [seek, setSeek] = useState<{ t: number; n: number } | null>(null);
  const load = useCallback(() => {
    setError('');
    qaApi
      .recording(rid)
      .then(setA)
      .catch((e) => setError(errorText(e)));
  }, [rid]);
  useEffect(() => {
    setA(null);
    load();
  }, [load]);
  if (error) return <ErrorBox error={`Análise indisponível: ${error}`} onRetry={load} />;
  if (!a) return <Loading />;
  const pending = ['pending', 'running', 'waiting_audio'].includes(a.job.status);
  return (
    <div className="grid cols-2">
      <div className="stack">
        {pending ? (
          <Notice kind="info">
            Processando ({a.job.status === 'waiting_audio' ? 'aguardando a gravação' : a.job.stage || 'na fila'}). Atualize em instantes.
          </Notice>
        ) : null}
        {a.job.status === 'failed' ? <Notice kind="danger">Falha no processamento ({a.job.error_code}). A equipe de QA foi notificada.</Notice> : null}
        {a.transcription?.status === 'partial' ? <Notice kind="warn">Transcrição parcial: parte do áudio não foi transcrita.</Notice> : null}
        <Player recordingId={rid} segments={a.segments} seekTo={seek} />
        {a.transcription ? (
          <span className="small muted">
            Transcrição automática ({a.transcription.model}, idioma {a.transcription.language || '?'}); dados pessoais mascarados.
            {a.transcription.diarization === 'none' ? ' Falantes não identificados (áudio mono).' : ''}
          </span>
        ) : null}
      </div>
      <div className="stack" style={{ gap: 12 }}>
        <SummaryBox a={a} onChanged={load} agentEmail={agentEmail} />
        <QaBox a={a} onSeek={(t) => setSeek({ t, n: Date.now() })} />
      </div>
    </div>
  );
}

const SUMMARY_FIELDS: [string, string][] = [
  ['motivo', 'Motivo'],
  ['problema', 'Problema'],
  ['contexto', 'Contexto'],
  ['solucao', 'Solução'],
  ['retorno', 'Retorno'],
  ['proxima_acao', 'Próxima ação'],
];
const SUMMARY_LISTS: [string, string][] = [
  ['verificacoes', 'Verificações'],
  ['pendencias', 'Pendências'],
  ['compromissos', 'Compromissos'],
];

function Item({ it }: { it: SummaryItem }) {
  return (
    <>
      {it.texto}{' '}
      <Badge kind={it.tipo === 'fato' ? 'ok' : 'warn'} title={it.tipo === 'fato' ? 'Dito na ligação (com trecho de evidência)' : 'Interpretação da IA: confira'}>
        {it.tipo === 'fato' ? 'fato' : 'inferência'}
      </Badge>
    </>
  );
}

function SummaryBox({ a, onChanged }: { a: RecordingAnalysis; onChanged: () => void; agentEmail: string }) {
  const s = a.summary;
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  if (!s) return <Empty>Resumo ainda não gerado.</Empty>;
  const c = s.final_content || s.content;
  async function act(action: 'approve' | 'reject') {
    setBusy(true);
    try {
      await qaApi.reviewSummary(s!.id, action);
      onChanged();
    } catch (e) {
      setMsg(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="stack">
      <div className="card-head">
        <h3>Resumo</h3>
        <Badge kind={s.status === 'draft' ? 'warn' : s.status === 'rejected' ? 'danger' : 'ok'}>
          {s.status === 'draft' ? 'rascunho IA: revisar' : s.status === 'approved' ? 'aprovado' : s.status === 'edited' ? 'editado' : 'rejeitado'}
        </Badge>
      </div>
      <dl className="kv">
        {SUMMARY_FIELDS.map(([k, label]) =>
          c[k] ? (
            <Fragment3 key={k} label={label}>
              <Item it={c[k]} />
            </Fragment3>
          ) : null,
        )}
        {SUMMARY_LISTS.map(([k, label]) =>
          (c[k] || []).length ? (
            <Fragment3 key={k} label={label}>
              <ul style={{ margin: 0, paddingLeft: 16 }}>
                {(c[k] as SummaryItem[]).map((it, i) => (
                  <li key={i}>
                    <Item it={it} />
                  </li>
                ))}
              </ul>
            </Fragment3>
          ) : null,
        )}
        {c.classificacao_sugerida?.categoria ? (
          <Fragment3 label="Classificação sugerida">
            {c.classificacao_sugerida.categoria} / {c.classificacao_sugerida.subcategoria || '-'} <Badge kind="warn">inferência</Badge>
          </Fragment3>
        ) : null}
      </dl>
      {s.status === 'draft' ? (
        <div className="row">
          <button className="primary" disabled={busy} onClick={() => act('approve')}>
            Aprovar resumo
          </button>
          <button disabled={busy} onClick={() => act('reject')}>
            Rejeitar
          </button>
        </div>
      ) : null}
      {msg ? <Notice kind="danger">{msg}</Notice> : null}
      {a.csat ? (
        <span className="small">
          CSAT: <strong>{a.csat.score}/{a.csat.scale_max}</strong> {a.csat.comment ? `· "${a.csat.comment}"` : ''}
        </span>
      ) : (
        <span className="small muted">CSAT: sem resposta.</span>
      )}
    </div>
  );
}

function Fragment3({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </>
  );
}

function QaBox({ a, onSeek }: { a: RecordingAnalysis; onSeek: (t: number) => void }) {
  const ev = a.evaluation;
  if (!ev) return null;
  return (
    <div className="stack">
      <div className="card-head">
        <h3>Qualidade (recomendação da IA)</h3>
        {ev.final_score !== null ? (
          <Badge kind={scoreClass(ev.final_score)}>{Math.round(ev.final_score)}/100{ev.human_score !== null ? ' · revisado' : ''}</Badge>
        ) : (
          <Badge kind="warn">sem nota: evidência insuficiente</Badge>
        )}
      </div>
      <ul className="stack" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {ev.criteria.map((c) => (
          <li key={c.key} className={`crit ${c.status}`}>
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <strong className="small">{c.label}</strong>
              <span className="small muted">
                {STATUS_LABEL[c.status]}
                {c.score !== null ? ` · ${Math.round(c.score)}` : ''}
              </span>
            </div>
            {c.suggestion ? <div className="small">Sugestão: {c.suggestion}</div> : null}
            {c.evidence_text && c.evidence_start_s !== null && c.evidence_start_s !== undefined ? (
              <button className="link small" onClick={() => onSeek(c.evidence_start_s!)}>
                {fmtClock(c.evidence_start_s)} “{c.evidence_text}”
              </button>
            ) : null}
          </li>
        ))}
      </ul>
      {a.alerts.length ? (
        <div className="row">
          {a.alerts.map((al) => (
            <Badge key={al.id} kind={al.severity === 'alta' ? 'danger' : 'warn'} title={al.evidence_text || ''}>
              {ALERT_LABEL[al.alert_type || ''] || al.title}
            </Badge>
          ))}
        </div>
      ) : null}
      <span className="small muted">A nota da IA é uma recomendação. A avaliação definitiva é do supervisor/QA.</span>
    </div>
  );
}
