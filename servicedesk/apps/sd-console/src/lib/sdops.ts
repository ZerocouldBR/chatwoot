/**
 * Cliente do sd-ops (A2), REST /sd-ops/api/v1 (WEBHOOK_CONTRACTS.md §8.4–8.7, CTI_AUTH.md).
 * As respostas são normalizadas de forma tolerante (envelope `data` opcional). As capacidades do CTI vêm
 * SÓ de GET /capabilities (dial, webphone, callbacks, recordings, ura): nada de sondagem ou heurística.
 * Capacidade não informada = função DESABILITADA (nunca simulada).
 */
import { ApiError, http, qs, type Query } from './http';

export const SDOPS = '/sd-ops/api/v1';

export type Role = 'agente' | 'supervisor' | 'qa' | 'admin';
export interface Me {
  email: string;
  name: string;
  tenant: string;
  roles: Role[];
}
const ROLE: Record<string, Role> = { agent: 'agente', agente: 'agente', administrator: 'admin', admin: 'admin', supervisor: 'supervisor', qa: 'qa' };

function unwrap<T = Record<string, unknown>>(d: unknown): T {
  if (d && typeof d === 'object' && 'data' in (d as object) && !Array.isArray(d)) return (d as { data: T }).data;
  return d as T;
}

export function parseMe(raw: unknown): Me {
  const d = unwrap<Record<string, any>>(raw) || {};
  const u = (d.user && typeof d.user === 'object' ? d.user : d) as Record<string, any>;
  const t = d.tenant_id ?? d.tenant;
  return {
    email: String(u.email || ''),
    name: String(u.name || u.email || ''),
    tenant: String(t && typeof t === 'object' ? t.slug || t.id : t || ''),
    roles: ((d.roles || u.roles || []) as string[]).map((r) => ROLE[String(r).toLowerCase()] || (r as Role)),
  };
}

export async function me(): Promise<Me> {
  return parseMe(await http(`${SDOPS}/auth/me`));
}

export interface SessionOut {
  session_token: string;
  csrf_token?: string;
  expires_at?: string;
}
export async function createSession(chatwootToken: string, accountId: number | string): Promise<SessionOut> {
  return unwrap(await http(`${SDOPS}/auth/session`, { method: 'POST', json: { chatwoot_token: chatwootToken, account_id: accountId } }));
}
export async function logout() {
  await http(`${SDOPS}/auth/logout`, { method: 'POST' }).catch(() => undefined);
}

export interface Capability {
  enabled: boolean;
  mode?: string;
  reason?: string;
  url?: string;
  branch?: string;
}
/** Nomes publicados pelo sd-ops em GET /capabilities. */
export const CAPABILITY_NAMES = ['dial', 'webphone', 'callbacks', 'recordings', 'ura'] as const;
export type CapabilityName = (typeof CAPABILITY_NAMES)[number];
export type Capabilities = Partial<Record<CapabilityName | string, Capability>>;

const opt = (v: unknown) => (v === null || v === undefined || v === '' ? undefined : String(v));

/** GET /sd-ops/api/v1/capabilities: {capabilities: {dial|webphone|callbacks|recordings|ura: {enabled, mode, reason, url}}}.
 *  É a ÚNICA fonte das capacidades do CTI. 404/405 (sd-ops antigo) => null: a UI desabilita tudo e explica. */
export async function capabilities(): Promise<Capabilities | null> {
  try {
    const d = unwrap<Record<string, any>>(await http(`${SDOPS}/capabilities`));
    const src = (d.capabilities || d) as Record<string, any>;
    const out: Capabilities = {};
    Object.entries(src).forEach(([k, v]) => {
      if (typeof v === 'boolean') out[k] = { enabled: v };
      else if (v && typeof v === 'object') {
        const c: Capability = { enabled: !!v.enabled, mode: opt(v.mode), reason: opt(v.reason), url: opt(v.url) };
        if (opt(v.branch)) c.branch = opt(v.branch);
        out[k] = c;
      }
    });
    return out;
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 405)) return null;
    throw e;
  }
}

export interface Health {
  status?: string;
  enabled?: boolean;
  mock?: boolean;
  env?: string;
}
export async function health(): Promise<Health> {
  return unwrap(await http(`${SDOPS}/health`));
}

export interface TicketRef {
  id: string;
  protocol?: string;
  status?: string;
  subject?: string;
  category?: string;
  priority?: string;
  assignee?: string;
  sla_due_at?: string;
  sla_state?: string;
}
export interface CallRef {
  id: string;
  direction?: string;
  started_at?: string;
  answered_at?: string;
  ended_at?: string;
  outcome?: string;
  talk_s?: number;
  wait_s?: number;
  queue?: string;
  branch?: string;
  agent_email?: string;
  ticket_id?: string;
  conversation_id?: number | string;
  status?: string;
  recordings?: { id: string; duration_s?: number; mime?: string; status?: string }[];
  ura?: Record<string, string>;
}
export interface Context {
  contact?: { id?: number | string; name?: string; phone?: string; email?: string; preferred_channel?: string };
  identification?: string;
  tickets: TicketRef[];
  last_calls: CallRef[];
  callbacks: { id: string; due_at?: string; status?: string; reason?: string }[];
  active_call?: CallRef | null;
  recurring_subjects?: { label: string; count: number }[];
  owner?: string;
}

/** Estado de SLA a partir de sd-ops ticket.sla = [{metric, status, breached, due_at}]. */
export function slaState(sla: unknown): string | undefined {
  if (!Array.isArray(sla) || !sla.length) return undefined;
  if (sla.some((x: any) => x.breached)) return 'violado';
  const soon = sla.some((x: any) => x.status !== 'stopped' && x.due_at && new Date(x.due_at).getTime() - Date.now() < 3600_000);
  return soon ? 'em_risco' : 'no_prazo';
}

function normTicket(t: any): TicketRef {
  return { ...t, id: String(t.id), sla_state: t.sla_state || slaState(t.sla), assignee: t.assignee || t.assignee_name };
}

function normCall(c: any): CallRef {
  const ura = c.ura && typeof c.ura === 'object' ? c.ura : c.ura ? { URA: String(c.ura) } : undefined;
  return { ...c, id: String(c.id), status: c.status || c.state, ura };
}

/** GET /context (sd-ops): open_tickets, recent_calls, active_call, callbacks_pending. (O `dial` que ainda vem no
 *  /context é ignorado pela UI: a capacidade vale só pelo GET /capabilities.) */
export async function context(q: Query): Promise<Context> {
  const d = unwrap<Record<string, any>>(await http(`${SDOPS}/context${qs(q)}`)) || {};
  const contact = d.contact ? { ...d.contact, phone: d.contact.phone_number || d.phone_e164 } : d.phone_e164 ? { phone: d.phone_e164 } : undefined;
  return {
    contact,
    identification: d.identification,
    tickets: (d.open_tickets || d.tickets || []).map(normTicket),
    last_calls: (d.recent_calls || d.last_calls || []).map(normCall),
    callbacks: d.callbacks_pending || d.callbacks || [],
    active_call: d.active_call ? normCall(d.active_call) : null,
    recurring_subjects: d.recurring_subjects || [],
    owner: d.owner || d.assignee,
  };
}

export async function calls(q: Query): Promise<CallRef[]> {
  const d = unwrap<any>(await http(`${SDOPS}/calls${qs(q)}`));
  return (Array.isArray(d) ? d : d?.items || []).map(normCall);
}

export async function recordingUrl(id: string): Promise<{ url: string; expires_at?: string; expires_in?: number }> {
  return unwrap(await http(`${SDOPS}/recordings/${encodeURIComponent(id)}/url`));
}

export interface DialResult {
  dial_id?: string;
  status: string;
  simulated?: boolean;
  message?: string;
  provider_call_id?: string;
}
export async function dial(body: { phone: string; ticket_id?: string; conversation_id?: number | string; contact_id?: number | string }): Promise<DialResult> {
  return unwrap(await http(`${SDOPS}/dial`, { method: 'POST', json: body }));
}

export async function createCallback(body: Record<string, unknown>) {
  return unwrap(await http(`${SDOPS}/callbacks`, { method: 'POST', json: body }));
}

export async function ticketNote(ticketId: string, body: Record<string, unknown>) {
  return unwrap(await http(`${SDOPS}/tickets/${encodeURIComponent(ticketId)}/notes`, { method: 'POST', json: body }));
}

export async function ticketTransition(ticketId: string, to: string, reason: string) {
  return unwrap(await http(`${SDOPS}/tickets/${encodeURIComponent(ticketId)}/transitions`, { method: 'POST', json: { to, reason } }));
}

/** /metrics/telephony devolve {groups: {total, "queue=X", "day=AAAA-MM-DD", ...}, callbacks}. Busca por fila,
 *  por dia e por ramal (3 chamadas com group_by; todas trazem o total) e junta num objeto só. */
export async function metricsTelephony(q: Query): Promise<Record<string, any>> {
  const [byQueue, byDay, byBranch] = await Promise.all(
    ['queue', 'day', 'branch'].map((g) =>
      http<Record<string, any>>(`${SDOPS}/metrics/telephony${qs({ ...q, group_by: g })}`).then((x) => unwrap<Record<string, any>>(x)),
    ),
  );
  const groups = (d: Record<string, any>, prefix: string) =>
    Object.entries(d?.groups || {})
      .filter(([k]) => k.startsWith(prefix + '='))
      .map(([k, v]) => ({ key: k.slice(prefix.length + 1), ...(v as object) }) as Record<string, any>);
  return {
    ...(byQueue?.groups?.total || byQueue || {}),
    retornos: byQueue?.callbacks || {},
    por_fila: groups(byQueue, 'queue').map((r) => ({ ...r, fila: r.key, tma_s: r.tma_receptivo_s })),
    serie_diaria: groups(byDay, 'day')
      .map((r) => ({ ...r, dia: r.key }))
      .sort((a, b) => (a.dia < b.dia ? -1 : 1)),
    por_ramal: groups(byBranch, 'branch').map((r) => ({ ...r, ramal: r.key, tma_s: r.tma_receptivo_s ?? r.tma_ativo_s })),
    fonte: byQueue?.fonte,
  };
}
export async function metricsTickets(q: Query): Promise<Record<string, any>> {
  return unwrap(await http(`${SDOPS}/metrics/tickets${qs(q)}`));
}
