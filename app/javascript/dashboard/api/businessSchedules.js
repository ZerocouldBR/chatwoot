import ApiClient from './ApiClient';

class BusinessSchedulesAPI extends ApiClient {
  constructor() {
    super('business_schedules', { accountScoped: true });
  }
}

export default new BusinessSchedulesAPI();
