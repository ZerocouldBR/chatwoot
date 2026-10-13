import {
  TICKET_COLUMNS,
  SORT_DIRECTION,
  serverSortToColumn,
  isServerSortColumn,
  getTicketSubject,
  getTicketRequester,
  getTicketOrganization,
  getTicketStatus,
  compareColumnValues,
  sortRows,
  rangeBetween,
  normalizeText,
} from '../ticketTableHelpers';
import { readStoredMode, writeStoredMode } from '../useTicketListMode';

describe('ticketTableHelpers', () => {
  describe('getTicketSubject', () => {
    it('uses mail_subject when present', () => {
      expect(
        getTicketSubject({
          additional_attributes: { mail_subject: '  Reserva 123 ' },
          messages: [],
        })
      ).toEqual({ text: 'Reserva 123', isPreview: false });
    });

    it('falls back to the last message preview', () => {
      const chat = {
        additional_attributes: {},
        messages: [{ content: 'Olá,\n  tudo bem?', message_type: 0 }],
        last_non_activity_message: null,
      };
      expect(getTicketSubject(chat)).toEqual({
        text: 'Olá, tudo bem?',
        isPreview: true,
      });
    });

    it('returns empty text when nothing is available', () => {
      expect(getTicketSubject({})).toEqual({ text: '', isPreview: true });
    });
  });

  describe('getTicketRequester / getTicketOrganization', () => {
    const chat = {
      meta: { sender: { id: 7, name: 'Sender' } },
      custom_attributes: { zd_nome_da_organizacao: 'Org ZD' },
    };

    it('prefers the store contact', () => {
      expect(getTicketRequester(chat, { id: 7, name: 'Store' }).name).toBe(
        'Store'
      );
      expect(getTicketRequester(chat, {}).name).toBe('Sender');
    });

    it('uses company_name before Zendesk fields', () => {
      expect(
        getTicketOrganization(chat, {
          additional_attributes: { company_name: 'ACME' },
        })
      ).toBe('ACME');
      expect(getTicketOrganization(chat, {})).toBe('Org ZD');
      expect(getTicketOrganization({}, {})).toBe('');
    });
  });

  describe('getTicketStatus', () => {
    it('uses zd_status and maps its category', () => {
      expect(
        getTicketStatus({
          status: 'open',
          custom_attributes: { zd_status: 'Desenvolvimento Concluído' },
        })
      ).toEqual({
        source: 'zendesk',
        label: 'Desenvolvimento Concluído',
        nativeStatus: 'open',
        category: 'hold',
      });
    });

    it('falls back to native category for unknown zd_status', () => {
      expect(
        getTicketStatus({
          status: 'resolved',
          custom_attributes: { zd_status: 'Outro' },
        }).category
      ).toBe('solved');
    });

    it('uses the native status when zd_status is missing', () => {
      expect(getTicketStatus({ status: 'snoozed' })).toEqual({
        source: 'native',
        nativeStatus: 'snoozed',
        category: 'hold',
      });
    });
  });

  describe('sorting', () => {
    it('maps server sort values to columns', () => {
      expect(serverSortToColumn('priority_asc')).toEqual({
        column: TICKET_COLUMNS.PRIORITY,
        direction: SORT_DIRECTION.ASC,
      });
      expect(serverSortToColumn('last_activity_at_desc')).toEqual({
        column: TICKET_COLUMNS.UPDATED,
        direction: SORT_DIRECTION.DESC,
      });
      expect(serverSortToColumn('unread')).toBeNull();
      expect(isServerSortColumn(TICKET_COLUMNS.SUBJECT)).toBe(false);
    });

    it('keeps empty values last in both directions', () => {
      expect(compareColumnValues('', 'a', SORT_DIRECTION.ASC)).toBe(1);
      expect(compareColumnValues('', 'a', SORT_DIRECTION.DESC)).toBe(1);
      expect(compareColumnValues('b', 'a', SORT_DIRECTION.DESC)).toBeLessThan(
        0
      );
    });

    it('sorts accent-insensitively and stably', () => {
      const rows = [
        { id: 1, name: 'Érica' },
        { id: 2, name: '' },
        { id: 3, name: 'ana' },
        { id: 4, name: 'Ana' },
      ];
      const sorted = sortRows(rows, 'name', SORT_DIRECTION.ASC, (r, c) => r[c]);
      expect(sorted.map(r => r.id)).toEqual([3, 4, 1, 2]);
      expect(rows.map(r => r.id)).toEqual([1, 2, 3, 4]);
    });
  });

  it('builds shift-click ranges', () => {
    expect(rangeBetween(null, 3)).toEqual([3]);
    expect(rangeBetween(5, 2)).toEqual([2, 3, 4, 5]);
  });

  it('normalizes text', () => {
    expect(normalizeText('  Retorno   Integrações ')).toBe(
      'retorno integracoes'
    );
  });
});

describe('useTicketListMode storage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('persists the mode per user', () => {
    writeStoredMode(1, 'table');
    expect(readStoredMode(1)).toBe('table');
    expect(readStoredMode(2)).toBeNull();
  });

  it('ignores invalid values and storage errors', () => {
    window.localStorage.setItem('servicedesk.ticketListMode:1', 'grid');
    expect(readStoredMode(1)).toBeNull();
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(readStoredMode(1)).toBeNull();
    expect(() => writeStoredMode(1, 'table')).not.toThrow();
  });
});
