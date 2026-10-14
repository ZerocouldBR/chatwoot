import { test, expect } from '@playwright/test';
import { ApiClient } from '@helpers/api';
import { E2E_PASSWORD, loadE2EEnv } from '@helpers/e2e-env';

// Zendesk-style ticket lifecycle driven through the agent UI.
test.describe('ticket status lifecycle', () => {
  let api: ApiClient;
  let ticketId: number;
  const env = loadE2EEnv();

  test.beforeEach(async ({ baseURL }) => {
    api = await ApiClient.login(baseURL!, env.users.admin.email, E2E_PASSWORD, env.account_id);
    const stamp = Date.now();
    const contact = await api.createContact(`Solicitante ${stamp}`, `solicitante-${stamp}@example.test`);
    const ticket = await api.createConversation(env.api_inbox_id, contact.id, `Preciso de ajuda ${stamp}`);
    ticketId = ticket.id;
  });

  test.afterEach(async () => {
    await api.ctx.dispose();
  });

  test('new ticket can be put on hold, submitted as pending and resolved', async ({ page }) => {
    expect((await api.getConversation(ticketId)).status).toBe('new_ticket');

    await page.goto(`/app/accounts/${env.account_id}/tickets/${ticketId}`);
    const header = page.locator('.conversation--header--actions');
    await expect(header.getByText('Novo')).toBeVisible();

    await page.getByTestId('ticket-status-menu').click();
    await page.getByRole('button', { name: 'Em espera' }).click();
    await expect(header.getByText('Em espera')).toBeVisible();
    await expect.poll(async () => (await api.getConversation(ticketId)).status).toBe('on_hold');

    await page.locator('.ProseMirror').first().fill('Pode nos enviar o número da reserva?');
    await page.getByTestId('submit-as-menu').click();
    await page.getByRole('button', { name: 'Enviar como Pendente' }).click();
    await expect(page.getByText('Pode nos enviar o número da reserva?')).toBeVisible();
    await expect(header.getByText('Pendente')).toBeVisible();
    await expect.poll(async () => (await api.getConversation(ticketId)).status).toBe('waiting_on_customer');

    await page.getByRole('button', { name: 'Resolver' }).click();
    await expect(header.getByText('Resolvido')).toBeVisible();
    const resolved = await api.getConversation(ticketId);
    expect(resolved.status).toBe('resolved');
    expect((resolved.meta as { assignee?: { id: number } }).assignee?.id).toBe(env.users.admin.id);
  });

  test('statuses only the system sets are rejected by the API', async () => {
    await expect(api.call('post', `/conversations/${ticketId}/toggle_status`, { status: 'closed' })).rejects.toThrow(/422/);
  });
});
