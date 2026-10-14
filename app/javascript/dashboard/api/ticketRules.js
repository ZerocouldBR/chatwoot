/* global axios */
import ApiClient from './ApiClient';

class TicketRulesAPI extends ApiClient {
  constructor() {
    super('ticket_rules', { accountScoped: true });
  }

  list(kind) {
    return axios.get(this.url, { params: { kind } });
  }

  createRule(kind, ticketRule) {
    return axios.post(this.url, { kind, ticket_rule: ticketRule });
  }

  updateRule(id, ticketRule) {
    return axios.patch(`${this.url}/${id}`, { ticket_rule: ticketRule });
  }

  reorder(kind, ids) {
    return axios.post(`${this.url}/reorder`, { kind, ids });
  }
}

export default new TicketRulesAPI();
