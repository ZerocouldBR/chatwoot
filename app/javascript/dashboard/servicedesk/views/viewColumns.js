/**
 * Colunas e ordenação de cada view, como no Zendesk (integ/final-v3, sobre a
 * lista do Victor).
 *
 * Cada view importada traz (API servicedesk/views, import_rules_views.rb):
 *   columns  [{ id, titulo }]  -> execution.columns do views.json
 *   sort     { campo, ordem }  -> execution.sort_by / sort_order
 *
 * `id` é um campo de sistema do Zendesk (subject, requester,
 * sla_next_breach_at...) ou o id numérico de um campo personalizado, que vira
 * o atributo da conversa com a descrição `zendesk_field:<id>`.
 */

export const SORT_DIRECTION = Object.freeze({ ASC: 'asc', DESC: 'desc' });

export const VIEW_COLUMNS = Object.freeze({
  NUMBER: 'number',
  SLA: 'sla',
  SUBJECT: 'subject',
  REQUESTER: 'requester',
  ORGANIZATION: 'organization',
  STATUS: 'status',
  PRIORITY: 'priority',
  GROUP: 'group',
  ASSIGNEE: 'assignee',
  UPDATED: 'updated',
  CHANNEL: 'channel',
  CREATED: 'created',
  SOLVED: 'solved',
  REQUESTER_UPDATED: 'requester_updated',
  ASSIGNEE_UPDATED: 'assignee_updated',
  SATISFACTION: 'satisfaction',
  TYPE: 'type',
});

const C = VIEW_COLUMNS;

export const FIELD_COLUMN_PREFIX = 'field:';

// Campo de sistema do Zendesk -> coluna
export const ZENDESK_COLUMN_TO_KEY = Object.freeze({
  custom_status_id: C.STATUS,
  status: C.STATUS,
  sla_next_breach_at: C.SLA,
  ticket_id: C.NUMBER,
  nice_id: C.NUMBER,
  id: C.NUMBER,
  subject: C.SUBJECT,
  description: C.SUBJECT,
  requester: C.REQUESTER,
  organization: C.ORGANIZATION,
  group: C.GROUP,
  assignee: C.ASSIGNEE,
  via: C.CHANNEL,
  created: C.CREATED,
  updated: C.UPDATED,
  updated_by_type: C.UPDATED,
  solved: C.SOLVED,
  requester_updated_at: C.REQUESTER_UPDATED,
  assignee_updated_at: C.ASSIGNEE_UPDATED,
  priority: C.PRIORITY,
  satisfaction_score: C.SATISFACTION,
  type: C.TYPE,
});

// Ordenação do servidor (Conversations::SortService) de cada coluna
export const SERVER_SORT_BY_COLUMN = Object.freeze({
  [C.NUMBER]: { asc: 'sd_id_asc', desc: 'sd_id_desc' },
  [C.SLA]: { asc: 'sd_sla_asc', desc: 'sd_sla_desc' },
  [C.SUBJECT]: { asc: 'sd_subject_asc', desc: 'sd_subject_desc' },
  [C.REQUESTER]: { asc: 'sd_requester_asc', desc: 'sd_requester_desc' },
  [C.STATUS]: { asc: 'sd_status_asc', desc: 'sd_status_desc' },
  [C.PRIORITY]: { asc: 'priority_asc', desc: 'priority_desc' },
  [C.GROUP]: { asc: 'sd_group_asc', desc: 'sd_group_desc' },
  [C.ASSIGNEE]: { asc: 'sd_assignee_asc', desc: 'sd_assignee_desc' },
  [C.UPDATED]: { asc: 'last_activity_at_asc', desc: 'last_activity_at_desc' },
  [C.CHANNEL]: { asc: 'sd_channel_asc', desc: 'sd_channel_desc' },
  [C.CREATED]: { asc: 'created_at_asc', desc: 'created_at_desc' },
  [C.SOLVED]: { asc: 'sd_solved_asc', desc: 'sd_solved_desc' },
  [C.REQUESTER_UPDATED]: {
    asc: 'sd_requester_updated_asc',
    desc: 'sd_requester_updated_desc',
  },
  [C.ASSIGNEE_UPDATED]: {
    asc: 'sd_assignee_updated_asc',
    desc: 'sd_assignee_updated_desc',
  },
});

// Chave i18n (SD_VIEW_TABLE.COLUMNS.<i18n>) de cada coluna de sistema
const COLUMN_I18N = Object.freeze(
  Object.fromEntries(Object.values(C).map(key => [key, key.toUpperCase()]))
);

export const isFieldColumn = key =>
  String(key || '').startsWith(FIELD_COLUMN_PREFIX);

export const systemColumn = (key, title = '') => ({
  key,
  i18n: COLUMN_I18N[key],
  title,
  attributeKey: null,
});

const getZendeskFieldId = attribute => {
  const description = (attribute?.attribute_description || '').trim();
  if (!description.startsWith('zendesk_field:')) return null;
  return description.slice('zendesk_field:'.length).trim() || null;
};

const indexAttributesByFieldId = (attributes = []) => {
  const byFieldId = new Map();
  attributes.forEach(attribute => {
    const fieldId = getZendeskFieldId(attribute);
    if (fieldId) byFieldId.set(String(fieldId), attribute);
  });
  return byFieldId;
};

/**
 * Colunas de uma view, na ordem do Zendesk. Colunas repetidas (ex.: "ID" e
 * "nice_id") aparecem uma vez. Sem colunas na view devolve [] (a lista do
 * Victor continua como está).
 */
export const buildViewColumns = (viewColumns, attributes = []) => {
  if (!Array.isArray(viewColumns) || !viewColumns.length) return [];
  const byFieldId = indexAttributesByFieldId(attributes);
  const seen = new Set();
  const columns = [];

  viewColumns.forEach(column => {
    const id = String(column?.id ?? '').trim();
    if (!id) return;
    const title = column.titulo || column.title || '';
    let built;
    if (/^\d+$/.test(id)) {
      const attribute = byFieldId.get(id);
      built = {
        key: `${FIELD_COLUMN_PREFIX}${attribute?.attribute_key || id}`,
        i18n: null,
        title: title || attribute?.attribute_display_name || id,
        attributeKey: attribute?.attribute_key || null,
        attributeType: attribute?.attribute_display_type || 'text',
      };
    } else if (ZENDESK_COLUMN_TO_KEY[id]) {
      built = systemColumn(ZENDESK_COLUMN_TO_KEY[id], title);
    } else {
      // Campo de sistema sem equivalente: mostra o título e fica vazio
      built = { key: `zd:${id}`, i18n: null, title: title || id };
    }
    if (seen.has(built.key)) return;
    seen.add(built.key);
    columns.push(built);
  });

  return columns;
};

/**
 * Ordenação da view: { column, direction, sortBy }. `sortBy` é a ordenação do
 * servidor quando a coluna tem uma; senão null (a tabela ordena as linhas
 * carregadas). null quando a view não define ordenação.
 */
export const viewSort = (view, attributes = []) => {
  const field = String(view?.sort?.campo ?? '').trim();
  if (!field) return null;
  const direction =
    view.sort.ordem === SORT_DIRECTION.DESC
      ? SORT_DIRECTION.DESC
      : SORT_DIRECTION.ASC;

  let column = ZENDESK_COLUMN_TO_KEY[field] || null;
  if (!column && /^\d+$/.test(field)) {
    const attribute = indexAttributesByFieldId(attributes).get(field);
    column = `${FIELD_COLUMN_PREFIX}${attribute?.attribute_key || field}`;
  }
  if (!column) return null;
  const sortBy = SERVER_SORT_BY_COLUMN[column]?.[direction] || null;
  return { column, direction, sortBy };
};

/** Ordenação do servidor de uma coluna numa direção (null = só no navegador). */
export const serverSortFor = (column, direction) =>
  SERVER_SORT_BY_COLUMN[column]?.[direction] || null;

/** Valor exibido de um campo personalizado (lista, caixa de seleção, data). */
export const formatFieldValue = (value, type, t) => {
  if (value === undefined || value === null || value === '') return '';
  if (type === 'checkbox') {
    return value === true || value === 'true'
      ? t('SD_VIEW_TABLE.VALUES.YES')
      : t('SD_VIEW_TABLE.VALUES.NO');
  }
  if (type === 'date') {
    const date = new Date(value);
    return Number.isNaN(date.getTime())
      ? String(value)
      : date.toLocaleDateString('pt-BR');
  }
  if (Array.isArray(value)) return value.join(', ');
  return String(value);
};

// Ordem das categorias de status do Zendesk no enum do Victor
export const STATUS_RANK = Object.freeze({
  new_ticket: 0,
  open: 1,
  pending: 1,
  waiting_on_customer: 2,
  on_hold: 3,
  resolved: 4,
  closed: 5,
});

/** Valor de ordenação no navegador (colunas sem ordenação no servidor). */
export const cellSortValue = (chat, column) => {
  if (column.attributeKey) {
    const value = chat?.custom_attributes?.[column.attributeKey];
    return value === undefined || value === null ? '' : String(value);
  }
  switch (column.key) {
    case C.ORGANIZATION:
      return chat?.company_name || '';
    case C.TYPE:
      return chat?.ticket_type || chat?.custom_attributes?.zd_tipo || '';
    case C.SATISFACTION:
      return chat?.satisfaction || '';
    default:
      return '';
  }
};
