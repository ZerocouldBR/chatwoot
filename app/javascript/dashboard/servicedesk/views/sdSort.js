/**
 * ServiceDesk: ordenações das views do Zendesk na store de conversas.
 *
 * O servidor ordena (Conversations::SortService, `sd_*`), mas a store
 * reordena a lista no navegador com `sortComparator`. Sem um comparador
 * próprio, uma chave desconhecida voltaria para "última atividade" e
 * desfaria a ordem da view. Aqui cada chave `sd_*` compara pelos mesmos dados
 * do payload; vazio fica sempre no fim (como no Zendesk) e o desempate é a
 * última atividade. Quando o dado não vem no payload (nome do canal), o
 * comparador devolve 0 e a ordem do servidor é mantida (sort estável).
 */
import { STATUS_RANK } from './viewColumns';

const collator =
  typeof Intl !== 'undefined'
    ? new Intl.Collator('pt-BR', { sensitivity: 'base', numeric: true })
    : null;

const isEmpty = value => value === '' || value === null || value === undefined;

const byLastActivity = (a, b) =>
  (b.last_activity_at || 0) - (a.last_activity_at || 0);

export const compareValues = (valueA, valueB, direction) => {
  const emptyA = isEmpty(valueA);
  const emptyB = isEmpty(valueB);
  if (emptyA && emptyB) return 0;
  if (emptyA) return 1;
  if (emptyB) return -1;
  let result;
  if (typeof valueA === 'number' && typeof valueB === 'number') {
    result = valueA - valueB;
  } else if (collator) {
    result = collator.compare(String(valueA), String(valueB));
  } else {
    result = String(valueA).localeCompare(String(valueB));
  }
  return direction === 'desc' ? -result : result;
};

const comparatorFor = getValue => (a, b, direction) =>
  compareValues(getValue(a), getValue(b), direction) || byLastActivity(a, b);

export const SD_SORT_VALUE = Object.freeze({
  sdSla: chat => Number(chat?.next_sla_breach_at) || null,
  sdId: chat => Number(chat?.id) || null,
  sdSubject: chat => chat?.subject || null,
  sdGroup: chat => chat?.meta?.team?.name || null,
  sdRequester: chat =>
    chat?.meta?.sender?.name || chat?.meta?.sender?.email || null,
  sdAssignee: chat => chat?.meta?.assignee?.name || null,
  sdStatus: chat => STATUS_RANK[chat?.status] ?? 1,
  sdSolved: chat =>
    chat?.sd_clock?.solved_at ||
    (['resolved', 'closed'].includes(chat?.status)
      ? chat?.last_activity_at
      : null) ||
    null,
  sdRequesterUpdated: chat => chat?.sd_clock?.requester_updated_at || null,
  sdAssigneeUpdated: chat => chat?.sd_clock?.assignee_updated_at || null,
});

const pair = (key, method) => ({
  [`${key}_asc`]: [method, 'asc'],
  [`${key}_desc`]: [method, 'desc'],
});

export const SD_SORT_OPTIONS = Object.freeze({
  ...pair('sd_sla', 'sortOnSdSla'),
  ...pair('sd_id', 'sortOnSdId'),
  ...pair('sd_subject', 'sortOnSdSubject'),
  ...pair('sd_group', 'sortOnSdGroup'),
  ...pair('sd_requester', 'sortOnSdRequester'),
  ...pair('sd_assignee', 'sortOnSdAssignee'),
  ...pair('sd_channel', 'sortOnServerOrder'),
  ...pair('sd_status', 'sortOnSdStatus'),
  ...pair('sd_solved', 'sortOnSdSolved'),
  ...pair('sd_requester_updated', 'sortOnSdRequesterUpdated'),
  ...pair('sd_assignee_updated', 'sortOnSdAssigneeUpdated'),
});

export const SD_SORT_CONFIG = Object.freeze({
  sortOnSdSla: comparatorFor(SD_SORT_VALUE.sdSla),
  sortOnSdId: comparatorFor(SD_SORT_VALUE.sdId),
  sortOnSdSubject: comparatorFor(SD_SORT_VALUE.sdSubject),
  sortOnSdGroup: comparatorFor(SD_SORT_VALUE.sdGroup),
  sortOnSdRequester: comparatorFor(SD_SORT_VALUE.sdRequester),
  sortOnSdAssignee: comparatorFor(SD_SORT_VALUE.sdAssignee),
  sortOnSdStatus: comparatorFor(SD_SORT_VALUE.sdStatus),
  sortOnSdSolved: comparatorFor(SD_SORT_VALUE.sdSolved),
  sortOnSdRequesterUpdated: comparatorFor(SD_SORT_VALUE.sdRequesterUpdated),
  sortOnSdAssigneeUpdated: comparatorFor(SD_SORT_VALUE.sdAssigneeUpdated),
  // Dado que não vem no payload: mantém a ordem do servidor.
  sortOnServerOrder: () => 0,
});

export const isSdSortKey = sortBy =>
  Object.prototype.hasOwnProperty.call(SD_SORT_OPTIONS, sortBy);
