import rolePermissions from './fixtures/rolePermissions.json';
import {
  canDeleteTicket,
  canEditTicket,
  canManageSuspendedTickets,
  canMergeTicket,
  canViewDeletedTickets,
  getServicedeskRole,
  canReplyPublicly,
  deniedConversationMenuKeys,
  hasSdPermission,
  sdLevel,
  sdRoleKey,
} from '../permissions';

// rolePermissions.json = account.permissions que o backend envia para cada papel padrão do Zendesk
// (conferido pelo rspec spec/services/servicedesk/roles/access_spec.rb).
describe('ServiceDesk M13 - permissões do papel no painel', () => {
  it('identifica o papel e os níveis', () => {
    expect(sdRoleKey(rolePermissions.agente_light)).toBe('agente_light');
    expect(sdRoleKey(rolePermissions.sem_papel)).toBeNull();
    expect(sdLevel(rolePermissions.agente_light, 'reports')).toBe('readonly');
    expect(sdLevel(rolePermissions.colaborador, 'ticket.access')).toBe(
      'groups'
    );
    expect(sdLevel(rolePermissions.agente, 'macros')).toBe('personal');
  });

  it('só agente light e colaborador ficam sem resposta pública', () => {
    expect(canReplyPublicly(rolePermissions.administrador)).toBe(true);
    expect(canReplyPublicly(rolePermissions.agente)).toBe(true);
    expect(canReplyPublicly(rolePermissions.sem_papel)).toBe(true);
    expect(canReplyPublicly(rolePermissions.agente_light)).toBe(false);
    expect(canReplyPublicly(rolePermissions.colaborador)).toBe(false);
    // sem as strings sd: (backend sem o M13): comportamento original do Chatwoot
    expect(canReplyPublicly(['agent'])).toBe(true);
    expect(deniedConversationMenuKeys(['agent'])).toEqual([]);
  });

  it('lê o papel do usuário atual no /profile', () => {
    const role = {
      role_key: 'colaborador',
      ticket_access: 'groups',
      team_ids: [4],
    };
    const user = {
      accounts: [
        { id: 1, servicedesk_role: null },
        { id: 2, servicedesk_role: role },
      ],
    };
    expect(getServicedeskRole(user, '2')).toEqual(role);
    expect(getServicedeskRole(user, 1)).toBeNull();
    expect(getServicedeskRole({}, 1)).toBeNull();
  });

  it('administrador tem tudo mesmo sem a string sd:', () => {
    expect(hasSdPermission(['administrator'], 'ticket.delete')).toBe(true);
    expect(hasSdPermission(['agent'], 'ticket.delete')).toBe(false);
  });

  it('menu de contexto do ticket: light não vê status, responsável, etiquetas nem excluir', () => {
    expect(deniedConversationMenuKeys(rolePermissions.administrador)).toEqual(
      []
    );
    expect(deniedConversationMenuKeys(rolePermissions.agente)).toEqual([]);
    expect(deniedConversationMenuKeys(rolePermissions.sem_papel)).toEqual([
      'delete',
    ]);
    expect(deniedConversationMenuKeys(rolePermissions.agente_light)).toEqual([
      'status',
      'snooze',
      'priority',
      'agent',
      'team',
      'label',
      'delete',
    ]);
  });

  it('controla Enviar como, mesclar, lixeira e suspensos (módulos do Victor) pelo papel', () => {
    expect(canEditTicket(rolePermissions.agente)).toBe(true);
    expect(canEditTicket(rolePermissions.sem_papel)).toBe(true);
    expect(canEditTicket(rolePermissions.agente_light)).toBe(false);
    expect(canEditTicket(rolePermissions.colaborador)).toBe(false);
    expect(canMergeTicket(rolePermissions.agente)).toBe(true);
    expect(canMergeTicket(rolePermissions.colaborador)).toBe(false);
    expect(canDeleteTicket(rolePermissions.agente)).toBe(true);
    expect(canDeleteTicket(rolePermissions.sem_papel)).toBe(false);
    expect(canViewDeletedTickets(rolePermissions.administrador)).toBe(true);
    expect(canViewDeletedTickets(rolePermissions.agente)).toBe(false);
    expect(canManageSuspendedTickets(rolePermissions.agente_light)).toBe(true);
    expect(canManageSuspendedTickets(rolePermissions.agente)).toBe(false);
    // sem as strings sd: (backend sem o M13): padrão do Chatwoot/Victor (lixeira e suspensos só admin)
    expect(canEditTicket(['agent'])).toBe(true);
    expect(canDeleteTicket(['agent'])).toBe(false);
    expect(canViewDeletedTickets(['administrator'])).toBe(true);
  });
});
