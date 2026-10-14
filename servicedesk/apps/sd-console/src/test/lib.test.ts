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
  it('parseMe lê o /auth/me real (plano, tenant_id)', () => {
    expect(sdops.parseMe({ kind: 'user', tenant_id: 'dev55', user_id: 1, email: 'a@b', name: 'A', roles: ['agente'], scopes: [] })).toEqual({
      email: 'a@b', name: 'A', tenant: 'dev55', roles: ['agente'],
    });
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
  it('capacidades no formato real do sd-ops (envelope capabilities, null vira ausente, ramal)', async () => {
    mockFetch({
      'GET /capabilities': {
        json: {
          tenant_id: 'dev55', env: 'dev',
          capabilities: {
            dial: { enabled: true, mode: 'mock', reason: 'MODO MOCK (DEV): nenhuma ligação real', branch: '5005' },
            webphone: { enabled: false, mode: 'external', url: null, reason: 'webphone não configurado' },
            callbacks: { enabled: true, reason: null },
            recordings: { enabled: true, mode: 'local', reason: null },
            ura: { enabled: false, mode: 'menu_dinamico', reason: 'sem credencial' },
          },
        },
      },
    });
    const c = (await sdops.capabilities())!;
    expect(Object.keys(c).sort()).toEqual([...sdops.CAPABILITY_NAMES].sort());
    expect(c.dial).toEqual({ enabled: true, mode: 'mock', reason: 'MODO MOCK (DEV): nenhuma ligação real', url: undefined, branch: '5005' });
    expect(c.webphone).toEqual({ enabled: false, mode: 'external', reason: 'webphone não configurado', url: undefined });
    expect(c.callbacks).toEqual({ enabled: true, mode: undefined, reason: undefined, url: undefined });
    expect(c.ura!.enabled).toBe(false);
  });
});

describe('métricas do sd-ops (formato real: groups + group_by)', () => {
  it('junta total, por fila, por dia e por ramal', async () => {
    const total = { recebidas: 10, atendidas: 8, tma_receptivo_s: 150, por_resultado: { answered: 8, abandoned_queue: 2 } };
    mockFetch({
      'GET /metrics/telephony': (url) => {
        const g = new URL('http://x' + url).searchParams.get('group_by');
        const extra = g === 'queue' ? { 'queue=FILA_SUPORTE_1': { recebidas: 10, tma_receptivo_s: 150 } }
          : g === 'day' ? { 'day=2026-10-13': { recebidas: 6 }, 'day=2026-10-12': { recebidas: 4 } }
          : { 'branch=5005': { atendidas: 8, tma_receptivo_s: 150 } };
        return { json: { groups: { total, ...extra }, callbacks: { pendentes: 1 } } };
      },
    });
    const t = normTelephony(await sdops.metricsTelephony({ from: '2026-10-01' }));
    expect(t.recebidas).toBe(10);
    expect(t.tma_s).toBe(150);
    expect(t.por_fila[0]).toMatchObject({ fila: 'FILA_SUPORTE_1', tma_s: 150 });
    expect(t.serie.map((s: any) => s.dia)).toEqual(['2026-10-12', '2026-10-13']);
    expect(t.por_ramal[0]).toMatchObject({ ramal: '5005' });
    expect(t.motivos).toContainEqual({ motivo: 'abandoned_queue', total: 2 });
    expect(t.retornos.pendentes).toBe(1);
  });
  it('tickets: dicionários viram listas e segundos viram horas', () => {
    const k = normTickets({ backlog_agora: 4, tempo_resolucao_medio_s: 7200, fcr: 0.5, sla: { resolution: { cumprimento: 0.9, vencidas: 1 }, first_response: { cumprimento: 1, vencidas: 0 } }, por_canal: { telefone: 3 } });
    expect(k.backlog).toBe(4);
    expect(k.tempo_resolucao_h).toBe(2);
    expect(k.sla_cumprido).toBe(0.9);
    expect(k.vencidos).toBe(1);
    expect(k.por_canal).toEqual([{ canal: 'telefone', criados: 3 }]);
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
