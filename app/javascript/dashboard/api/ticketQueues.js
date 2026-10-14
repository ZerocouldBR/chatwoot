/* global axios */
import ApiClient from './ApiClient';

// Deleted tickets (trash) and suspended tickets (held e-mails) share the same list/restore/delete shape.
class TicketQueueAPI extends ApiClient {
  constructor(resource, restoreAction) {
    super(resource, { accountScoped: true });
    this.restoreAction = restoreAction;
  }

  restore(id) {
    return axios.post(`${this.url}/${id}/${this.restoreAction}`);
  }
}

export const DeletedTicketsAPI = new TicketQueueAPI(
  'deleted_tickets',
  'restore'
);
export const SuspendedTicketsAPI = new TicketQueueAPI(
  'suspended_tickets',
  'recover'
);
