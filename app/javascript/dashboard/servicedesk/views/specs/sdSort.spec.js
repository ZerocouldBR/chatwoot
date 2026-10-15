import { sortComparator } from 'dashboard/store/modules/conversations/helpers';
import { isSdSortKey } from '../sdSort';

const sortWith = (list, key) =>
  [...list].sort((a, b) => sortComparator(a, b, key)).map(c => c.id);

describe('sdSort (store comparators of the Zendesk views)', () => {
  const tickets = [
    {
      id: 1,
      status: 'resolved',
      next_sla_breach_at: null,
      subject: 'boleto',
      meta: { team: { name: 'Suporte' } },
      last_activity_at: 10,
      sd_clock: { solved_at: 50 },
    },
    {
      id: 2,
      status: 'new_ticket',
      next_sla_breach_at: 200,
      subject: 'Acesso',
      meta: {},
      last_activity_at: 20,
    },
    {
      id: 3,
      status: 'on_hold',
      next_sla_breach_at: 100,
      subject: '',
      meta: { team: { name: 'Cadastro' } },
      last_activity_at: 30,
    },
  ];

  it('keeps the server order of the view instead of falling back to activity', () => {
    expect(sortWith(tickets, 'sd_sla_asc')).toEqual([3, 2, 1]);
    expect(sortWith(tickets, 'sd_status_asc')).toEqual([2, 3, 1]);
    expect(sortWith(tickets, 'sd_group_asc')).toEqual([3, 1, 2]);
    expect(sortWith(tickets, 'sd_subject_asc')).toEqual([2, 1, 3]);
    expect(sortWith(tickets, 'sd_id_desc')).toEqual([3, 2, 1]);
    expect(sortWith(tickets, 'sd_solved_desc')).toEqual([1, 3, 2]);
    expect(sortWith(tickets, 'sd_channel_asc')).toEqual([1, 2, 3]);
  });

  it('knows its keys', () => {
    expect(isSdSortKey('sd_sla_asc')).toBe(true);
    expect(isSdSortKey('last_activity_at_desc')).toBe(false);
  });
});
