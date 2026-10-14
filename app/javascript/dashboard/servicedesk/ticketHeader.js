/**
 * ServiceDesk — cabeçalho do ticket (padrão Agent Workspace): o ASSUNTO em
 * destaque, com o nome do solicitante como alternativa.
 */
import { resolveTicketStatus } from './statusTokens';

/** Assunto do ticket: mail_subject; para tickets importados, zd_assunto. */
export const getTicketSubject = (chat = {}) =>
  String(
    chat.additional_attributes?.mail_subject ||
      chat.custom_attributes?.zd_assunto ||
      ''
  )
    .replace(/\s+/g, ' ')
    .trim();

/**
 * Título do cabeçalho: assunto, senão o nome do contato.
 * `hasSubject` indica se o nome do contato deve aparecer na linha de baixo.
 */
export const getTicketHeaderTitle = (chat = {}, contactName = '') => {
  const subject = getTicketSubject(chat);
  return {
    title: subject || contactName || '',
    hasSubject: !!subject,
  };
};

/** Selo de status do cabeçalho: rótulo zd_status com a cor da categoria. */
export const getTicketHeaderStatus = (chat = {}) => resolveTicketStatus(chat);
