import { test, expect } from '@playwright/test';
import { ApiClient } from '@helpers/api';
import { E2E_PASSWORD, loadE2EEnv } from '@helpers/e2e-env';
import { railsRunner } from '@helpers/rails';

type Policy = { id: number; name: string; targets: Array<{ metric: string; priority: string; minutes: number }> };

// SLA policies: per-priority targets shown on the ticket and fulfilled by the first agent reply.
test.describe('SLA', () => {
  const env = loadE2EEnv();
  let api: ApiClient;
  let policyId: number | undefined;

  test.beforeEach(async ({ baseURL }) => {
    api = await ApiClient.login(baseURL!, env.users.admin.email, E2E_PASSWORD, env.account_id);
  });

  test.afterEach(async () => {
    if (policyId) await api.call('delete', `/sla_policies/${policyId}`);
    await api.dispose();
  });

  test('admin creates a policy and urgent tickets show the first reply target', async ({ page }) => {
    const name = `Urgentes ${Date.now()}`;
    await page.goto(`/app/accounts/${env.account_id}/settings/sla/list`);
    await page.getByRole('button', { name: 'Nova política' }).click();
    await page.getByTestId('sla-name').fill(name);
    await page.getByRole('button', { name: 'Adicionar condição' }).first().click();
    await page.getByTestId('sla-target-first_reply_time-urgent').fill('30');
    await page.getByTestId('sla-policy-form').getByRole('button', { name: 'Salvar' }).click();
    await expect(page.getByText('Política salva')).toBeVisible();

    const { payload } = await api.call<{ payload: Policy[] }>('get', '/sla_policies');
    const policy = payload.find(item => item.name === name)!;
    policyId = policy.id;
    expect(policy.targets).toEqual([{ metric: 'first_reply_time', priority: 'urgent', minutes: 30, business_hours: false }]);

    const stamp = Date.now();
    const contact = await api.createContact(`SLA ${stamp}`, `sla-${stamp}@example.test`);
    const ticket = await api.createCustomerTicket(env.api_inbox_id, contact.id, `Urgente ${stamp}`);
    await api.call('post', `/conversations/${ticket.id}/toggle_priority`, { priority: 'urgent' });
    await expect.poll(async () => (await api.getConversation(ticket.id)).next_sla_breach_at, { timeout: 30_000 }).toBeTruthy();

    await page.goto(`/app/accounts/${env.account_id}/tickets/${ticket.id}`);
    const badge = page.getByTestId('ticket-header').getByTestId('ticket-sla-badge');
    await expect(badge).toContainText(/2\d min|30 min/);

    await api.call('post', `/conversations/${ticket.id}/messages`, { content: 'Já estamos verificando.' });
    await expect.poll(async () => (await api.getConversation(ticket.id)).next_sla_breach_at, { timeout: 30_000 }).toBeNull();

    const late = await api.createCustomerTicket(env.api_inbox_id, contact.id, `Atrasado ${stamp}`);
    await api.call('post', `/conversations/${late.id}/toggle_priority`, { priority: 'urgent' });
    const result = railsRunner<{ sla_breached: boolean }>('tests/playwright/support/age_ticket_for_sla.rb', {
      E2E_ACCOUNT_ID: String(env.account_id),
      E2E_TICKET_ID: String(late.id),
      E2E_MINUTES_AGO: '45',
    });
    expect(result.sla_breached).toBe(true);
    await page.goto(`/app/accounts/${env.account_id}/tickets/${late.id}`);
    await expect(page.getByTestId('ticket-header').getByTestId('ticket-sla-badge')).toContainText('SLA violado');

    // The SLA report lists the breach of the late ticket under its policy.
    await page.goto(`/app/accounts/${env.account_id}/reports/sla`);
    const row = page.locator('div.grid').filter({ has: page.getByRole('link', { name: `#${late.id}` }) });
    await expect(row).toContainText(name);
    await row.getByRole('button', { name: 'Ver detalhes' }).click();
    await expect(page.getByText('Tempo de primeira resposta')).toBeVisible();
  });
});
