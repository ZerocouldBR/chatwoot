import {
  describeCustomAttributeAction,
  getAttributeValueOptions,
  getSettableAttributes,
  getTicketStatusOptions,
  valueInputTypeFor,
} from '../actionOptions';

const t = key => key;
const zdStatus = {
  attribute_key: 'zd_status',
  attribute_display_name: 'Status do ticket',
  attribute_display_type: 'list',
  attribute_values: ['Novo', 'Desenvolvimento'],
};
const tabulacao = {
  attribute_key: 'zd_tabulacao',
  attribute_display_name: 'Tabulação',
  attribute_display_type: 'list',
  attribute_values: ['Chargeback', 'Estorno'],
};
const vip = {
  attribute_key: 'zd_vip',
  attribute_display_name: 'VIP',
  attribute_display_type: 'checkbox',
};

describe('ServiceDesk actionOptions', () => {
  describe('getTicketStatusOptions', () => {
    it('uses the zd_status list of the account', () => {
      expect(getTicketStatusOptions([tabulacao, zdStatus])).toEqual([
        { id: 'Novo', name: 'Novo' },
        { id: 'Desenvolvimento', name: 'Desenvolvimento' },
      ]);
    });

    it('falls back to the active statuses of ticketFormsMeta.json', () => {
      const labels = getTicketStatusOptions([]).map(option => option.id);

      expect(labels).toContain('Desenvolvimento Concluído');
      expect(labels).not.toContain('Escalonado');
      expect(labels).toHaveLength(11);
    });
  });

  it('does not offer zd_status to set_custom_attribute', () => {
    expect(getSettableAttributes([zdStatus, tabulacao])).toEqual([tabulacao]);
  });

  it('offers fixed values for list and checkbox attributes', () => {
    expect(getAttributeValueOptions(tabulacao, t)).toEqual([
      { id: 'Chargeback', name: 'Chargeback' },
      { id: 'Estorno', name: 'Estorno' },
    ]);
    expect(getAttributeValueOptions(vip, t).map(o => o.id)).toEqual([
      'true',
      'false',
    ]);
    expect(
      getAttributeValueOptions({ attribute_display_type: 'text' }, t)
    ).toBeNull();
  });

  it('maps the attribute type to the input type', () => {
    expect(valueInputTypeFor({ attribute_display_type: 'number' })).toBe(
      'number'
    );
    expect(valueInputTypeFor({ attribute_display_type: 'date' })).toBe('date');
    expect(valueInputTypeFor({ attribute_display_type: 'text' })).toBe('text');
  });

  it('describes set_custom_attribute for the macro preview', () => {
    const attributes = [tabulacao, vip];

    expect(
      describeCustomAttributeAction(
        ['zd_tabulacao', 'Chargeback'],
        attributes,
        t
      )
    ).toBe('Tabulação: Chargeback');
    expect(
      describeCustomAttributeAction(['zd_vip', 'true'], attributes, t)
    ).toBe('VIP: FILTER.ATTRIBUTE_LABELS.TRUE');
    expect(
      describeCustomAttributeAction(['zd_tabulacao', ''], attributes, t)
    ).toBe('Tabulação: MACROS.EXECUTE.CLEAR_VALUE');
    expect(describeCustomAttributeAction(['outro', 'x'], attributes, t)).toBe(
      'outro: x'
    );
  });
});
