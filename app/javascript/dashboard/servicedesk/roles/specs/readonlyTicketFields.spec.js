import { mount } from '@vue/test-utils';
import { computed, ref } from 'vue';
import MultiselectDropdown from 'shared/components/ui/MultiselectDropdown.vue';
import MultiselectDropdownItems from 'shared/components/ui/MultiselectDropdownItems.vue';
import TicketCcChips from 'dashboard/components-next/Conversation/TicketCcChips.vue';
import TicketFields from 'dashboard/routes/dashboard/conversation/TicketFields.vue';

// ServiceDesk M13: na tela do ticket, quem não tem ticket.edit (Agente light, Colaborador) vê os campos só
// para leitura (o backend responde 403 a qualquer alteração).

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: key => key }),
}));
vi.mock('dashboard/composables', () => ({ useAlert: vi.fn() }));
vi.mock('dashboard/api/inbox/conversation', () => ({
  default: { update: vi.fn(), addCc: vi.fn(), removeCc: vi.fn() },
}));
const canEdit = ref(true);
vi.mock('dashboard/servicedesk/roles/useSdRolePermissions', () => ({
  useSdRolePermissions: () => ({
    canEditTicket: computed(() => canEdit.value),
    canEditTags: computed(() => canEdit.value),
  }),
}));

const global = {
  mocks: { $t: key => key },
  stubs: { RouterLink: { template: '<a><slot /></a>' } },
};

describe('MultiselectDropdown readonly', () => {
  const options = [
    { id: 1, name: 'Ana' },
    { id: 2, name: 'Bia' },
  ];

  it('editável: sem cadeado e sem marca de somente leitura', () => {
    const wrapper = mount(MultiselectDropdown, {
      props: { options, selectedItem: options[0] },
      global,
    });
    expect(wrapper.find('button').attributes('data-readonly')).toBeUndefined();
    expect(wrapper.find('.i-lucide-lock').exists()).toBe(false);
  });

  it('mostra o valor e não abre a lista quando é somente leitura', async () => {
    const wrapper = mount(MultiselectDropdown, {
      props: { options, selectedItem: options[0], readonly: true },
      global,
    });
    const button = wrapper.find('button');
    expect(button.attributes('data-readonly')).toBe('true');
    expect(wrapper.find('.i-lucide-lock').exists()).toBe(true);
    expect(wrapper.text()).toContain('Ana');
    await button.trigger('click');
    expect(wrapper.find('div.visible').exists()).toBe(false);
    expect(wrapper.findComponent(MultiselectDropdownItems).exists()).toBe(
      false
    );
    expect(wrapper.emitted('select')).toBeUndefined();
  });
});

describe('TicketCcChips readonly', () => {
  it('sem permissão: mostra os CCs sem remover nem adicionar', () => {
    const wrapper = mount(TicketCcChips, {
      props: { conversationId: 1, emails: ['a@x.test'], readonly: true },
      global,
    });
    expect(wrapper.text()).toContain('a@x.test');
    expect(wrapper.find('[data-testid=ticket-cc-input]').exists()).toBe(false);
    expect(wrapper.find('button').exists()).toBe(false);
  });

  it('com permissão: mantém o campo e o botão de remover', () => {
    const wrapper = mount(TicketCcChips, {
      props: { conversationId: 1, emails: ['a@x.test'] },
      global,
    });
    expect(wrapper.find('[data-testid=ticket-cc-input]').exists()).toBe(true);
    expect(wrapper.find('button').exists()).toBe(true);
  });
});

describe('TicketFields conforme o papel', () => {
  const conversation = {
    id: 7,
    account_id: 1,
    ticket_type: 'task',
    due_at: Date.UTC(2026, 9, 20, 15) / 1000,
  };

  it('Agente light: tipo e vencimento só para leitura', () => {
    canEdit.value = false;
    const wrapper = mount(TicketFields, { props: { conversation }, global });
    expect(
      wrapper
        .find('[data-testid=ticket-type] button')
        .attributes('data-readonly')
    ).toBe('true');
    const due = wrapper.find('[data-testid=ticket-due-date]');
    expect(due.element.tagName).toBe('P');
    expect(wrapper.find('input[type=date]').exists()).toBe(false);
  });

  it('Agente: tipo e vencimento editáveis', () => {
    canEdit.value = true;
    const wrapper = mount(TicketFields, { props: { conversation }, global });
    expect(
      wrapper
        .find('[data-testid=ticket-type] button')
        .attributes('data-readonly')
    ).toBeUndefined();
    expect(wrapper.find('input[type=date]').exists()).toBe(true);
  });
});
