import {
  buildFormFieldGroups,
  defaultCustomStatusFor,
  getZendeskFieldId,
  nativeStatusFor,
  displayNameFor,
  resolveFormName,
  ticketForms,
  ticketFormsMeta,
} from '../ticketFormHelper';

const forms = {
  Principal: [1, 10, 11, 12, 13],
  Outro: [20],
};

const meta = {
  default_form: 'Principal',
  conditions: {
    Principal: [
      {
        parent_field_id: 10,
        value: 'Suporte',
        child_fields: [{ id: 11, is_required: true }],
      },
    ],
  },
  required_field_ids: [10],
  statuses: {
    Novo: { category: 'new', native: 'open' },
    Pendente: { category: 'pending', native: 'snoozed' },
    Desenvolvimento: { category: 'hold', native: 'snoozed' },
    Resolvido: { category: 'solved', native: 'resolved' },
  },
  native_status_default: {
    open: 'Aberto',
    snoozed: 'Pendente',
    resolved: 'Resolvido',
  },
};

const attr = (key, fieldId, name = key) => ({
  attribute_key: key,
  attribute_display_name: name,
  attribute_description: fieldId ? `zendesk_field:${fieldId}` : 'zendesk:x',
});

const attributes = [
  attr('area', 10),
  attr('tabulacao', 11),
  attr('texto', 12),
  attr('inativo', 13, 'Inativo (inativo no Zendesk)'),
  attr('outro', 20),
  attr('zd_tipo', 1),
  attr('zd_ticket_id', null),
];

describe('ticketFormHelper', () => {
  it('extrai o id do campo do Zendesk da descrição', () => {
    expect(getZendeskFieldId(attr('a', 123))).toBe('123');
    expect(getZendeskFieldId({ attribute_description: 'zendesk:x' })).toBe(
      null
    );
  });

  it('usa o formulário padrão quando o ticket não tem formulário válido', () => {
    expect(resolveFormName('', forms, meta)).toBe('Principal');
    expect(resolveFormName('Desconhecido', forms, meta)).toBe('Principal');
    expect(resolveFormName('Outro', forms, meta)).toBe('Outro');
  });

  it('oculta campo condicional até a condição ser atendida', () => {
    const groups = buildFormFieldGroups({
      formName: 'Principal',
      attributes,
      values: {},
      forms,
      meta,
    });
    expect(groups.formFields.map(f => f.key)).toEqual(['area', 'texto']);
    expect(groups.hiddenCount).toBe(2);
    expect(groups.formFields[0].isRequired).toBe(true);
  });

  it('mostra o filho quando o pai tem o valor da condição', () => {
    const groups = buildFormFieldGroups({
      formName: 'Principal',
      attributes,
      values: { area: 'Suporte' },
      forms,
      meta,
    });
    const child = groups.formFields.find(f => f.key === 'tabulacao');
    expect(child).toBeTruthy();
    expect(child.isRequired).toBe(true);
  });

  it('nunca esconde campos com valor e separa campos fora do formulário', () => {
    const groups = buildFormFieldGroups({
      formName: 'Principal',
      attributes,
      values: { inativo: 'x', outro: 'y', zd_ticket_id: 42, zd_tipo: 'Tarefa' },
      forms,
      meta,
    });
    expect(groups.formFields.map(f => f.key)).toContain('inativo');
    expect(groups.otherFields.map(f => f.key)).toEqual(['outro']);
    expect(groups.metaFields.map(f => f.key)).toEqual(['zd_ticket_id']);
    // zd_tipo fica no cabeçalho
    expect(groups.formFields.map(f => f.key)).not.toContain('zd_tipo');
  });

  it('mapeia status personalizado <-> status nativo', () => {
    expect(nativeStatusFor('Novo', meta)).toBe('open');
    expect(nativeStatusFor('Resolvido', meta)).toBe('resolved');
    expect(nativeStatusFor('?', meta)).toBe(null);
    expect(nativeStatusFor('Desenvolvimento', meta)).toBe('snoozed');
    expect(defaultCustomStatusFor('snoozed', meta)).toBe('Pendente');
    expect(defaultCustomStatusFor('pending', meta)).toBe(null);
  });

  it('o JSON versionado segue o status canônico', () => {
    const canon = {
      new: 'open',
      open: 'open',
      pending: 'snoozed',
      hold: 'snoozed',
      solved: 'resolved',
    };
    Object.values(ticketFormsMeta.statuses).forEach(status => {
      expect(status.native).toBe(canon[status.category]);
    });
    expect(ticketFormsMeta.native_status_default).toEqual({
      open: 'Aberto',
      snoozed: 'Pendente',
      resolved: 'Resolvido',
    });
  });

  it('não mostra "Zendesk" nos rótulos', () => {
    expect(displayNameFor({ attribute_display_name: 'Status (Zendesk)' })).toBe(
      'Status do ticket'
    );
    expect(
      displayNameFor({ attribute_display_name: 'Nº ticket Zendesk' })
    ).toBe('Nº do ticket (histórico)');
    expect(
      displayNameFor({
        attribute_display_name: 'Checkout (inativo no Zendesk)',
      })
    ).toBe('Checkout (inativo)');
    expect(displayNameFor({ attribute_display_name: 'Canal (Zendesk)' })).toBe(
      'Canal (histórico)'
    );
    expect(displayNameFor({ attribute_display_name: 'Tipo' })).toBe('Tipo');
  });

  it('o JSON versionado tem os formulários do Zendesk', () => {
    expect(Object.keys(ticketForms)).toContain('Atendimento');
    expect(ticketFormsMeta.default_form).toBe('Atendimento');
    Object.values(ticketForms).forEach(ids => {
      expect(Array.isArray(ids)).toBe(true);
    });
  });
});
