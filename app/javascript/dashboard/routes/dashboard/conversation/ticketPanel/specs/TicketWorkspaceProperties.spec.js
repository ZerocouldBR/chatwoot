import { ref } from 'vue';
import { mount } from '@vue/test-utils';
import TicketWorkspaceProperties from '../TicketWorkspaceProperties.vue';

const isPropertiesOpen = ref(true);
const toggleProperties = vi.fn(() => {
  isPropertiesOpen.value = !isPropertiesOpen.value;
});

vi.mock('dashboard/servicedesk/workspace/useTicketWorkspace', () => ({
  useTicketWorkspace: () => ({ isPropertiesOpen, toggleProperties }),
}));

const stubs = {
  TicketPropertiesPanel: {
    props: ['conversationId', 'variant'],
    template:
      '<div class="panel" :data-variant="variant" :data-id="conversationId" />',
  },
  NextButton: {
    emits: ['click'],
    template: '<button v-bind="$attrs" @click="$emit(\'click\')" />',
  },
};

const mountColumn = () =>
  mount(TicketWorkspaceProperties, {
    props: { conversationId: 10 },
    global: {
      stubs,
      mocks: { $t: key => key },
      directives: { tooltip: {} },
    },
  });

describe('TicketWorkspaceProperties', () => {
  beforeEach(() => {
    isPropertiesOpen.value = true;
    toggleProperties.mockClear();
  });

  it('mostra a coluna de 300px com o painel em modo coluna', () => {
    const wrapper = mountColumn();
    const column = wrapper.find('[data-testid="ticket-workspace-properties"]');
    expect(column.exists()).toBe(true);
    expect(column.classes()).toContain('w-[300px]');
    const panel = wrapper.find('.panel');
    expect(panel.attributes('data-variant')).toBe('column');
    expect(panel.attributes('data-id')).toBe('10');
    expect(wrapper.text()).toContain(
      'SERVICEDESK_TICKET_PANEL.WORKSPACE.PROPERTIES'
    );
  });

  it('recolhe para o trilho e expande de novo', async () => {
    const wrapper = mountColumn();
    await wrapper
      .find('[data-testid="ticket-workspace-collapse"]')
      .trigger('click');
    expect(toggleProperties).toHaveBeenCalledTimes(1);
    expect(wrapper.find('[data-testid="ticket-workspace-rail"]').exists()).toBe(
      true
    );
    expect(wrapper.find('.panel').exists()).toBe(false);
    await wrapper
      .find('[data-testid="ticket-workspace-expand"]')
      .trigger('click');
    expect(wrapper.find('.panel').exists()).toBe(true);
  });
});
