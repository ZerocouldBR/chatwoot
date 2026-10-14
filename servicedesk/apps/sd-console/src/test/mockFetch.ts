import { vi } from 'vitest';

export type Handler = (url: string, init: RequestInit & { body?: any }) => { status?: number; json?: unknown; text?: string } | undefined;

/** fetch falso por rota (prefixo "MÉTODO /caminho"); registra as chamadas. */
export function mockFetch(routes: Record<string, Handler | { status?: number; json?: unknown; text?: string }>) {
  const calls: { method: string; url: string; body: any; headers: Headers }[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const method = (init.method || 'GET').toUpperCase();
    const body = typeof init.body === 'string' ? JSON.parse(init.body) : init.body;
    calls.push({ method, url, body, headers: new Headers(init.headers) });
    const key = Object.keys(routes)
      .filter((k) => {
        const [m, p] = k.split(' ');
        return m === method && url.split('?')[0].endsWith(p);
      })
      .sort((a, b) => b.length - a.length)[0];
    const r = key ? routes[key] : undefined;
    const out = typeof r === 'function' ? r(url, { ...init, body }) : r;
    if (!out) return new Response(JSON.stringify({ detail: { error: 'not_found', message: 'não encontrado' } }), { status: 404, headers: { 'content-type': 'application/json' } });
    if (out.text !== undefined) return new Response(out.text, { status: out.status || 200, headers: { 'content-type': 'text/csv' } });
    return new Response(JSON.stringify(out.json ?? {}), { status: out.status || 200, headers: { 'content-type': 'application/json' } });
  });
  vi.stubGlobal('fetch', fn);
  return calls;
}

// Formato real do GET /sd-ops/api/v1/auth/me
export const ME = { kind: 'user', tenant_id: 'dev55', user_id: 1, email: 'ana@exemplo.test', name: 'Ana Teste', roles: ['agente'], scopes: [] };
export const SUP = { kind: 'user', tenant_id: 'dev55', user_id: 3, email: 'sup@exemplo.test', name: 'Sup Teste', roles: ['qa', 'supervisor'], scopes: [] };
