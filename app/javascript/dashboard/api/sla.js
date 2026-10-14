/* global axios */
import ApiClient from './ApiClient';

class SlaAPI extends ApiClient {
  constructor() {
    super('sla_policies', { accountScoped: true });
  }

  reorder(ids) {
    return axios.post(`${this.url}/reorder`, { ids });
  }
}

export default new SlaAPI();
