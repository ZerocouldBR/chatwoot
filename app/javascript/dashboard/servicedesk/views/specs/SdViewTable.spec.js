import { mount } from '@vue/test-utils';
import { createStore } from 'vuex';
import SdViewTable from '../SdViewTable.vue';

const push = vi.fn();
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }));
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: key => key }) }));

const store = createStore({
  getters: {
    getCurrentAccountId: () => 1,
    getSelectedChat: () => ({ id: 2 }),
  },
});

const columns = [
  { key: 'number', i18n: 'NUMBER', title: 'ID' },
  { key: 'subject', i18n: 'SUBJECT', title: '' },
  { key: 'status', i18n: 'STATUS', title: 'Status' },
  { key: 'organization', i18n: 'ORGANIZATION', title: 'Organização' },
];
const conversations = [
  {
    id: 1,
    subject: 'Boleto',
    status: 'on_hold',
    company_name: 'Zeta',
    custom_attributes: { zd_status: 'Desenvolvimento' },
    meta: {},
  },
  {
    id: 2,
    subject: 'Acesso',
    status: 'open',
    company_name: 'Alfa',
    custom_attributes: {},
    meta: {},
  },
];

const factory = props =>
  mount(SdViewTable, {
    props: { conversations, columns, foldersId: 7, ...props },
    global: {
      plugins: [store],
      stubs: { TicketSlaBadge: true },
    },
  });

describe('SdViewTable', () => {
  it('renders the view columns with the Zendesk titles and the status label', () => {
    const wrapper = factory();
    const headers = wrapper.findAll('th').map(th => th.text());
    expect(headers).toEqual([
      'ID',
      'SD_VIEW_TABLE.COLUMNS.SUBJECT',
      'Status',
      'Organização',
    ]);
    const firstRow = wrapper.findAll('tbody tr')[0].findAll('td');
    expect(firstRow[0].text()).toBe('#1');
    expect(firstRow[1].text()).toBe('Boleto');
    expect(firstRow[2].text()).toContain('Desenvolvimento');
  });

  it('sorts locally the columns without server sort and emits the header sort', async () => {
    const wrapper = factory({
      activeSort: { column: 'organization', direction: 'asc', sortBy: null },
    });
    const firstCells = wrapper
      .findAll('tbody tr')
      .map(tr => tr.find('td').text());
    expect(firstCells).toEqual(['#2', '#1']);
    await wrapper.findAll('th')[3].trigger('click');
    expect(wrapper.emitted('sort')[0][0]).toEqual({
      column: 'organization',
      direction: 'desc',
    });
  });

  it('opens the ticket inside the view', async () => {
    const wrapper = factory();
    await wrapper.findAll('tbody tr')[0].trigger('click');
    expect(push).toHaveBeenCalledWith({
      path: '/app/accounts/1/custom_view/7/tickets/1',
    });
  });
});
