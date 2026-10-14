import { describe, expect, it, vi } from 'vitest';
import { hasPermissions } from 'dashboard/helper/permissionsHelper';
import rolePermissions from './fixtures/rolePermissions.json';

import { routes as contactRoutes } from 'dashboard/routes/dashboard/contacts/routes';
import { routes as companyRoutes } from 'dashboard/routes/dashboard/companies/routes';
import reportRoutes from 'dashboard/routes/dashboard/settings/reports/reports.routes';
import macroRoutes from 'dashboard/routes/dashboard/settings/macros/macros.routes';
import sdRoleRoutes from 'dashboard/routes/dashboard/settings/sdRoles/sdRoles.routes';

// ServiceDesk M13: o menu (barra lateral) mostra um item quando o usuário tem alguma das permissões da rota
// (provider.js -> isAllowed -> usePolicy.shouldShow -> hasPermissions). Aqui usamos as rotas REAIS do painel e
// as permissões que o backend envia para cada papel do Zendesk (fixture conferida pelo rspec).

vi.mock('dashboard/routes/dashboard/contacts/pages/ContactsIndex.vue', () => ({
  default: {},
}));
vi.mock(
  'dashboard/routes/dashboard/contacts/pages/ContactManageView.vue',
  () => ({ default: {} })
);
vi.mock(
  'dashboard/routes/dashboard/companies/pages/CompaniesIndex.vue',
  () => ({ default: {} })
);
vi.mock(
  'dashboard/routes/dashboard/companies/pages/CompanyDetailView.vue',
  () => ({ default: {} })
);
vi.mock('dashboard/routes/dashboard/settings/SettingsWrapper.vue', () => ({
  default: {},
}));
vi.mock('dashboard/routes/dashboard/settings/Wrapper.vue', () => ({
  default: {},
}));
vi.mock('dashboard/routes/dashboard/settings/macros/Index.vue', () => ({
  default: {},
}));
vi.mock('dashboard/routes/dashboard/settings/macros/MacroEditor.vue', () => ({
  default: {},
}));
vi.mock('dashboard/routes/dashboard/settings/sdRoles/Index.vue', () => ({
  default: {},
}));
vi.mock(
  'dashboard/routes/dashboard/settings/reports/components/ReportsWrapper.vue',
  () => ({ default: {} })
);
vi.mock('dashboard/routes/dashboard/settings/reports/Index.vue', () => ({
  default: {},
}));
vi.mock(
  'dashboard/routes/dashboard/settings/reports/AgentReportsIndex.vue',
  () => ({ default: {} })
);
vi.mock(
  'dashboard/routes/dashboard/settings/reports/InboxReportsIndex.vue',
  () => ({ default: {} })
);
vi.mock(
  'dashboard/routes/dashboard/settings/reports/LabelReportsIndex.vue',
  () => ({ default: {} })
);
vi.mock(
  'dashboard/routes/dashboard/settings/reports/TeamReportsIndex.vue',
  () => ({ default: {} })
);
vi.mock(
  'dashboard/routes/dashboard/settings/reports/AgentReportsShow.vue',
  () => ({ default: {} })
);
vi.mock(
  'dashboard/routes/dashboard/settings/reports/InboxReportsShow.vue',
  () => ({ default: {} })
);
vi.mock(
  'dashboard/routes/dashboard/settings/reports/LabelReportsShow.vue',
  () => ({ default: {} })
);
vi.mock(
  'dashboard/routes/dashboard/settings/reports/TeamReportsShow.vue',
  () => ({ default: {} })
);
vi.mock('dashboard/routes/dashboard/settings/reports/AgentReports.vue', () => ({
  default: {},
}));
vi.mock('dashboard/routes/dashboard/settings/reports/InboxReports.vue', () => ({
  default: {},
}));
vi.mock('dashboard/routes/dashboard/settings/reports/LabelReports.vue', () => ({
  default: {},
}));
vi.mock('dashboard/routes/dashboard/settings/reports/TeamReports.vue', () => ({
  default: {},
}));
vi.mock('dashboard/routes/dashboard/settings/reports/BotReports.vue', () => ({
  default: {},
}));
vi.mock(
  'dashboard/routes/dashboard/settings/reports/CsatResponses.vue',
  () => ({ default: {} })
);
vi.mock('dashboard/routes/dashboard/settings/reports/LiveReports.vue', () => ({
  default: {},
}));
vi.mock(
  'dashboard/routes/dashboard/settings/reports/monitors/MonitorShow.vue',
  () => ({ default: {} })
);
vi.mock(
  'dashboard/routes/dashboard/settings/reports/monitors/MonitorsIndex.vue',
  () => ({ default: {} })
);
vi.mock('dashboard/routes/dashboard/settings/reports/SLAReports.vue', () => ({
  default: {},
}));

const allRoutes = [
  ...contactRoutes,
  ...companyRoutes,
  ...reportRoutes.routes,
  ...macroRoutes.routes,
  ...sdRoleRoutes.routes,
];

const findRoute = (list, name) => {
  let found = null;
  list.some(route => {
    if (route.name === name) found = route;
    else if (route.children) found = findRoute(route.children, name);
    return !!found;
  });
  return found;
};

// Itens da barra lateral (Sidebar.vue) e a rota de destino de cada um
const MENU = {
  contatos: 'contacts_dashboard_index',
  empresas: 'companies_dashboard_index',
  relatorios: 'account_overview_reports',
  macros: 'macros_wrapper',
  papeis: 'sd_roles_list',
};

const visibleMenu = role =>
  Object.entries(MENU)
    .filter(([, routeName]) => {
      const route = findRoute(allRoutes, routeName);
      const permissions = route?.meta?.permissions || [];
      return hasPermissions(permissions, rolePermissions[role]);
    })
    .map(([item]) => item);

describe('ServiceDesk M13 - menu conforme o papel (padrão Zendesk)', () => {
  it('todas as rotas do menu existem', () => {
    Object.values(MENU).forEach(name => {
      expect(findRoute(allRoutes, name), name).not.toBeNull();
    });
  });

  it('administrador vê tudo, inclusive Papéis', () => {
    expect(visibleMenu('administrador')).toEqual([
      'contatos',
      'empresas',
      'relatorios',
      'macros',
      'papeis',
    ]);
  });

  it('agente vê contatos e macros pessoais; não vê relatórios nem Papéis', () => {
    expect(visibleMenu('agente')).toEqual(['contatos', 'empresas', 'macros']);
  });

  it('agente light vê contatos e relatórios (só leitura); não gerencia macros', () => {
    expect(visibleMenu('agente_light')).toEqual([
      'contatos',
      'empresas',
      'relatorios',
    ]);
  });

  it('colaborador não vê lista de usuários finais, relatórios nem macros', () => {
    expect(visibleMenu('colaborador')).toEqual([]);
  });

  it('agente sem papel SD mantém o menu do Chatwoot CE', () => {
    expect(visibleMenu('sem_papel')).toEqual([
      'contatos',
      'empresas',
      'macros',
    ]);
  });
});
