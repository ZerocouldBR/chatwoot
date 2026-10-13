// Regras do painel de propriedades do ticket (formulários estilo Zendesk).
// Fonte provisória: JSONs estáticos gerados a partir do export do Zendesk
// (script/servicedesk_generate_ticket_forms.py). O módulo M1 leva para o banco.
import ticketForms from './ticketForms.json';
import ticketFormsMeta from './ticketFormsMeta.json';

export const FORM_ATTRIBUTE_KEY = 'zd_formulario';
export const STATUS_ATTRIBUTE_KEY = 'zd_status';
export const TYPE_ATTRIBUTE_KEY = 'zd_tipo';
export const CC_ATTRIBUTE_KEY = 'zd_cc';
export const FOLLOWERS_ATTRIBUTE_KEY = 'zd_seguidores';

// Atributos exibidos no cabeçalho do painel (não se repetem nos grupos).
export const HEADER_ATTRIBUTE_KEYS = [
  FORM_ATTRIBUTE_KEY,
  STATUS_ATTRIBUTE_KEY,
  TYPE_ATTRIBUTE_KEY,
  CC_ATTRIBUTE_KEY,
  FOLLOWERS_ATTRIBUTE_KEY,
];

const FIELD_PREFIX = 'zendesk_field:';
const META_PREFIX = 'zendesk:';

export const getZendeskFieldId = attribute => {
  const description = (attribute?.attribute_description || '').trim();
  if (!description.startsWith(FIELD_PREFIX)) return null;
  const id = description.slice(FIELD_PREFIX.length).trim();
  return id || null;
};

export const isZendeskMetaAttribute = attribute =>
  (attribute?.attribute_description || '').trim().startsWith(META_PREFIX);

export const hasValue = value =>
  value !== undefined && value !== null && value !== '';

export const getFormNames = (forms = ticketForms) => Object.keys(forms);

export const getDefaultFormName = (meta = ticketFormsMeta) =>
  meta.default_form || null;

/**
 * Formulário efetivo do ticket: o valor gravado em zd_formulario, se existir
 * na configuração; senão o formulário padrão (como no Zendesk).
 */
export const resolveFormName = (
  value,
  forms = ticketForms,
  meta = ticketFormsMeta
) => {
  if (hasValue(value) && forms[value]) return value;
  return getDefaultFormName(meta);
};

// Sufixo atual "(inativo)"; "(inativo no Zendesk)" é o nome antigo.
const isFieldInactive = attribute =>
  /\(inativo( no zendesk)?\)/i.test(attribute?.attribute_display_name || '');

// Rede de segurança: a UI não mostra "Zendesk" mesmo que alguma definição de
// atributo ainda esteja com o nome antigo (a renomeação oficial é no banco).
const LABEL_RENAMES = [
  [/^status \(zendesk\)$/i, 'Status do ticket'],
  [/^n[ºo°]? ?ticket zendesk$/i, 'Nº do ticket (histórico)'],
  [/\s*\(inativo no zendesk\)/i, ' (inativo)'],
  [/\s*\(exclu[ií]do no zendesk\)/i, ' (excluído)'],
  [/\s*\(zendesk\)/i, ' (histórico)'],
  [/\s*zendesk\b/i, ''],
];
export const displayNameFor = attribute => {
  const name = String(attribute?.attribute_display_name || '');
  const rule = LABEL_RENAMES.find(([regex]) => regex.test(name));
  return rule ? name.replace(rule[0], rule[1]).trim() : name;
};

/**
 * Monta os grupos de campos personalizados do formulário.
 * @param {Object} params
 * @param {string} params.formName formulário efetivo
 * @param {Array} params.attributes definições de atributo de conversa
 * @param {Object} params.values custom_attributes da conversa
 * @param {boolean} [params.showAllConditional] mostra campos condicionais ocultos
 * @returns {{ formFields: Array, otherFields: Array, metaFields: Array, hiddenCount: number }}
 */
export const buildFormFieldGroups = ({
  formName,
  attributes = [],
  values = {},
  showAllConditional = false,
  forms = ticketForms,
  meta = ticketFormsMeta,
}) => {
  const byFieldId = new Map();
  attributes.forEach(attribute => {
    const fieldId = getZendeskFieldId(attribute);
    if (fieldId) byFieldId.set(fieldId, attribute);
  });

  const conditions = (meta.conditions || {})[formName] || [];
  const requiredIds = new Set((meta.required_field_ids || []).map(String));
  // filho -> lista de { parentId, value, isRequired }
  const childRules = new Map();
  conditions.forEach(condition => {
    (condition.child_fields || []).forEach(child => {
      const key = String(child.id);
      if (!childRules.has(key)) childRules.set(key, []);
      childRules.get(key).push({
        parentId: String(condition.parent_field_id),
        value: condition.value,
        isRequired: !!child.is_required,
      });
    });
  });

  const valueOfField = fieldId => {
    const attribute = byFieldId.get(String(fieldId));
    return attribute ? values[attribute.attribute_key] : undefined;
  };

  const used = new Set(HEADER_ATTRIBUTE_KEYS);
  const formFields = [];
  let hiddenCount = 0;

  (forms[formName] || []).forEach(rawId => {
    const fieldId = String(rawId);
    const attribute = byFieldId.get(fieldId);
    // Campos de sistema (status, grupo, responsável, assunto, descrição,
    // prioridade) não têm atributo: ficam no cabeçalho do painel.
    if (!attribute || used.has(attribute.attribute_key)) return;

    const value = values[attribute.attribute_key];
    const rules = childRules.get(fieldId) || [];
    const matchedRules = rules.filter(
      rule => valueOfField(rule.parentId) === rule.value
    );
    const conditionMet = !rules.length || matchedRules.length > 0;
    const inactive = isFieldInactive(attribute);
    const visible =
      hasValue(value) || (!inactive && (conditionMet || showAllConditional));

    used.add(attribute.attribute_key);
    if (!visible) {
      hiddenCount += 1;
      return;
    }
    formFields.push({
      ...attribute,
      attribute_display_name: displayNameFor(attribute),
      key: attribute.attribute_key,
      value: hasValue(value) ? value : '',
      zendeskFieldId: fieldId,
      isConditional: rules.length > 0,
      isRequired:
        requiredIds.has(fieldId) || matchedRules.some(rule => rule.isRequired),
    });
  });

  const otherFields = [];
  const metaFields = [];
  attributes.forEach(attribute => {
    if (used.has(attribute.attribute_key)) return;
    const value = values[attribute.attribute_key];
    if (!hasValue(value)) return;
    const field = {
      ...attribute,
      attribute_display_name: displayNameFor(attribute),
      key: attribute.attribute_key,
      value,
      zendeskFieldId: getZendeskFieldId(attribute),
      isConditional: false,
      isRequired: false,
    };
    if (isZendeskMetaAttribute(attribute)) metaFields.push(field);
    else otherFields.push(field);
  });

  return { formFields, otherFields, metaFields, hiddenCount };
};

export const getStatusMeta = (label, meta = ticketFormsMeta) =>
  (meta.statuses || {})[label] || null;

/** Status nativo correspondente a um status personalizado (zd_status). */
export const nativeStatusFor = (label, meta = ticketFormsMeta) =>
  getStatusMeta(label, meta)?.native || null;

/** Status personalizado padrão de um status nativo (open/snoozed/resolved). */
export const defaultCustomStatusFor = (nativeStatus, meta = ticketFormsMeta) =>
  (meta.native_status_default || {})[nativeStatus] || null;

export { ticketForms, ticketFormsMeta };
