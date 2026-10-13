import { ref } from 'vue';
import { mount, flushPromises } from '@vue/test-utils';
import TicketPropertiesPanel from '../TicketPropertiesPanel.vue';

const dispatch = vi.fn(() => Promise.resolve());
const getters = {};
const uiSettings = ref({});

vi.mock('dashboard/composables', () => ({ useAlert: vi.fn() }));
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: key => key }) }));
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { accountId: 1 } }),
}));
vi.mock('dashboard/composables/store', async () => {
  const { computed } = await import('vue');
  return {
    useStore: () => ({ dispatch }),
    useMapGetter: key => computed(() => getters[key].value),
  };
});
vi.mock('dashboard/composables/useAgentsList', () => ({
  useAgentsList: () => ({ agentsList: ref([{ id: 7, name: 'Ana' }]) }),
}));
vi.mock('dashboard/composables/useUISettings', () => ({
  useUISettings: () => ({ uiSettings, updateUISettings: vi.fn() }),
}));
vi.mock('dashboard/api/companies', () => ({
  default: { show: vi.fn(() => Promise.resolve({ data: { name: 'ACME' } })) },
}));

const definitions = [
  {
    attribute_key: 'zd_formulario',
    attribute_display_name: 'Formulário',
    attribute_display_type: 'list',
    attribute_description: 'zendesk:ticket_form',
    attribute_values: ['Atendimento', 'Formulário TI', 'LGPD & Segurança'],
  },
  {
    attribute_key: 'zd_status',
    attribute_display_name: 'Status',
    attribute_display_type: 'list',
    attribute_description: 'zendesk:custom_status',
    attribute_values: ['Novo', 'Aberto', 'Pendente', 'Resolvido'],
  },
  {
    attribute_key: 'zd_tipo',
    attribute_display_name: 'Tipo',
    attribute_display_type: 'list',
    attribute_description: 'zendesk_field:20487384447387',
    attribute_values: ['Pergunta', 'Incidente'],
  },
  {
    attribute_key: 'zd_area_interna',
    attribute_display_name: 'Área interna',
    attribute_display_type: 'list',
    attribute_description: 'zendesk_field:21587135564955',
    attribute_values: ['Suporte', 'Financeiro'],
  },
  {
    attribute_key: 'zd_tabulacao',
    attribute_display_name: 'Tabulação',
    attribute_display_type: 'list',
    attribute_description: 'zendesk_field:21537600796443',
    attribute_values: ['A'],
  },
  {
    attribute_key: 'zd_motivos_ti',
    attribute_display_name: 'Motivos TI',
    attribute_display_type: 'list',
    attribute_description: 'zendesk_field:21797736040987',
    attribute_values: ['x'],
  },
  {
    attribute_key: 'zd_ticket_id',
    attribute_display_name: 'Nº ticket',
    attribute_display_type: 'number',
    attribute_description: 'zendesk:ticket_id',
    attribute_values: [],
  },
];

const chat = ref({});

const stubs = {
  MultiselectDropdown: {
    props: ['options', 'selectedItem'],
    emits: ['select'],
    template:
      '<div class="ms" :data-selected="selectedItem && selectedItem.name"></div>',
  },
  CustomAttribute: {
    props: ['attributeKey', 'label', 'value'],
    template: '<div class="ca" :data-key="attributeKey">{{ label }}</div>',
  },
  ConversationLabels: true,
  Avatar: true,
  NextButton: true,
  Icon: true,
  RouterLink: { template: '<a><slot /></a>' },
};

const mountPanel = (props = {}) =>
  mount(TicketPropertiesPanel, {
    props: { conversationId: 10, ...props },
    global: { stubs, mocks: { $t: key => key } },
  });

describe('TicketPropertiesPanel', () => {
  beforeEach(() => {
    dispatch.mockClear();
    chat.value = {
      id: 10,
      status: 'open',
      priority: null,
      custom_attributes: { zd_ticket_id: 123 },
      meta: { sender: { id: 5, name: 'Cliente', email: 'c@x.com' } },
    };
    getters.getSelectedChat = chat;
    getters.getCurrentUser = ref({ id: 7, name: 'Ana' });
    getters['teams/getTeams'] = ref([]);
    getters['contacts/getContact'] = ref(() => ({
      id: 5,
      additional_attributes: { company_name: 'Empresa X' },
    }));
    getters['attributes/getAttributesByModel'] = ref(() => definitions);
  });

  it('usa o formulário padrão e esconde campos condicionais', () => {
    const wrapper = mountPanel();
    const keys = wrapper
      .findAll('.ca')
      .map(node => node.attributes('data-key'));
    expect(keys).toContain('zd_area_interna');
    expect(keys).not.toContain('zd_tabulacao');
    expect(keys).not.toContain('zd_motivos_ti');
    expect(wrapper.text()).toContain('Empresa X');
    expect(wrapper.text()).toContain('SERVICEDESK_TICKET_PANEL.FORM.DEFAULT');
  });

  it('mostra o campo filho quando a condição é atendida', () => {
    chat.value.custom_attributes = { zd_area_interna: 'Suporte' };
    const keys = mountPanel()
      .findAll('.ca')
      .map(node => node.attributes('data-key'));
    expect(keys).toContain('zd_tabulacao');
  });

  it('troca os campos conforme o formulário', () => {
    chat.value.custom_attributes = { zd_formulario: 'Formulário TI' };
    const keys = mountPanel()
      .findAll('.ca')
      .map(node => node.attributes('data-key'));
    expect(keys).toContain('zd_motivos_ti');
    expect(keys).not.toContain('zd_area_interna');
  });

  it('status personalizado resolvido também resolve a conversa', async () => {
    const wrapper = mountPanel();
    const statusDropdown = wrapper
      .findAllComponents('.ms')
      .find(c => c.props('options')?.some(o => o.name === 'Resolvido'));
    statusDropdown.vm.$emit('select', { id: 4, name: 'Resolvido' });
    await flushPromises();
    expect(dispatch).toHaveBeenCalledWith('updateCustomAttributes', {
      conversationId: 10,
      customAttributes: { zd_ticket_id: 123, zd_status: 'Resolvido' },
    });
    expect(dispatch).toHaveBeenCalledWith('toggleStatus', {
      conversationId: 10,
      status: 'resolved',
    });
  });

  it('selo de status longo não é truncado e fica junto do número', () => {
    chat.value.status = 'snoozed';
    chat.value.custom_attributes = {
      zd_ticket_id: 990008,
      zd_status: 'Desenvolvimento Concluído',
    };
    const wrapper = mountPanel();
    const badge = wrapper.find('[data-testid="ticket-status-badge"]');
    expect(badge.text()).toBe('Desenvolvimento Concluído');
    expect(badge.classes()).not.toContain('truncate');
    expect(badge.classes()).toContain('whitespace-normal');
    expect(badge.attributes('data-category')).toBe('hold');
    expect(wrapper.find('[data-testid="ticket-number"]').classes()).toContain(
      'whitespace-nowrap'
    );
  });

  it('variante coluna (Agent Workspace) não tem a borda do painel embutido', () => {
    expect(mountPanel().find('section').classes()).toContain('border-b');
    expect(
      mountPanel({ variant: 'column' }).find('section').classes()
    ).not.toContain('border-b');
  });
});
