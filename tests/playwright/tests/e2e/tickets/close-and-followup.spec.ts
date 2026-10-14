import { test, expect } from '@playwright/test';
import { ApiClient } from '@helpers/api';
import { E2E_PASSWORD, loadE2EEnv } from '@helpers/e2e-env';
import { railsRunner } from '@helpers/rails';

// Solved tickets close after the account delay and become read-only, like Zendesk.
test('a solved ticket closes and can no longer be changed', async ({ page, baseURL }) => {
  const env = loadE2EEnv();
  const api = await ApiClient.login(baseURL!, env.users.admin.email, E2E_PASSWORD, env.account_id);
  const stamp = Date.now();
  const contact = await api.createContact(`Cliente ${stamp}`, `cliente-close-${stamp}@example.test`);
  const ticket = await api.createConversation(env.api_inbox_id, contact.id, `Fechar ${stamp}`);
  await api.call('post', `/conversations/${ticket.id}/toggle_status`, { status: 'resolved' });

  const statuses = railsRunner<Record<string, string>>('tests/playwright/support/close_solved_tickets.rb', {
    E2E_ACCOUNT_ID: String(env.account_id),
    E2E_TICKET_IDS: String(ticket.id),
  });
  expect(statuses[String(ticket.id)]).toBe('closed');

  await page.goto(`/app/accounts/${env.account_id}/tickets/${ticket.id}`);
  await expect(page.locator('.conversation--header--actions').getByText('Fechado')).toBeVisible();
  await expect(page.getByText('Este ticket está fechado.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Resolver' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Reabrir' })).toHaveCount(0);

  await expect(api.call('post', `/conversations/${ticket.id}/messages`, { content: 'oi' })).rejects.toThrow(/422/);
  await expect(api.call('post', `/conversations/${ticket.id}/toggle_status`, { status: 'open' })).rejects.toThrow(/422/);
  await api.dispose();
});

test('the close delay is configured in the ticket settings', async ({ page, baseURL }) => {
  const env = loadE2EEnv();
  await page.goto(`/app/accounts/${env.account_id}/settings/conversation-workflow`);
  const hours = page.getByTestId('close-solved-hours');
  await expect(hours).toHaveValue('96');
  await hours.fill('48');
  await page.getByRole('button', { name: 'Salvar' }).first().click();
  await expect(page.getByText('Prazo de fechamento salvo')).toBeVisible();

  const api = await ApiClient.login(baseURL!, env.users.admin.email, E2E_PASSWORD, env.account_id);
  const account = await api.ctx.get(`/api/v1/accounts/${env.account_id}`, { headers: api.auth });
  expect((await account.json()).settings.close_solved_after_hours).toBe(48);
  await hours.fill('96');
  await page.getByRole('button', { name: 'Salvar' }).first().click();
  await api.dispose();
});
