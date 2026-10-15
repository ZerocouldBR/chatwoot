// ServiceDesk M13: papéis no painel (padrão Zendesk).
// O backend manda em account.permissions, além de 'administrator'/'agent':
//   'sd:<chave>'          permissão liberada (booleano true ou nível acima de none/readonly)
//   'sd:<chave>:<nível>'  nível das chaves de lista (ex.: 'sd:reports:readonly')
//   'sd_role:<key>'       papel do agente
// (ver Servicedesk::Roles::Access#permission_strings). O backend sempre aplica as mesmas regras; aqui só
// escondemos o que o papel não pode usar.

export const SD_ROUTE_PERMISSIONS = {
  // Usuários finais: some para quem não tem a lista (Colaborador no Zendesk)
  contacts: ['administrator', 'sd:contacts.list', 'contact_manage'],
  companies: ['administrator', 'sd:contacts.list'],
  // Relatórios: admin e quem tem reports >= readonly (Agente light)
  reports: [
    'administrator',
    'report_manage',
    'sd:reports:readonly',
    'sd:reports:full',
  ],
  // Configurações > Macros: só quem cria macros (pessoais ou compartilhadas)
  macros: ['administrator', 'sd:macros'],
  // Configurações > Papéis: só administrador (manage_roles do Zendesk)
  roles: ['administrator'],
  // Lixeira (tickets excluídos) e tickets suspensos do Victor, conforme o papel (Zendesk)
  deletedTickets: ['administrator', 'sd:ticket.view_deleted'],
  suspendedTickets: ['administrator', 'sd:suspended_tickets.manage'],
};

// Papel e permissões efetivas do usuário na conta, como o backend manda em /profile
// (accounts[].servicedesk_role): { role_key, role_name, base_role, ticket_access, team_ids, permissions, ... }.
// Também em GET /api/v1/accounts/:id/sd_roles/me. Usado pelo painel e pelo filtro de views por grupo.
export const getServicedeskRole = (user, accountId) => {
  const account = (user?.accounts || []).find(
    item => Number(item.id) === Number(accountId)
  );
  return account?.servicedesk_role || null;
};

export const hasSdPermission = (permissions = [], key = '') =>
  permissions.includes('administrator') || permissions.includes(`sd:${key}`);

export const sdLevel = (permissions = [], key = '') => {
  const prefix = `sd:${key}:`;
  const found = permissions.find(item => item.startsWith(prefix));
  return found ? found.slice(prefix.length) : null;
};

export const sdRoleKey = (permissions = []) => {
  const found = permissions.find(item => item.startsWith('sd_role:'));
  return found ? found.slice('sd_role:'.length) : null;
};

// O backend do ServiceDesk sempre manda as strings 'sd:'; sem nenhuma (backend sem o M13 ou usuário fora da
// conta), o painel mantém o comportamento original do Chatwoot.
const hasSdData = (permissions = []) =>
  permissions.some(item => item.startsWith('sd:'));

// Pode responder ao cliente? Sem isso (Agente light, Colaborador) o editor fica só em nota interna.
export const canReplyPublicly = (permissions = []) =>
  !hasSdData(permissions) ||
  hasSdPermission(permissions, 'ticket.comment_public');

// Pode mudar o status/propriedades do ticket? Sem ticket.edit (Agente light, Colaborador) o
// "Enviar como <status>", o menu de status e as ações em massa de status/responsável/time não aparecem:
// o editor só grava nota interna.
export const canEditTicket = (permissions = []) =>
  !hasSdData(permissions) || hasSdPermission(permissions, 'ticket.edit');

// Permissões booleanas do papel; sem dados 'sd:' vale o padrão do Chatwoot (fallback).
const sdAllows = (permissions, key, fallback) =>
  hasSdData(permissions) ? hasSdPermission(permissions, key) : fallback;

export const canEditTags = (permissions = []) =>
  sdAllows(permissions, 'ticket.edit_tags', true);

export const canMergeTicket = (permissions = []) =>
  sdAllows(permissions, 'ticket.merge', true);

export const canDeleteTicket = (permissions = []) =>
  sdAllows(permissions, 'ticket.delete', permissions.includes('administrator'));

export const canViewDeletedTickets = (permissions = []) =>
  sdAllows(
    permissions,
    'ticket.view_deleted',
    permissions.includes('administrator')
  );

export const canManageSuspendedTickets = (permissions = []) =>
  sdAllows(
    permissions,
    'suspended_tickets.manage',
    permissions.includes('administrator')
  );

// Itens do menu de contexto do ticket (lista) que o papel não pode usar.
export const deniedConversationMenuKeys = (permissions = []) => {
  const denied = [];
  if (!hasSdData(permissions)) return denied;
  if (!hasSdPermission(permissions, 'ticket.edit')) {
    denied.push('status', 'snooze', 'priority', 'agent', 'team');
  }
  if (!hasSdPermission(permissions, 'ticket.edit_tags')) denied.push('label');
  if (!hasSdPermission(permissions, 'ticket.delete')) denied.push('delete');
  return denied;
};

// Catálogo para a tela Configurações > Papéis (rótulos em i18n SD_ROLES.PERMISSIONS.<chave com _>)
export const PERMISSION_GROUPS = [
  {
    key: 'TICKETS',
    permissions: [
      'ticket.access',
      'ticket.comment_public',
      'ticket.edit',
      'ticket.edit_tags',
      'ticket.assignable',
      'ticket.assign_any_team',
      'ticket.merge',
      'ticket.delete',
      'ticket.redact',
      'ticket.modify_closed',
      'ticket.view_deleted',
      'suspended_tickets.manage',
    ],
  },
  {
    key: 'PEOPLE',
    permissions: [
      'contacts.list',
      'contacts.edit',
      'organizations.edit',
      'team_directory',
      'profile.edit_own',
    ],
  },
  {
    key: 'TOOLS',
    permissions: ['macros', 'views', 'views.export', 'reports', 'kb'],
  },
];

export const permissionI18nKey = key => key.replace(/\./g, '_').toUpperCase();
