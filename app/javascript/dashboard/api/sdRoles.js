// ServiceDesk M13: API dos papéis (Configurações > Papéis). Código CE próprio, não usa custom_roles.
import ApiClient from './ApiClient';

class SdRolesAPI extends ApiClient {
  constructor() {
    super('sd_roles', { accountScoped: true });
  }
}

export default new SdRolesAPI();
