import { computed } from 'vue';
import { useMapGetter } from 'dashboard/composables/store';
import { getUserPermissions } from 'dashboard/helper/permissionsHelper';
import {
  canEditTicket,
  canEditTags,
  canMergeTicket,
  canDeleteTicket,
  canReplyPublicly,
  canViewDeletedTickets,
  canManageSuspendedTickets,
} from './permissions';

// ServiceDesk M13: permissões do papel do usuário atual na conta atual, para esconder o que o papel não pode
// usar (o backend aplica as mesmas regras e responde 403).
export function useSdRolePermissions() {
  const currentUser = useMapGetter('getCurrentUser');
  const accountId = useMapGetter('getCurrentAccountId');
  const permissions = computed(() =>
    getUserPermissions(currentUser.value, accountId.value)
  );

  return {
    permissions,
    canEditTicket: computed(() => canEditTicket(permissions.value)),
    canEditTags: computed(() => canEditTags(permissions.value)),
    canMergeTicket: computed(() => canMergeTicket(permissions.value)),
    canDeleteTicket: computed(() => canDeleteTicket(permissions.value)),
    canReplyPublicly: computed(() => canReplyPublicly(permissions.value)),
    canViewDeletedTickets: computed(() =>
      canViewDeletedTickets(permissions.value)
    ),
    canManageSuspendedTickets: computed(() =>
      canManageSuspendedTickets(permissions.value)
    ),
  };
}
