import { flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import Index from '../Index.vue';
import { settingsFixture } from './fixtures';

const client = {
  getSettings: vi.fn(),
  saveSettings: vi.fn(),
  testSettings: vi.fn(),
  rotateWebhookSecret: vi.fn(),
};
vi.mock('../sdOpsClient', () => ({ createSdOpsClient: () => client }));

const dispatch = vi.fn();
const getters = {
  getCurrentUser: ref({ id: 1, access_token: 'token-pessoal-ficticio' }),
  getCurrentAccountId: ref(4),
  'agents/getAgents': ref([
    { id: 11, name: 'Ana Teste', email: 'ana.teste@exemplo.test' },
    { id: 12, name: 'Bruno Fictício', email: 'bruno.ficticio@exemplo.test' },
  ]),
  'teams/getTeams': ref([
    { id: 1, name: 'Suporte' },
    { id: 2, name: 'Financeiro' },
  ]),
};
vi.mock('dashboard/composables/store', () => ({
  useStore: () => ({ dispatch }),
  useMapGetter: key => getters[key],
}));
const useAlert = vi.fn();
vi.mock('dashboard/composables', () => ({
  useAlert: (...a) => useAlert(...a),
}));
vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key, params) =>
      params && typeof params === 'object'
        ? `${key} ${JSON.stringify(params)}`
        : key,
    te: () => false,
  }),
}));
vi.mock('shared/helpers/clipboard', () => ({ copyTextToClipboard: vi.fn() }));

const mountPage = () =>
  mount(Index, {
    global: {
      mocks: { $t: key => key },
      stubs: {
        SettingsLayout: {
          props: ['isLoading', 'loadingMessage'],
          template:
            '<main><slot name="header" /><slot v-if="!isLoading" name="body" /></main>',
        },
        BaseSettingsHeader: {
          props: ['title', 'description'],
          template: '<header>{{ title }}<slot name="actions" /></header>',
        },
      },
    },
  });

describe('Configurações > Telefonia 55PBX', () => {
  beforeEach(() => {
    Object.values(client).forEach(f => f.mockReset());
    useAlert.mockReset();
    client.getSettings.mockResolvedValue(settingsFixture());
  });

  it('carrega pelo sd-ops e mostra as seções, o checklist e os segredos mascarados', async () => {
    const w = mountPage();
    await flushPromises();
    expect(client.getSettings).toHaveBeenCalled();
    expect(dispatch).toHaveBeenCalledWith('agents/get');
    const sections = w
      .findAll('[data-test^="section-"]')
      .map(x => x.attributes('data-test'));
    expect(sections).toEqual(
      ['STATUS', 'API', 'WEBHOOK', 'RECORDINGS', 'DIAL', 'URA', 'MAPS']
        .concat(['TICKETS', 'HOURS', 'N8N'])
        .map(s => `section-${s}`)
    );
    expect(
      w.findAll('[data-test^="check-"]').map(x => x.attributes('data-test'))
    ).toEqual([
      'check-D1',
      'check-D2',
      'check-D3',
      'check-D4',
      'check-MAPS',
      'check-ENABLED',
    ]);
    const key = w.find('[data-test="field-pbx_api_key"]');
    expect(key.find('[data-test="secret-status"]').text()).toContain(
      '"last4":"ABCD"'
    );
    expect(key.find('input[type="password"]').exists()).toBe(false); // só aparece ao "Substituir"
    expect(w.find('[data-test="webhook-masked-url"]').text()).toContain('••••');
    // S3 só aparece com storage s3
    expect(w.find('[data-test="field-s3_bucket"]').exists()).toBe(false);
    // o botão Salvar começa desabilitado (nada alterado)
    expect(w.find('[data-test="save"]').attributes('disabled')).toBeDefined();
  });

  it('salvar envia só o que mudou (segredo vazio mantém) e recarrega com a resposta', async () => {
    const saved = settingsFixture();
    saved.version = 4;
    saved.fields.dial_jwt = {
      ...saved.fields.dial_jwt,
      defined: true,
      last4: '1234',
      source: 'panel',
    };
    client.saveSettings.mockResolvedValue(saved);
    const w = mountPage();
    await flushPromises();
    const jwt = w.find('[data-test="field-dial_jwt"]');
    await jwt.find('[data-test="secret-edit"]').trigger('click');
    await jwt.find('input[type="password"]').setValue('jwt-ficticio-1234');
    await w.find('[data-test="save"]').trigger('click');
    await flushPromises();
    expect(client.saveSettings).toHaveBeenCalledWith({
      version: 3,
      values: {},
      secrets: { dial_jwt: 'jwt-ficticio-1234' },
    });
    expect(useAlert).toHaveBeenCalledWith('SD_TELEPHONY.SAVED');
    expect(
      w.find('[data-test="field-dial_jwt"] [data-test="secret-status"]').text()
    ).toContain('1234');
    expect(w.html()).not.toContain('jwt-ficticio-1234');
  });

  it('erro de validação do sd-ops aparece por campo', async () => {
    client.saveSettings.mockRejectedValue(
      Object.assign(new Error('há campos inválidos'), {
        status: 422,
        code: 'validation',
        extra: { fields: { allowed_ips: 'IP/CIDR inválido: x' } },
      })
    );
    const w = mountPage();
    await flushPromises();
    await w.find('[data-test="field-allowed_ips"] input').setValue('x');
    await w.find('[data-test="save"]').trigger('click');
    await flushPromises();
    expect(w.find('[data-test="field-errors"]').text()).toContain(
      'IP/CIDR inválido: x'
    );
  });

  it('testar conexão mostra o resultado por item', async () => {
    client.testSettings.mockResolvedValue({
      tested_at: '2026-10-14T12:00:00Z',
      items: [
        {
          id: 'report02',
          status: 'ok',
          detail: 'Report02 respondeu com a chave',
        },
        {
          id: 'recordings',
          status: 'error',
          detail: 'host vsa19.55pbx.com não alcançável',
        },
        {
          id: 'dial',
          status: 'missing',
          detail: 'faltam credenciais da discagem (D4)',
        },
      ],
    });
    const w = mountPage();
    await flushPromises();
    await w.find('[data-test="test"]').trigger('click');
    await flushPromises();
    expect(client.testSettings).toHaveBeenCalledWith(undefined); // nada alterado: testa o salvo
    const items = w.findAll('[data-test^="test-"][data-status]');
    expect(
      items.map(i => [i.attributes('data-test'), i.attributes('data-status')])
    ).toEqual([
      ['test-report02', 'ok'],
      ['test-recordings', 'error'],
      ['test-dial', 'missing'],
    ]);
    expect(w.find('[data-test="test-recordings"]').text()).toContain(
      'não alcançável'
    );
  });

  it('gerar novo segredo mostra a URL completa uma vez', async () => {
    client.rotateWebhookSecret.mockResolvedValue({
      url: 'https://helpdesk.exemplo.test/integracoes/55pbx/webhook/abc123',
      last4: 'c123',
    });
    const w = mountPage();
    await flushPromises();
    await w.find('[data-test="webhook-rotate"]').trigger('click');
    await w.find('[data-test="webhook-rotate-confirm"]').trigger('click');
    await flushPromises();
    expect(client.rotateWebhookSecret).toHaveBeenCalled();
    expect(w.find('[data-test="webhook-full-url"]').text()).toContain(
      '/webhook/abc123'
    );
  });

  it('agente comum (403) vê a mensagem de permissão', async () => {
    client.getSettings.mockRejectedValue(
      Object.assign(new Error(''), { status: 403, code: 'forbidden' })
    );
    const w = mountPage();
    await flushPromises();
    expect(w.find('[data-test="load-error"]').text()).toContain(
      'SD_TELEPHONY.ERRORS.FORBIDDEN'
    );
  });
});
