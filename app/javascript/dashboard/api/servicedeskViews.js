/* global axios */
import ApiClient from './ApiClient';

// ServiceDesk: views compartilhadas do Zendesk (visibilidade por grupo), com
// colunas, ordenação e contadores (Api::V1::Accounts::Servicedesk::ViewsController).
class ServicedeskViewsAPI extends ApiClient {
  constructor() {
    super('servicedesk/views', { accountScoped: true });
  }

  getCounts() {
    return axios.get(`${this.url}/counts`);
  }
}

export default new ServicedeskViewsAPI();
