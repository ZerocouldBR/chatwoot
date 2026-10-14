import { FEATURE_FLAGS } from '../../../../featureFlags';
import { frontendURL } from 'dashboard/helper/URLHelper';

import { SD_ROUTE_PERMISSIONS } from 'dashboard/servicedesk/roles/permissions';
import SettingsContent from '../Wrapper.vue';
import SettingsWrapper from '../SettingsWrapper.vue';
import Macros from './Index.vue';
import MacroEditor from './MacroEditor.vue';

export default {
  routes: [
    {
      path: frontendURL('accounts/:accountId/settings/macros'),
      component: SettingsWrapper,
      children: [
        {
          path: '',
          name: 'macros_wrapper',
          component: Macros,
          meta: {
            featureFlag: FEATURE_FLAGS.MACROS,
            // ServiceDesk M13: só quem cria macros (pessoais ou compartilhadas); readonly só aplica no ticket
            permissions: SD_ROUTE_PERMISSIONS.macros,
          },
        },
      ],
    },
    {
      path: frontendURL('accounts/:accountId/settings/macros'),
      component: SettingsContent,
      props: () => {
        return {
          headerTitle: 'MACROS.HEADER',
          icon: 'flash-settings',
          showBackButton: true,
        };
      },
      children: [
        {
          path: ':macroId/edit',
          name: 'macros_edit',
          component: MacroEditor,
          meta: {
            featureFlag: FEATURE_FLAGS.MACROS,
            // ServiceDesk M13: só quem cria macros (pessoais ou compartilhadas); readonly só aplica no ticket
            permissions: SD_ROUTE_PERMISSIONS.macros,
          },
        },
        {
          path: 'new',
          name: 'macros_new',
          component: MacroEditor,
          meta: {
            featureFlag: FEATURE_FLAGS.MACROS,
            // ServiceDesk M13: só quem cria macros (pessoais ou compartilhadas); readonly só aplica no ticket
            permissions: SD_ROUTE_PERMISSIONS.macros,
          },
        },
      ],
    },
  ],
};
