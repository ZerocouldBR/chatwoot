/**
 * ServiceDesk — filtro de status da lista (padrão Agent Workspace):
 *   Aberto · Pendente · Em espera · Resolvido · Todos
 *
 * Pelo status canônico, Pendente e Em espera usam o mesmo status nativo
 * (snoozed) e se distinguem pela categoria do rótulo `zd_status`
 * (statusTokens.js / ticketFormsMeta.json):
 *   - Em espera: snoozed com zd_status de categoria "hold";
 *   - Pendente: os demais snoozed (categoria "pending", sem rótulo ou rótulo
 *     desconhecido), exatamente o que o selo da tela mostra.
 *
 * Os valores `sd_pending` / `sd_hold` ficam no store (`chatStatusFilter`) e
 * nas preferências do usuário como qualquer outro status; a API recebe
 * `status=snoozed&zd_status_category=pending|hold` (ver toApiStatusParams) e o
 * backend aplica o mesmo critério (Servicedesk::TicketStatusFilter).
 */
import { resolveTicketStatus } from './statusTokens';

export const SD_STATUS_FILTER = Object.freeze({
  OPEN: 'open',
  PENDING: 'sd_pending',
  HOLD: 'sd_hold',
  RESOLVED: 'resolved',
  ALL: 'all',
});

// valor do filtro -> categoria do zd_status enviada à API
const CATEGORY_BY_FILTER = Object.freeze({
  [SD_STATUS_FILTER.PENDING]: 'pending',
  [SD_STATUS_FILTER.HOLD]: 'hold',
});

/** Opções do menu, na ordem do Agent Workspace (chaves de i18n). */
export const SD_STATUS_FILTER_OPTIONS = Object.freeze([
  SD_STATUS_FILTER.OPEN,
  SD_STATUS_FILTER.PENDING,
  SD_STATUS_FILTER.HOLD,
  SD_STATUS_FILTER.RESOLVED,
  SD_STATUS_FILTER.ALL,
]);

export const isSdCategoryFilter = status => !!CATEGORY_BY_FILTER[status];

/** Status nativo correspondente ao filtro (sd_pending/sd_hold -> snoozed). */
export const toNativeStatus = status =>
  isSdCategoryFilter(status) ? 'snoozed' : status;

/** Parâmetros da API de conversas para o valor do filtro. */
export const toApiStatusParams = status => {
  const category = CATEGORY_BY_FILTER[status];
  if (!category) return { status };
  return { status: 'snoozed', zd_status_category: category };
};

/**
 * O ticket pertence ao filtro? Usado pelo store para manter a lista coerente
 * com as atualizações em tempo real (applyPageFilters).
 */
export const matchesStatusFilter = (conversation, filterStatus) => {
  const ticket = conversation || {};
  if (!filterStatus || filterStatus === SD_STATUS_FILTER.ALL) return true;
  const category = CATEGORY_BY_FILTER[filterStatus];
  if (!category) return ticket.status === filterStatus;
  if (ticket.status !== 'snoozed') return false;
  const isHold = resolveTicketStatus(ticket).category === 'hold';
  return category === 'hold' ? isHold : !isHold;
};
