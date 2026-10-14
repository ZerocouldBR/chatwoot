import { frontendURL } from '../../../helper/URLHelper';
import TicketHome from './TicketHome.vue';
import TicketQueue from './TicketQueue.vue';

export const routes = [
  {
    path: frontendURL('accounts/:accountId/home'),
    name: 'ticket_home',
    meta: {
      permissions: ['administrator', 'agent', 'custom_role'],
    },
    component: TicketHome,
  },
  {
    path: frontendURL('accounts/:accountId/suspended-tickets'),
    name: 'suspended_tickets',
    meta: { permissions: ['administrator'] },
    component: TicketQueue,
    props: { kind: 'suspended' },
  },
  {
    path: frontendURL('accounts/:accountId/deleted-tickets'),
    name: 'deleted_tickets',
    meta: { permissions: ['administrator'] },
    component: TicketQueue,
    props: { kind: 'deleted' },
  },
];
