import { frontendURL } from '../../../helper/URLHelper';
import TicketHome from './TicketHome.vue';

export const routes = [
  {
    path: frontendURL('accounts/:accountId/home'),
    name: 'ticket_home',
    meta: {
      permissions: ['administrator', 'agent', 'custom_role'],
    },
    component: TicketHome,
  },
];
