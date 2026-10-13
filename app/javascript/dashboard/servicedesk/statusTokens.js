/**
 * ServiceDesk — tokens de status de ticket (estilo Agent Workspace / Garden).
 *
 * Fonte única para listas, painel do ticket, filtros e relatórios.
 * As cores reais vivem em variáveis CSS (`--sd-status-*`, ver
 * assets/scss/_servicedesk-theme.scss), então claro/escuro funcionam sozinhos.
 * As classes Tailwind abaixo vêm de `theme/colors.js` (chave `sd.status`).
 *
 * STATUS CANÔNICO (decisão 1 do projeto; fonte: zendesk_field_map.json,
 * custom_statuses[].chatwoot_status):
 *   new -> open · open -> open · pending -> snoozed · hold -> snoozed
 *   · solved -> resolved · closed -> resolved
 * O rótulo exato (Novo, Em andamento, Desenvolvimento...) fica no atributo
 * `zd_status` da conversa; Pendente x Em espera se distinguem por ele.
 * O status nativo `pending` do Chatwoot NÃO é usado (reservado a bot/IA).
 *
 * Uso:
 *   import { resolveTicketStatus } from 'dashboard/servicedesk/statusTokens';
 *   const s = resolveTicketStatus(conversation);
 *   // s.token.classes.badge, s.label (zd_status) ou $t(s.token.labelKey)
 */

export const STATUS_CATEGORIES = Object.freeze([
  'new',
  'open',
  'pending',
  'hold',
  'solved',
  'closed',
]);

// Categoria -> status nativo do Chatwoot (status canônico).
export const CATEGORY_TO_NATIVE_STATUS = Object.freeze({
  new: 'open',
  open: 'open',
  pending: 'snoozed',
  hold: 'snoozed',
  solved: 'resolved',
  closed: 'resolved',
});

// Status nativo -> categoria usada quando o ticket não tem `zd_status`.
// snoozed é ambíguo (Pendente ou Em espera): sem rótulo, vale Pendente.
// pending (fila do bot/IA) é exibido como Aberto.
export const NATIVE_STATUS_TO_CATEGORY = Object.freeze({
  open: 'open',
  snoozed: 'pending',
  resolved: 'solved',
  pending: 'open',
});

// Status personalizados (rótulo normalizado: minúsculas, sem acento) ->
// categoria. Inclui os inativos, que ainda aparecem em tickets antigos.
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

const build = (category, hex) => {
  const name = `sd-status-${category}`;
  return Object.freeze({
    category,
    labelKey: `SD_THEME.STATUS.${category.toUpperCase()}`,
    shortLabelKey: `SD_THEME.STATUS_SHORT.${category.toUpperCase()}`,
    // Valores de referência (modo claro) para gráficos/canvas/e-mails.
    hex: Object.freeze(hex),
    // Variáveis CSS (canais RGB): use como `rgb(var(--sd-status-open))`.
    cssVar: Object.freeze({
      bg: `--${name}`,
      fg: `--${name}-fg`,
      softBg: `--${name}-soft`,
      softFg: `--${name}-soft-fg`,
    }),
    // Classes Tailwind prontas (listas completas para o JIT encontrar).
    classes: Object.freeze({
      badge: `bg-${name} text-${name}-fg`,
      soft: `bg-${name}-soft text-${name}-soft-fg`,
      dot: `bg-${name}`,
      text: `text-${name}-soft-fg`,
      border: `border-${name}`,
    }),
  });
};

export const STATUS_TOKENS = Object.freeze({
  new: build('new', {
    bg: '#FFB057',
    fg: '#2F3941',
    softBg: '#FFF7ED',
    softFg: '#AD5918',
  }),
  open: build('open', {
    bg: '#CC3340',
    fg: '#FFFFFF',
    softBg: '#FFF0F1',
    softFg: '#8C232C',
  }),
  pending: build('pending', {
    bg: '#1F73B7',
    fg: '#FFFFFF',
    softBg: '#EDF7FF',
    softFg: '#144A75',
  }),
  hold: build('hold', {
    bg: '#2F3941',
    fg: '#FFFFFF',
    softBg: '#E9EBED',
    softFg: '#2F3941',
  }),
  solved: build('solved', {
    bg: '#68737D',
    fg: '#FFFFFF',
    softBg: '#F8F9F9',
    softFg: '#49545C',
  }),
  closed: build('closed', {
    bg: '#D8DCDE',
    fg: '#2F3941',
    softBg: '#F8F9F9',
    softFg: '#68737D',
  }),
});

/*
 * Referência literal das classes para o Tailwind JIT (não remover):
 * bg-sd-status-new text-sd-status-new-fg bg-sd-status-new-soft text-sd-status-new-soft-fg border-sd-status-new
 * bg-sd-status-open text-sd-status-open-fg bg-sd-status-open-soft text-sd-status-open-soft-fg border-sd-status-open
 * bg-sd-status-pending text-sd-status-pending-fg bg-sd-status-pending-soft text-sd-status-pending-soft-fg border-sd-status-pending
 * bg-sd-status-hold text-sd-status-hold-fg bg-sd-status-hold-soft text-sd-status-hold-soft-fg border-sd-status-hold
 * bg-sd-status-solved text-sd-status-solved-fg bg-sd-status-solved-soft text-sd-status-solved-soft-fg border-sd-status-solved
 * bg-sd-status-closed text-sd-status-closed-fg bg-sd-status-closed-soft text-sd-status-closed-soft-fg border-sd-status-closed
 */

/**
 * Resolve o token a partir de uma categoria (new/open/pending/...) ou de um
 * status nativo do Chatwoot (open/snoozed/resolved). Desconhecido -> open.
 * `pending` é lido como categoria; para status nativo use getNativeStatusToken.
 */
export const getStatusToken = statusOrCategory => {
  const key = String(statusOrCategory || '').toLowerCase();
  if (STATUS_TOKENS[key]) return STATUS_TOKENS[key];
  const category = NATIVE_STATUS_TO_CATEGORY[key];
  return STATUS_TOKENS[category] || STATUS_TOKENS.open;
};

/**
 * Token de um status NATIVO do Chatwoot. Diferente de getStatusToken, trata
 * `pending` como status nativo (fila do bot/IA -> Aberto), não como categoria.
 */
export const getNativeStatusToken = nativeStatus =>
  STATUS_TOKENS[NATIVE_STATUS_TO_CATEGORY[nativeStatus] || 'open'];

/**
 * Status exibido de um ticket: rótulo `zd_status` (quando existe) com a cor da
 * sua categoria; senão a categoria derivada do status nativo.
 * Aceita a conversa (status + custom_attributes) ou `{ status, zdStatus }`.
 */
export const resolveTicketStatus = (conversationOrStatus = {}) => {
  const nativeStatus = conversationOrStatus.status || 'open';
  const rawLabel =
    conversationOrStatus.zdStatus ??
    conversationOrStatus.custom_attributes?.zd_status;
  const label = rawLabel ? String(rawLabel).trim() : '';
  const nativeCategory = NATIVE_STATUS_TO_CATEGORY[nativeStatus] || 'open';
  const category = (label && categoryForCustomStatus(label)) || nativeCategory;
  return {
    category,
    label,
    isCustom: !!label,
    nativeStatus,
    token: STATUS_TOKENS[category],
  };
};

export default STATUS_TOKENS;
