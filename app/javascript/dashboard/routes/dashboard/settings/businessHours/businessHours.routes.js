import { frontendURL } from '../../../../helper/URLHelper';
import SettingsWrapper from '../SettingsWrapper.vue';
import BusinessHoursIndex from './Index.vue';

export default {
  routes: [
    {
      path: frontendURL('accounts/:accountId/settings/business-hours'),
      component: SettingsWrapper,
      children: [
        {
          path: '',
          name: 'business_hours_index',
          component: BusinessHoursIndex,
          meta: {
            permissions: ['administrator'],
          },
        },
      ],
    },
  ],
};
