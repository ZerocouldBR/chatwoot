/**
 * HTTP com a sessão do sd-ops (CTI_AUTH.md): cookie `sdops_session` (mesmo site) e/ou
 * `Authorization: Bearer <session_token>` guardado SÓ EM MEMÓRIA (nunca localStorage).
 * Erros sempre viram ApiError com o código do servidor; nada é tratado como sucesso por omissão.
 */
export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

let sessionToken: string | null = null;
let csrfToken: string | null = null;
const listeners = new Set<() => void>();

export function setSession(token: string | null, csrf: string | null = null) {
  sessionToken = token;
  csrfToken = csrf;
}
export function hasBearer() {
  return !!sessionToken;
}
export function onUnauthorized(fn: () => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export type Query = Record<string, string | number | boolean | null | undefined>;

export function qs(q?: Query) {
  if (!q) return '';
  const p = new URLSearchParams();
  Object.entries(q).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
}

export async function http<T>(url: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  if (sessionToken) headers.set('Authorization', `Bearer ${sessionToken}`);
  const method = (init.method || 'GET').toUpperCase();
  if (method !== 'GET' && csrfToken) headers.set('X-SD-CSRF', csrfToken);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set('Content-Type', 'application/json');
    body = JSON.stringify(init.json);
  }
  let res: Response;
  try {
    res = await fetch(url, { ...init, method, headers, body, credentials: 'include' });
  } catch {
    throw new ApiError(0, 'network', 'Serviço indisponível (falha de rede).');
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get('content-type') || '';
  const data = ct.includes('json') ? await res.json().catch(() => null) : await res.text();
  if (!res.ok) {
    const d = (data && typeof data === 'object' ? ((data as { detail?: unknown }).detail ?? data) : {}) as {
      error?: string;
      message?: string;
    };
    if (res.status === 401) listeners.forEach((l) => l());
    throw new ApiError(res.status, d.error || `http_${res.status}`, d.message || `Erro HTTP ${res.status}`);
  }
  return data as T;
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 0) return e.message;
    if (e.status === 401) return 'Sessão expirada ou inválida. Entre novamente.';
    if (e.status === 403) return 'Você não tem permissão para esta ação.';
    if (e.status === 404) return 'Não encontrado (ou sem acesso).';
    return e.message;
  }
  return 'Erro inesperado.';
}
