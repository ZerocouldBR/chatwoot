import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { Player } from '../components/Player';
import { SessionGate } from '../components/Session';
import { CapButton } from '../components/ui';
import { setSession } from '../lib/http';
import { CtiInner } from '../pages/Cti';
import Dashboards from '../pages/Dashboards';
import QaEvaluation from '../pages/QaEvaluation';
import { ME, mockFetch, SUP } from './mockFetch';

beforeAll(() => {
  window.HTMLMediaElement.prototype.play = vi.fn(async () => undefined);
  window.HTMLMediaElement.prototype.pause = vi.fn();
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => {
  vi.unstubAllGlobals();
  setSession(null);
});

const SEGS = [
  { idx: 0, start_s: 0, end_s: 4, text: 'B2B Reservas, bom dia!', low_confidence: false },
  { idx: 1, start_s: 5, end_s: 9, text: 'O CPF é [CPF].', low_confidence: true },
];

describe('CapButton', () => {
  it('sem capacidade informada: desabilitado e com explicação', () => {
    render(<CapButton cap={null} capName="dial" onClick={() => undefined}>Discar</CapButton>);
    expect(screen.getByRole('button', { name: 'Discar' })).toBeDisabled();
    expect(screen.getByText(/não informou a capacidade/)).toBeInTheDocument();
  });
  it('capacidade desligada mostra o motivo do sd-ops; ligada habilita', () => {
    const { rerender } = render(<CapButton cap={{ enabled: false, reason: 'Credenciais 55PBX ausentes' }} capName="dial" onClick={() => undefined}>Discar</CapButton>);
    expect(screen.getByText('Credenciais 55PBX ausentes')).toBeInTheDocument();
    rerender(<CapButton cap={{ enabled: true }} capName="dial" onClick={() => undefined}>Discar</CapButton>);
    expect(screen.getByRole('button', { name: 'Discar' })).toBeEnabled();
  });
});

describe('Player', () => {
  it('URL temporária do sd-ops, navegação pela transcrição, velocidade, marcação e registro de acesso', async () => {
    const calls = mockFetch({
      'GET /recordings/r1/url': { json: { url: '/sd-ops/api/v1/recordings/stream/tok', expires_in: 300 } },
      'GET /recordings/r1/marks': { json: { items: [] } },
      'POST /access-log': { json: { ok: true } },
      'POST /recordings/r1/marks': { status: 201, json: { id: 9 } },
    });
    render(<Player recordingId="r1" segments={SEGS} />);
    await waitFor(() => expect(document.querySelector('audio')).toHaveAttribute('src', '/sd-ops/api/v1/recordings/stream/tok'));
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Reproduzir' }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith('/access-log') && c.body.action === 'play')).toBe(true));
    await user.click(screen.getByText('O CPF é [CPF].'));
    expect((document.querySelector('audio') as HTMLAudioElement).currentTime).toBe(5);
    await user.selectOptions(screen.getByLabelText('Velocidade de reprodução'), '1.5');
    expect((document.querySelector('audio') as HTMLAudioElement).playbackRate).toBe(1.5);
    await user.type(screen.getByLabelText('Rótulo da marcação'), 'dados pessoais');
    await user.click(screen.getByRole('button', { name: /Marcar/ }));
    await waitFor(() => expect(screen.getByText(/dados pessoais/)).toBeInTheDocument());
    expect(calls.find((c) => c.method === 'POST' && c.url.endsWith('/marks'))!.body).toMatchObject({ label: 'dados pessoais', start_s: 5 });
    expect(screen.queryByText(/download/i)).toBeNull();
  });
  it('erro de gravação é mostrado, não silenciado', async () => {
    mockFetch({ 'GET /recordings/r2/url': { status: 403, json: { error: 'forbidden' } }, 'GET /recordings/r2/marks': { json: { items: [] } } });
    render(<Player recordingId="r2" segments={[]} />);
    expect(await screen.findByText(/Gravação indisponível: Você não tem permissão/)).toBeInTheDocument();
  });
});

function withSession(ui: React.ReactNode) {
  return (
    <MemoryRouter initialEntries={['/qa/avaliacoes/5']}>
      <SessionGate accountId={1}>
        <Routes>
          <Route path="/qa/avaliacoes/:id" element={ui} />
          <Route path="*" element={ui} />
        </Routes>
      </SessionGate>
    </MemoryRouter>
  );
}

// Formato REAL do GET /sd-ops/api/v1/context (sd_ops/api.py, commit a0f8e93717)
const CTX = {
  contact: { id: 55, name: 'Roberto Fictício', phone_number: '+5511900000001', email: null, identifier: null },
  phone_e164: '+5511900000001',
  identification: 'unique',
  open_tickets: [
    { id: 'tk1', protocol: 'DEV-2026-000123', status: 'em_atendimento', subject: 'Voucher',
      sla: [{ metric: 'resolution', status: 'running', breached: false, due_at: new Date(Date.now() + 600000).toISOString() }] },
  ],
  recent_calls: [],
  active_call: { id: 'c1', state: 'active', branch: '5005', queue: 'FILA_SUPORTE_1', answered_at: new Date().toISOString(), recordings: [] },
  callbacks_pending: [],
  dial: { available: true, reason: null }, // ignorado pela UI: a capacidade vale só pelo GET /capabilities
};

// Formato REAL do GET /sd-ops/api/v1/capabilities (sd_ops/api.py, integração final)
const CAPS_OFF = {
  tenant_id: 'dev55', env: 'prod', integration_enabled: true,
  capabilities: {
    dial: { enabled: false, mode: 'disabled', reason: 'click-to-call desativado (PBX_DIAL_MODE=disabled)' },
    webphone: { enabled: false, mode: 'external', url: null, reason: 'webphone da 55PBX não configurado no sd-ops (PBX_WEBPHONE_URL)' },
    callbacks: { enabled: false, reason: 'sem permissão para retornos' },
    recordings: { enabled: true, mode: 'local', reason: null },
    ura: { enabled: false, mode: 'menu_dinamico', reason: 'Menu Dinâmico (URA) sem credencial configurada para este tenant' },
  },
};
const CAPS_MOCK = {
  ...CAPS_OFF,
  env: 'dev',
  capabilities: {
    ...CAPS_OFF.capabilities,
    dial: { enabled: true, mode: 'mock', reason: 'MODO MOCK (DEV): nenhuma ligação real', branch: '5005' },
    webphone: { enabled: true, mode: 'external', url: 'https://fone.55pbx.test', reason: null },
    callbacks: { enabled: true, reason: null },
  },
};

describe('CTI', () => {
  it('pede login quando não há sessão e troca o token por sessão (token não fica no navegador)', async () => {
    const calls = mockFetch({
      'GET /auth/me': (_u, init) => (new Headers(init.headers).get('authorization') ? { json: ME } : { status: 401, json: {} }),
      'POST /auth/session': { json: { session_token: 'sess-xyz', csrf_token: 'c' } },
    });
    render(withSession(<div>conteúdo</div>));
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText('Token de acesso'), 'tok-chatwoot');
    await user.click(screen.getByRole('button', { name: 'Entrar' }));
    expect(await screen.findByText('conteúdo')).toBeInTheDocument();
    expect(calls.find((c) => c.url.endsWith('/auth/session'))!.body).toEqual({ chatwoot_token: 'tok-chatwoot', account_id: '1' });
    expect(window.localStorage.length).toBe(0);
  });

  it('sd-ops reporta discagem indisponível: botões desabilitados com o motivo real', async () => {
    const calls = mockFetch({
      'GET /auth/me': { json: ME }, 'GET /context': { json: CTX }, 'GET /calls': { json: { items: [] } },
      'GET /health': { json: { status: 'ok' } }, 'GET /capabilities': { json: CAPS_OFF },
    });
    render(withSession(<CtiInner ctx={{ conversation: { id: 101, account_id: 1 }, contact: { id: 55, name: 'Roberto Fictício', phone_number: '+5511900000001' } }} embedded />));
    expect(await screen.findByText('DEV-2026-000123', { selector: 'dd' })).toBeInTheDocument();
    expect(await screen.findByText('click-to-call desativado (PBX_DIAL_MODE=disabled)')).toBeInTheDocument();
    // o /context ainda diz dial.available=true: a UI NÃO usa (só o /capabilities vale)
    expect(screen.getByRole('button', { name: 'Discar' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Abrir webphone' })).toBeDisabled();
    expect(screen.getByText('webphone da 55PBX não configurado no sd-ops (PBX_WEBPHONE_URL)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Registrar retorno' })).toBeDisabled();
    expect(screen.getByText('sem permissão para retornos')).toBeInTheDocument();
    // sem sondagem de /callbacks
    expect(calls.some((c) => c.method === 'GET' && c.url.split('?')[0].endsWith('/callbacks'))).toBe(false);
    expect(screen.getByText('FILA_SUPORTE_1')).toBeInTheDocument();
    expect(screen.getByText('SLA em risco')).toBeInTheDocument();
  });

  it('discagem em modo mock aparece como MOCK, nunca como sucesso; erro da 55PBX aparece', async () => {
    let n = 0;
    mockFetch({
      'GET /auth/me': { json: ME },
      'GET /context': { json: CTX },
      'GET /calls': { json: { items: [] } },
      'GET /health': { json: { status: 'ok' } },
      'GET /capabilities': { json: CAPS_MOCK },
      'POST /dial': () =>
        ++n === 1
          ? { json: { status: 'mock', simulated: true, message: 'MODO MOCK (DEV): nenhuma ligação foi feita' } }
          : { status: 502, json: { error: 'rejected', message: 'E-mail inválido.' } },
    });
    render(withSession(<CtiInner ctx={{ conversation: { id: 101, account_id: 1 }, contact: { id: 55, phone_number: '+5511900000001' } }} embedded />));
    const user = userEvent.setup();
    const btn = await screen.findByRole('button', { name: 'Discar' });
    await waitFor(() => expect(btn).toBeEnabled());
    await user.click(btn);
    expect(await screen.findByText('MODO MOCK (DEV): nenhuma ligação foi feita')).toBeInTheDocument();
    expect(screen.getByText(/sd-ops em MODO MOCK/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Discar' }));
    expect(await screen.findByText('Discagem não realizada: E-mail inválido.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Abrir webphone' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Registrar retorno' })).toBeEnabled();
  });

  it('sd-ops sem GET /capabilities (404): tudo desabilitado e explicado, mesmo com dial no /context', async () => {
    mockFetch({ 'GET /auth/me': { json: ME }, 'GET /context': { json: CTX }, 'GET /calls': { json: { items: [] } }, 'GET /health': { json: { status: 'ok' } } });
    render(withSession(<CtiInner ctx={{ conversation: { id: 101, account_id: 1 }, contact: { id: 55, phone_number: '+5511900000001' } }} embedded />));
    expect(await screen.findByText(/O sd-ops não informou as capacidades disponíveis/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Discar' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Abrir webphone' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Registrar retorno' })).toBeDisabled();
  });
});

const DETAIL = {
  id: 5, recording_id: 'r1', agent_ref: 'bruno@exemplo.test', agent_name: 'Bruno', status: 'ai_completed', review_state: 'pendente',
  ai_score: 28, human_score: null, final_score: 28, created_at: '2026-10-13T18:00:00Z', open_tasks: 1, applicable_weight: 90,
  redistribution: { resultado: '1 critério não aplicável', regra: 'regra' }, warnings: [], llm_provider: 'mock', llm_model: 'regras-ptbr-v1',
  criteria: [
    { key: 'saudacao', label: 'Saudação e identificação', weight: 10, effective_weight: 11.1, status: 'not_observed', score: 0, evidence_text: 'Alô.', evidence_start_s: 0, confidence: 0.6, flags: [] },
    { key: 'registro', label: 'Registro e conformidade', weight: 10, effective_weight: 0, status: 'not_applicable', score: null, confidence: 0.5, flags: [] },
  ],
  human_reviews: [], rubric: { id: 1, code: 'padrao', version: 1, name: 'Rubrica padrão' }, prompt: { id: 1, kind: 'qa', version: 'v1', sha256: 'a'.repeat(64) },
  transcription: { id: 1, status: 'completed', provider: 'faster_whisper', model: 'small', language: 'pt', pii_counts: { cpf: 1 }, run: 1 },
  segments: SEGS, summary: null, tasks: [{ id: 3, kind: 'alert', alert_type: 'reclamacao', severity: 'alta', title: 'Reclamação', status: 'open', evidence_text: 'Vou registrar uma reclamação', evidence_start_s: 40, created_at: '' }],
  events: [], history: [{ id: 5, score: 28, status: 'ai_completed', is_current: true, rubric_version_id: 1, created_at: '2026-10-13T18:00:00Z' }],
};

describe('Console de QA', () => {
  it('mostra evidência, versões e envia só os critérios alterados na revisão', async () => {
    const calls = mockFetch({
      'GET /auth/me': { json: SUP },
      'GET /evaluations/5': { json: DETAIL },
      'GET /recordings/r1/url': { json: { url: '/a.mp3' } },
      'GET /recordings/r1/marks': { json: { items: [] } },
      'POST /evaluations/5/review': { json: { human_evaluation_id: 6, score: 40 } },
    });
    render(withSession(<QaEvaluation />));
    expect(await screen.findByText(/Rubrica padrão \(v1\)/)).toBeInTheDocument();
    expect(screen.getAllByText(/“Alô.”/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Reclamação/).length).toBeGreaterThan(0);
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText('Status de Saudação e identificação'), 'observed');
    const score = screen.getByLabelText('Nota de Saudação e identificação');
    await user.clear(score);
    await user.type(score, '40');
    await user.click(screen.getByRole('button', { name: 'Registrar revisão' }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith('/evaluations/5/review'))).toBe(true));
    const body = calls.find((c) => c.url.endsWith('/evaluations/5/review'))!.body;
    expect(body.criteria).toEqual([{ key: 'saudacao', status: 'observed', score: 40, justification: null }]);
    expect(await screen.findByText(/Revisão registrada. Nota final: 40/)).toBeInTheDocument();
  });

  it('agente pode contestar a própria avaliação', async () => {
    const calls = mockFetch({
      'GET /auth/me': { json: { ...ME, email: 'bruno@exemplo.test' } },
      'GET /evaluations/5': { json: DETAIL },
      'GET /recordings/r1/url': { json: { url: '/a.mp3' } },
      'GET /recordings/r1/marks': { json: { items: [] } },
      'POST /evaluations/5/contest': { json: { status: 'contested' } },
    });
    render(withSession(<QaEvaluation />));
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText('Por que você discorda?'), 'O cliente desligou antes, ver 00:40');
    await user.click(screen.getByRole('button', { name: 'Contestar avaliação' }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith('/contest'))).toBe(true));
    expect(screen.queryByRole('button', { name: 'Registrar revisão' })).toBeNull();
  });
});

describe('Dashboards', () => {
  it('supervisor vê telefonia, tickets e qualidade; filtros vão para a API', async () => {
    const calls = mockFetch({
      'GET /auth/me': { json: SUP },
      'GET /metrics/telephony': { json: { data: { recebidas: 120, atendidas: 100, abandonadas: 12, perdidas: 8, efetuadas: 300, tma_s: 163, tme_s: 21, nivel_servico: 0.82, taxa_abandono: 0.1, serie_diaria: [{ dia: '2026-10-12', recebidas: 60, abandonadas: 5 }, { dia: '2026-10-13', recebidas: 60, abandonadas: 7 }] } } },
      'GET /metrics/tickets': { json: { criados: 80, resolvidos: 70, backlog: 40, fcr: 0.6, por_canal: [{ canal: 'telefone', criados: 50 }] } },
      'GET /metrics/quality': { json: { transcritas: 2, gravacoes_recebidas: 2, taxa_sucesso: 1, qa_medio_final: 62.5, distribuicao: { '0-49': 1, '90-100': 1 }, criterios: [{ key: 'saudacao', label: 'Saudação', aplicavel: 2, falhas: 1, taxa_falha: 0.5, nao_aplicavel: 0, media: 50 }], csat: { respostas: 0 }, divergencia_ia_humano: {}, custo_ia: { llm_provider: 'mock', stt_provider: 'faster_whisper', estimado_brl: 0 }, serie_diaria: [] } },
    });
    render(
      <MemoryRouter>
        <SessionGate accountId={1}>
          <Dashboards />
        </SessionGate>
      </MemoryRouter>,
    );
    expect(await screen.findByText('120')).toBeInTheDocument();
    expect(screen.getByText('02:43')).toBeInTheDocument(); // TMA
    expect(await screen.findByText('80')).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole('tab', { name: 'Qualidade e IA' }));
    expect(await screen.findByText('62,5')).toBeInTheDocument();
    expect(screen.getByText(/modo MOCK/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Fila'), { target: { value: 'FILA_SUPORTE_1' } });
    await user.click(screen.getByRole('tab', { name: 'Supervisor' }));
    await user.click(screen.getByRole('button', { name: 'Aplicar filtros' }));
    await waitFor(() => expect(calls.some((c) => c.url.includes('/metrics/telephony') && c.url.includes('queue=FILA_SUPORTE_1'))).toBe(true));
  });
});
