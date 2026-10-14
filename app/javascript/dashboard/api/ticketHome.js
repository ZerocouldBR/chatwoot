/* global axios */
import ApiClient from './ApiClient';

class TicketHomeAPI extends ApiClient {
  constructor() {
    super('ticket_home', { accountScoped: true });
  }

  getView({ view, page = 1 }) {
    return axios.get(this.url, { params: { view, page } });
  }

  getStats() {
    return axios.get(`${this.url}/stats`);
  }
}

export default new TicketHomeAPI();
