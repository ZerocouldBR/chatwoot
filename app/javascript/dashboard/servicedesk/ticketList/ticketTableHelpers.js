import { getLastMessage } from 'dashboard/helper/conversationHelper';
import wootConstants from 'dashboard/constants/globals';
import {
  STATUS_CATEGORY,
  STATUS_CATEGORY_ORDER,
  ZD_STATUS_CATEGORY_BY_LABEL,
  NATIVE_STATUS_CATEGORY,
} from './statusTokensFallback';

const { SORT_BY_TYPE } = wootConstants;

export const SORT_DIRECTION = Object.freeze({ ASC: 'asc', DESC: 'desc' });

export const TICKET_COLUMNS = Object.freeze({
  NUMBER: 'number',
  SUBJECT: 'subject',
  REQUESTER: 'requester',
  ORGANIZATION: 'organization',
  STATUS: 'status',
  PRIORITY: 'priority',
  GROUP: 'group',
  ASSIGNEE: 'assignee',
  UPDATED: 'updated',
  CHANNEL: 'channel',
});

// Colunas ordenadas no servidor (reaproveitam o sort existente da store, que
// reinicia a paginacao). As demais ordenam apenas os tickets ja carregados.
export const SERVER_SORT_BY_COLUMN = Object.freeze({
  [TICKET_COLUMNS.NUMBER]: {
    asc: SORT_BY_TYPE.CREATED_AT_ASC,
    desc: SORT_BY_TYPE.CREATED_AT_DESC,
  },
  [TICKET_COLUMNS.UPDATED]: {
    asc: SORT_BY_TYPE.LAST_ACTIVITY_AT_ASC,
    desc: SORT_BY_TYPE.LAST_ACTIVITY_AT_DESC,
  },
  [TICKET_COLUMNS.PRIORITY]: {
    asc: SORT_BY_TYPE.PRIORITY_ASC,
    desc: SORT_BY_TYPE.PRIORITY_DESC,
  },
});

export const isServerSortColumn = column =>
  Object.prototype.hasOwnProperty.call(SERVER_SORT_BY_COLUMN, column);

/**
 * Converte o sort ativo da store (ex.: "priority_desc") em { column, direction }.
 * Retorna null quando o sort ativo nao corresponde a nenhuma coluna.
 */
export const serverSortToColumn = sortBy => {
  const entry = Object.entries(SERVER_SORT_BY_COLUMN).find(([, dirs]) =>
    Object.values(dirs).includes(sortBy)
  );
  if (!entry) return null;
  const [column, dirs] = entry;
  return {
    column,
    direction: dirs.asc === sortBy ? SORT_DIRECTION.ASC : SORT_DIRECTION.DESC,
  };
};

export const normalizeText = value =>
  String(value ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();

const lastMessageOf = chat => {
  if (!chat) return null;
  if (Array.isArray(chat.messages) && chat.messages.length) {
    return getLastMessage(chat);
  }
  return chat.last_non_activity_message || null;
};

/**
 * Assunto do ticket: additional_attributes.mail_subject ou, na falta dele,
 * a previa da ultima mensagem.
 */
export const getTicketSubject = chat => {
  const subject = chat?.additional_attributes?.mail_subject;
  if (subject && String(subject).trim()) {
    return { text: String(subject).trim(), isPreview: false };
  }
  const content = lastMessageOf(chat)?.content || '';
  return {
    text: String(content).replace(/\s+/g, ' ').trim().slice(0, 240),
    isPreview: true,
  };
};

/** Solicitante: contato da store (mais atualizado) ou meta.sender. */
export const getTicketRequester = (chat, storeContact) => {
  if (storeContact && storeContact.id) return storeContact;
  return chat?.meta?.sender || {};
};

/**
 * Organizacao: contact.additional_attributes.company_name (decisao 7: a
 * importacao grava o nome da organizacao ali) e, so na falta dele, os campos
 * importados na conversa (zd_nome_da_organizacao / zd_nome_da_empresa).
 */
export const getTicketOrganization = (chat, contact) => {
  const candidates = [
    contact?.additional_attributes?.company_name,
    chat?.meta?.sender?.additional_attributes?.company_name,
    chat?.custom_attributes?.zd_nome_da_organizacao,
    chat?.custom_attributes?.zd_nome_da_empresa,
  ];
  const found = candidates.find(value => value && String(value).trim());
  return found ? String(found).trim() : '';
};

export const getZendeskStatusCategory = label =>
  ZD_STATUS_CATEGORY_BY_LABEL[normalizeText(label)] || null;

/**
 * Status exibido: rotulo zd_status (status personalizado) quando existir, com a
 * cor da sua categoria; senao, a categoria do status nativo (canonico).
 * Retorna { source: 'custom'|'native', label?, nativeStatus, category }.
 */
export const getTicketStatus = chat => {
  const nativeStatus = chat?.status || 'open';
  const nativeCategory =
    NATIVE_STATUS_CATEGORY[nativeStatus] || STATUS_CATEGORY.OPEN;
  const zdStatus = chat?.custom_attributes?.zd_status;
  if (zdStatus && String(zdStatus).trim()) {
    return {
      source: 'custom',
      label: String(zdStatus).trim(),
      nativeStatus,
      category: getZendeskStatusCategory(zdStatus) || nativeCategory,
    };
  }
  return { source: 'native', nativeStatus, category: nativeCategory };
};

export const statusCategoryRank = category => {
  const index = STATUS_CATEGORY_ORDER.indexOf(category);
  return index === -1 ? STATUS_CATEGORY_ORDER.length : index;
};

const PRIORITY_RANK = { urgent: 4, high: 3, medium: 2, low: 1 };
export const priorityRank = priority => PRIORITY_RANK[priority] || 0;

const collator =
  typeof Intl !== 'undefined'
    ? new Intl.Collator('pt-BR', { sensitivity: 'base', numeric: true })
    : null;

const compareText = (a, b) =>
  collator ? collator.compare(a, b) : a.localeCompare(b);

const isEmptyValue = value =>
  value === '' || value === null || value === undefined;

/**
 * Compara dois valores de coluna. Vazios sempre ficam no fim, independente da
 * direcao (como nas views do Zendesk).
 */
export const compareColumnValues = (a, b, direction = SORT_DIRECTION.ASC) => {
  const emptyA = isEmptyValue(a);
  const emptyB = isEmptyValue(b);
  if (emptyA && emptyB) return 0;
  if (emptyA) return 1;
  if (emptyB) return -1;
  const result =
    typeof a === 'number' && typeof b === 'number'
      ? a - b
      : compareText(String(a), String(b));
  return direction === SORT_DIRECTION.DESC ? -result : result;
};

/**
 * Ordena (sem mutar) as linhas ja carregadas. `getValue(row, column)` devolve
 * o valor comparavel. Ordenacao estavel: empate preserva a ordem do servidor.
 */
export const sortRows = (rows, column, direction, getValue) => {
  if (!column) return [...rows];
  return rows
    .map((row, index) => ({ row, index, value: getValue(row, column) }))
    .sort(
      (x, y) =>
        compareColumnValues(x.value, y.value, direction) || x.index - y.index
    )
    .map(({ row }) => row);
};

/** Indices (inclusivos) entre a ultima linha clicada e a atual (shift+clique). */
export const rangeBetween = (from, to) => {
  if (from === null || from === undefined || from < 0) return [to];
  const start = Math.min(from, to);
  const end = Math.max(from, to);
  return Array.from({ length: end - start + 1 }, (_, i) => start + i);
};
