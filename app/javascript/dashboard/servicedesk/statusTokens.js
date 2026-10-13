/**
 * ServiceDesk — tokens de status de ticket (estilo Agent Workspace / Zendesk Garden).
 *
 * Fonte única para listas, painel do ticket, filtros e relatórios.
 * As cores reais vivem em variáveis CSS (`--sd-status-*`, ver
 * assets/scss/_servicedesk-theme.scss), então claro/escuro funcionam sozinhos.
 * As classes Tailwind abaixo vêm de `theme/colors.js` (chave `sd.status`).
 *
 * Categorias (as mesmas de CustomStatus.category no design de migração):
 *   new (Novo) · open (Aberto) · pending (Pendente) · hold (Em espera)
 *   · solved (Resolvido) · closed (Fechado)
 *
 * Uso:
 *   import { getStatusToken } from 'dashboard/servicedesk/statusTokens';
 *   const token = getStatusToken(conversation.status); // aceita status nativo
 *   <span :class="token.classes.badge">{{ $t(token.labelKey) }}</span>
 */

export const STATUS_CATEGORIES = Object.freeze([
  'new',
  'open',
  'pending',
  'hold',
  'solved',
  'closed',
]);

// Status nativo do Chatwoot -> categoria ServiceDesk/Zendesk.
// "new" não existe no Chatwoot: vem do status personalizado (categoria new).
export const NATIVE_STATUS_TO_CATEGORY = Object.freeze({
  open: 'open',
  pending: 'pending',
  snoozed: 'hold',
  resolved: 'solved',
});

// Categoria -> status nativo usado quando um status personalizado é aplicado.
export const CATEGORY_TO_NATIVE_STATUS = Object.freeze({
  new: 'open',
  open: 'open',
  pending: 'pending',
  hold: 'snoozed',
  solved: 'resolved',
  closed: 'resolved',
});

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
 * Resolve o token a partir de uma categoria (new/open/...) ou de um status
 * nativo do Chatwoot (open/pending/snoozed/resolved). Desconhecido -> open.
 */
export const getStatusToken = statusOrCategory => {
  const key = String(statusOrCategory || '').toLowerCase();
  if (STATUS_TOKENS[key]) return STATUS_TOKENS[key];
  const category = NATIVE_STATUS_TO_CATEGORY[key];
  return STATUS_TOKENS[category] || STATUS_TOKENS.open;
};

export default STATUS_TOKENS;
