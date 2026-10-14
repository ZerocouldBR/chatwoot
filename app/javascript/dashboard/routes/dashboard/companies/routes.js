import { frontendURL } from '../../../helper/URLHelper';
import CompaniesIndex from './pages/CompaniesIndex.vue';
import CompanyDetailView from './pages/CompanyDetailView.vue';
import { FEATURE_FLAGS } from '../../../featureFlags';
import { SD_ROUTE_PERMISSIONS } from 'dashboard/servicedesk/roles/permissions';

const commonMeta = {
  featureFlag: FEATURE_FLAGS.COMPANIES,
  // ServiceDesk M13: organizações acompanham a lista de usuários finais (contacts.list)
  permissions: SD_ROUTE_PERMISSIONS.companies,
};

export const routes = [
  {
    path: frontendURL('accounts/:accountId/companies'),
    component: CompaniesIndex,
    meta: commonMeta,
    children: [
      {
        path: '',
        name: 'companies_dashboard_index',
        component: CompaniesIndex,
        meta: commonMeta,
      },
    ],
  },
  {
    path: frontendURL('accounts/:accountId/companies/:companyId'),
    component: CompanyDetailView,
    meta: commonMeta,
    children: [
      {
        path: '',
        name: 'companies_dashboard_show',
        component: CompanyDetailView,
        meta: commonMeta,
      },
    ],
  },
];
