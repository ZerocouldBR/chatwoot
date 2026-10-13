/**
 * ServiceDesk M5/M4: opções do construtor de macros e automações para as ações
 * set_ticket_status, set_custom_attribute e change_subject.
 * O backend valida os mesmos parâmetros (Servicedesk::ConversationActionParams).
 */
import ticketFormsMeta from './ticketFormsMeta.json';

export const TICKET_STATUS_ATTRIBUTE_KEY = 'zd_status';

const toOption = value => ({ id: value, name: value });

/**
 * Rótulos de status para set_ticket_status: a lista do atributo zd_status da conta
 * (é o que o backend aceita) e, sem ela, os status ativos de ticketFormsMeta.json.
 */
export const getTicketStatusOptions = (conversationAttributes = []) => {
  const definition = conversationAttributes.find(
    attribute => attribute.attribute_key === TICKET_STATUS_ATTRIBUTE_KEY
  );
  if (
    definition?.attribute_display_type === 'list' &&
    definition.attribute_values?.length
  ) {
    return definition.attribute_values.map(toOption);
  }
  return Object.entries(ticketFormsMeta.statuses || {})
    .filter(([, status]) => status.active)
    .map(([label]) => toOption(label));
};

/** Atributos de conversa que set_custom_attribute pode gravar (zd_status tem ação própria). */
export const getSettableAttributes = (conversationAttributes = []) =>
  conversationAttributes.filter(
    attribute => attribute.attribute_key !== TICKET_STATUS_ATTRIBUTE_KEY
  );

/** Opções fixas do valor (lista e checkbox) ou null quando o valor é digitado. */
export const getAttributeValueOptions = (attribute, t) => {
  if (!attribute) return null;
  if (attribute.attribute_display_type === 'list') {
    return (attribute.attribute_values || []).map(toOption);
  }
  if (attribute.attribute_display_type === 'checkbox') {
    return [
      { id: 'true', name: t('FILTER.ATTRIBUTE_LABELS.TRUE') },
      { id: 'false', name: t('FILTER.ATTRIBUTE_LABELS.FALSE') },
    ];
  }
  return null;
};

const VALUE_INPUT_TYPES = {
  number: 'number',
  currency: 'number',
  percent: 'number',
  date: 'date',
  link: 'url',
};

export const valueInputTypeFor = attribute =>
  VALUE_INPUT_TYPES[attribute?.attribute_display_type] || 'text';

/** Texto da prévia da macro para set_custom_attribute ("Tabulação: Chargeback"). */
export const describeCustomAttributeAction = (
  [key, value] = [],
  conversationAttributes = [],
  t = text => text
) => {
  if (!key) return '';
  const attribute = conversationAttributes.find(
    item => item.attribute_key === key
  );
  const name = attribute?.attribute_display_name || key;
  let shown = value;
  if (value === '' || value === null || value === undefined) {
    shown = t('MACROS.EXECUTE.CLEAR_VALUE');
  } else if (attribute?.attribute_display_type === 'checkbox') {
    shown =
      String(value) === 'true'
        ? t('FILTER.ATTRIBUTE_LABELS.TRUE')
        : t('FILTER.ATTRIBUTE_LABELS.FALSE');
  }
  return `${name}: ${shown}`;
};
