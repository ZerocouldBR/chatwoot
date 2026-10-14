import {
  buildViewColumns,
  viewSort,
  serverSortFor,
  formatFieldValue,
  cellSortValue,
  VIEW_COLUMNS,
} from '../viewColumns';

const attributes = [
  {
    attribute_key: 'zd_tabulacao',
    attribute_display_name: 'Tabulação',
    attribute_display_type: 'list',
    attribute_description: 'zendesk_field:21537600796443',
  },
];

describe('viewColumns', () => {
  it('maps the Zendesk columns of a view, without duplicates', () => {
    const columns = buildViewColumns(
      [
        { id: 'status', titulo: 'Status' },
        { id: 'nice_id', titulo: 'ID' },
        { id: 'ticket_id' },
        { id: 'subject', titulo: 'Assunto' },
        { id: '21537600796443', titulo: 'Tabulação' },
        { id: 'sla_next_breach_at', titulo: 'Próxima violação' },
        { id: 'campo_sem_par', titulo: 'Outro' },
      ],
      attributes
    );
    expect(columns.map(c => c.key)).toEqual([
      VIEW_COLUMNS.STATUS,
      VIEW_COLUMNS.NUMBER,
      VIEW_COLUMNS.SUBJECT,
      'field:zd_tabulacao',
      VIEW_COLUMNS.SLA,
      'zd:campo_sem_par',
    ]);
    expect(columns[3]).toMatchObject({
      attributeKey: 'zd_tabulacao',
      title: 'Tabulação',
    });
  });

  it('returns no columns when the view has none (the subject list stays)', () => {
    expect(buildViewColumns([])).toEqual([]);
    expect(buildViewColumns(undefined)).toEqual([]);
  });

  it('turns the view sort into the server sort', () => {
    expect(
      viewSort({ sort: { campo: 'sla_next_breach_at', ordem: 'asc' } })
    ).toEqual({ column: 'sla', direction: 'asc', sortBy: 'sd_sla_asc' });
    expect(viewSort({ sort: { campo: 'updated', ordem: 'desc' } })).toEqual({
      column: 'updated',
      direction: 'desc',
      sortBy: 'last_activity_at_desc',
    });
    expect(
      viewSort({ sort: { campo: '21537600796443', ordem: 'asc' } }, attributes)
    ).toEqual({ column: 'field:zd_tabulacao', direction: 'asc', sortBy: null });
    expect(viewSort({ sort: {} })).toBeNull();
    expect(serverSortFor('group', 'desc')).toBe('sd_group_desc');
    expect(serverSortFor('organization', 'asc')).toBeNull();
  });

  it('formats custom field values and the client-side sort value', () => {
    const t = key => key;
    expect(formatFieldValue(true, 'checkbox', t)).toBe(
      'SD_VIEW_TABLE.VALUES.YES'
    );
    expect(formatFieldValue(['a', 'b'], 'list', t)).toBe('a, b');
    expect(formatFieldValue('', 'text', t)).toBe('');
    expect(
      cellSortValue(
        { custom_attributes: { zd_tabulacao: 'X' } },
        { attributeKey: 'zd_tabulacao' }
      )
    ).toBe('X');
    expect(
      cellSortValue({ company_name: 'B2B' }, { key: 'organization' })
    ).toBe('B2B');
    expect(cellSortValue({ ticket_type: 'problem' }, { key: 'type' })).toBe(
      'problem'
    );
  });
});
