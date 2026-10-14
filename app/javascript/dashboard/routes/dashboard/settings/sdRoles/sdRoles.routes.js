// ServiceDesk M13: Configurações > Papéis (Admin Center > Pessoas > Papéis no Zendesk). Só administrador.
import { frontendURL } from 'dashboard/helper/URLHelper';
import { SD_ROUTE_PERMISSIONS } from 'dashboard/servicedesk/roles/permissions';
import SettingsWrapper from '../SettingsWrapper.vue';
import SdRolesIndex from './Index.vue';

export default {
  routes: [
    {
      path: frontendURL('accounts/:accountId/settings/papeis'),
      component: SettingsWrapper,
      children: [
        {
          path: '',
          name: 'sd_roles_list',
          meta: { permissions: SD_ROUTE_PERMISSIONS.roles },
          component: SdRolesIndex,
        },
      ],
    },
  ],
};
