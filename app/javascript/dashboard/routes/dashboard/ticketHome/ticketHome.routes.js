import { frontendURL } from '../../../helper/URLHelper';
import { SD_ROUTE_PERMISSIONS } from 'dashboard/servicedesk/roles/permissions';
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
    // ServiceDesk M13: administrador ou papel com suspended_tickets.manage
    meta: { permissions: SD_ROUTE_PERMISSIONS.suspendedTickets },
    component: TicketQueue,
    props: { kind: 'suspended' },
  },
  {
    path: frontendURL('accounts/:accountId/deleted-tickets'),
    name: 'deleted_tickets',
    // ServiceDesk M13: administrador ou papel com ticket.view_deleted
    meta: { permissions: SD_ROUTE_PERMISSIONS.deletedTickets },
    component: TicketQueue,
    props: { kind: 'deleted' },
  },
];
