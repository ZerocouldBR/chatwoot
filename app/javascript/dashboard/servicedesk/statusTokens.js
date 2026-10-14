/**
 * ServiceDesk — status personalizados do cliente (Em andamento, Desenvolvimento...) e a categoria Zendesk de cada um.
 * A categoria define o status nativo do ticket, que segue os status do Zendesk: Novo, Aberto, Pendente, Em espera,
 * Resolvido e Fechado. Fechado não é definido por agentes nem macros (o sistema fecha os resolvidos), então a categoria
 * "closed" resolve o ticket. Espelha config/servicedesk/ticket_statuses.yml.
 */

export const STATUS_CATEGORIES = Object.freeze([
  'new',
  'open',
  'pending',
  'hold',
  'solved',
  'closed',
]);

// Categoria -> status nativo do ticket.
export const CATEGORY_TO_NATIVE_STATUS = Object.freeze({
  new: 'open',
  open: 'open',
  pending: 'waiting_on_customer',
  hold: 'on_hold',
  solved: 'resolved',
  closed: 'resolved',
});

export const CUSTOM_STATUS_CATEGORY = Object.freeze({
  novo: 'new',
  aberto: 'open',
  'em andamento': 'open',
  'devolvido cliente': 'open',
  reaberto: 'open',
  pendente: 'pending',
  'pendente autenticacao': 'pending',
  'aguardando desenvolvimento': 'hold',
  escalonado: 'hold',
  desenvolvimento: 'hold',
  'retorno integracoes': 'hold',
  devolvido: 'hold',
  'desenvolvimento concluido': 'hold',
  resolvido: 'solved',
  concluido: 'solved',
  'respondido cliente': 'solved',
  'autenticacao pendente': 'solved',
  fechado: 'closed',
});

export const normalizeStatusLabel = label =>
  String(label ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();

/** Categoria de um rótulo de status personalizado (ou null se desconhecido). */
export const categoryForCustomStatus = label =>
  CUSTOM_STATUS_CATEGORY[normalizeStatusLabel(label)] || null;
