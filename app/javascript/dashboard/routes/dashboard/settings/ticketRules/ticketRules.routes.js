import { frontendURL } from '../../../../helper/URLHelper';
import SettingsWrapper from '../SettingsWrapper.vue';
import Index from './Index.vue';

const meta = { permissions: ['administrator'] };

export default {
  routes: [
    {
      path: frontendURL('accounts/:accountId/settings/triggers'),
      component: SettingsWrapper,
      children: [
        {
          path: '',
          name: 'ticket_triggers_index',
          component: Index,
          props: { kind: 'trigger' },
          meta,
        },
      ],
    },
    {
      path: frontendURL('accounts/:accountId/settings/automations'),
      component: SettingsWrapper,
      children: [
        {
          path: '',
          name: 'ticket_automations_index',
          component: Index,
          props: { kind: 'automation' },
          meta,
        },
      ],
    },
  ],
};
