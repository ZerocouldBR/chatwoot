// ServiceDesk - tokens de status (FALLBACK LOCAL da L2).
//
// A tarefa L1 (layout-tema) e a dona oficial dos tokens de status em
// app/javascript/dashboard/servicedesk/. Enquanto ela nao publicar o arquivo
// oficial, a tabela de tickets usa este fallback. Quando o L1 existir, basta
// trocar os imports em ticketTableHelpers.js e TicketStatusBadge.vue.
//
// Cores inspiradas no Zendesk Garden (Apache-2.0): new=amarelo, open=vermelho,
// pending=azul, hold=grafite, solved/closed=cinza. As cores ficam em JS (style
// inline) porque o Tailwind so varre arquivos .vue.

export const STATUS_CATEGORY = Object.freeze({
  NEW: 'new',
  OPEN: 'open',
  PENDING: 'pending',
  HOLD: 'hold',
  SOLVED: 'solved',
  CLOSED: 'closed',
});

// Ordem usada na ordenacao da coluna Status (ciclo de vida do ticket).
export const STATUS_CATEGORY_ORDER = Object.freeze([
  STATUS_CATEGORY.NEW,
  STATUS_CATEGORY.OPEN,
  STATUS_CATEGORY.PENDING,
  STATUS_CATEGORY.HOLD,
  STATUS_CATEGORY.SOLVED,
  STATUS_CATEGORY.CLOSED,
]);

export const STATUS_BADGE_COLORS = Object.freeze({
  [STATUS_CATEGORY.NEW]: { background: '#FFB057', color: '#2F3941' },
  [STATUS_CATEGORY.OPEN]: { background: '#CC3340', color: '#FFFFFF' },
  [STATUS_CATEGORY.PENDING]: { background: '#1F73B7', color: '#FFFFFF' },
  [STATUS_CATEGORY.HOLD]: { background: '#2F3941', color: '#FFFFFF' },
  [STATUS_CATEGORY.SOLVED]: { background: '#68737D', color: '#FFFFFF' },
  [STATUS_CATEGORY.CLOSED]: { background: '#D8DCDE', color: '#2F3941' },
});

// Status personalizados do Zendesk (custom_statuses.json da B2B Reservas):
// chave normalizada (minusculas, sem acento) -> categoria.
export const ZD_STATUS_CATEGORY_BY_LABEL = Object.freeze({
  novo: STATUS_CATEGORY.NEW,
  aberto: STATUS_CATEGORY.OPEN,
  'em andamento': STATUS_CATEGORY.OPEN,
  'devolvido cliente': STATUS_CATEGORY.OPEN,
  reaberto: STATUS_CATEGORY.OPEN,
  pendente: STATUS_CATEGORY.PENDING,
  'pendente autenticacao': STATUS_CATEGORY.PENDING,
  'aguardando desenvolvimento': STATUS_CATEGORY.HOLD,
  escalonado: STATUS_CATEGORY.HOLD,
  desenvolvimento: STATUS_CATEGORY.HOLD,
  'retorno integracoes': STATUS_CATEGORY.HOLD,
  devolvido: STATUS_CATEGORY.HOLD,
  'desenvolvimento concluido': STATUS_CATEGORY.HOLD,
  resolvido: STATUS_CATEGORY.SOLVED,
  concluido: STATUS_CATEGORY.SOLVED,
  'respondido cliente': STATUS_CATEGORY.SOLVED,
  'autenticacao pendente': STATUS_CATEGORY.SOLVED,
  fechado: STATUS_CATEGORY.CLOSED,
});

// Status nativo do Chatwoot -> categoria (STATUS CANONICO do projeto:
// pending/hold -> snoozed; o rotulo zd_status distingue Pendente de Em espera).
// snoozed sem rotulo = Pendente; pending nativo (fila do bot/IA) = Aberto.
export const NATIVE_STATUS_CATEGORY = Object.freeze({
  open: STATUS_CATEGORY.OPEN,
  snoozed: STATUS_CATEGORY.PENDING,
  resolved: STATUS_CATEGORY.SOLVED,
  pending: STATUS_CATEGORY.OPEN,
});
