// ServiceDesk: Configurações > Telefonia 55PBX (só administrador; o item do menu some para os demais pela permissão).
import { frontendURL } from '../../../../helper/URLHelper';
import SettingsWrapper from '../SettingsWrapper.vue';
import Index from './Index.vue';

export default {
  routes: [
    {
      path: frontendURL('accounts/:accountId/settings/telefonia-55pbx'),
      meta: {
        permissions: ['administrator'],
      },
      component: SettingsWrapper,
      props: {
        headerTitle: 'SD_TELEPHONY.TITLE',
        icon: 'i-lucide-phone-call',
        showNewButton: false,
      },
      children: [
        {
          path: '',
          name: 'sd_telephony_settings_index',
          component: Index,
          meta: {
            permissions: ['administrator'],
          },
        },
      ],
    },
  ],
};
