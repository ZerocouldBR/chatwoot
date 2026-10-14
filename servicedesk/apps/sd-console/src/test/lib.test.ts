import { afterEach, describe, expect, it, vi } from 'vitest';
import { FETCH_INFO, originAllowed, parseContextMessage } from '../lib/chatwoot';
import { toCsv } from '../lib/csv';
import { ApiError, http, setSession } from '../lib/http';
import * as sdops from '../lib/sdops';
import { normTelephony, normTickets } from '../pages/Dashboards';
import { mockFetch } from './mockFetch';

afterEach(() => {
  vi.unstubAllGlobals();
  setSession(null);
});

describe('contexto do Dashboard App (Frame.vue)', () => {
  it('aceita só a mensagem appContext em JSON', () => {
    const ctx = parseContextMessage(JSON.stringify({ event: 'appContext', data: { conversation: { id: 7 }, theme: 'dark' } }));
    expect(ctx?.conversation?.id).toBe(7);
    expect(ctx?.theme).toBe('dark');
    expect(parseContextMessage({ event: 'appContext' })).toBeNull();
    expect(parseContextMessage('{"event":"outro"}')).toBeNull();
    expect(parseContextMessage('lixo')).toBeNull();
    expect(FETCH_INFO).toBe('chatwoot-dashboard-app:fetch-info');
  });
  it('filtra origem', () => {
    expect(originAllowed('https://helpdesk.ia4co.com', 'https://helpdesk.ia4co.com')).toBe(true);
    expect(originAllowed('https://malicioso.test', 'https://helpdesk.ia4co.com')).toBe(false);
    expect(originAllowed('http://localhost:13000', '')).toBe(true);
  });
});

describe('http + sd-ops', () => {
  it('envia Bearer da memória e CSRF em POST; erro vira ApiError', async () => {
    const calls = mockFetch({ 'POST /x': { status: 409, json: { error: 'dial_pending', message: 'Discagem pendente' } } });
    setSession('sess-1', 'csrf-1');
    await expect(http('/x', { method: 'POST', json: {} })).rejects.toMatchObject({ status: 409, code: 'dial_pending' });
    expect(calls[0].headers.get('authorization')).toBe('Bearer sess-1');
    expect(calls[0].headers.get('x-sd-csrf')).toBe('csrf-1');
  });
  it('falha de rede não é sucesso', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('down'); }));
    await expect(http('/y')).rejects.toBeInstanceOf(ApiError);
  });
  it('parseMe converte papéis do Chatwoot', () => {
    expect(sdops.parseMe({ data: { user: { email: 'a@b', name: 'A' }, tenant: { slug: 'b2b' }, roles: ['agent', 'administrator'] } })).toEqual({
      email: 'a@b', name: 'A', tenant: 'b2b', roles: ['agente', 'admin'],
    });
  });
  it('capacidades ausentes (404) => null', async () => {
    mockFetch({});
    expect(await sdops.capabilities()).toBeNull();
    mockFetch({ 'GET /capabilities': { json: { dial: { enabled: false, reason: 'sem credenciais' }, webphone: true } } });
    expect(await sdops.capabilities()).toEqual({ dial: { enabled: false, reason: 'sem credenciais', mode: undefined, url: undefined }, webphone: { enabled: true } });
  });
});

describe('normalizadores e CSV', () => {
  it('telefonia aceita nomes alternativos e nulos', () => {
    const t = normTelephony({ recebidas: 10, tma: { receptivo: 120, ativo: 60 }, nivel_servico: '0.8', by_queue: [{ fila: 'F' }] });
    expect(t.recebidas).toBe(10);
    expect(t.tma_s).toBe(120);
    expect(t.tma_ativo_s).toBe(60);
    expect(t.nivel_servico).toBe(0.8);
    expect(t.abandonadas).toBeNull();
    expect(t.por_fila).toHaveLength(1);
    expect(normTickets({ tempo_resolucao: { media_h: 5 } }).tempo_resolucao_h).toBe(5);
  });
  it('CSV com BOM, ";" e escape', () => {
    const csv = toCsv([{ a: 'x;y', b: 1.5 }], [{ key: 'a', label: 'A' }, { key: 'b', label: 'B' }]);
    expect(csv).toBe('﻿A;B\r\n"x;y";1,5\r\n');
  });
});
