import { test, expect } from '@playwright/test';
import { ApiClient } from '@helpers/api';
import { E2E_PASSWORD, loadE2EEnv } from '@helpers/e2e-env';

// Smoke test for the ticket E2E harness: isolated account, API client and logged-in UI session.
test('API-created ticket shows up for the logged-in admin', async ({ page, baseURL }) => {
  const env = loadE2EEnv();
  const api = await ApiClient.login(baseURL!, env.users.admin.email, E2E_PASSWORD, env.account_id);
  const stamp = Date.now();
  const contact = await api.createContact(`Cliente ${stamp}`, `cliente-${stamp}@example.test`);
  const ticket = await api.createConversation(env.api_inbox_id, contact.id, `Primeira mensagem ${stamp}`);

  await page.goto(`/app/accounts/${env.account_id}/tickets/${ticket.id}`);
  await expect(page.locator('[id^=message]').getByText(`Primeira mensagem ${stamp}`)).toBeVisible();
  await api.dispose();
});

test('old conversation links still open the ticket', async ({ page, baseURL }) => {
  const env = loadE2EEnv();
  const api = await ApiClient.login(baseURL!, env.users.admin.email, E2E_PASSWORD, env.account_id);
  const stamp = Date.now();
  const contact = await api.createContact(`Cliente ${stamp}`, `cliente-${stamp}@example.test`);
  const ticket = await api.createConversation(env.api_inbox_id, contact.id, `Link antigo ${stamp}`);

  await page.goto(`/app/accounts/${env.account_id}/conversations/${ticket.id}`);
  await expect(page.locator('[id^=message]').getByText(`Link antigo ${stamp}`)).toBeVisible();
  await expect(page.getByRole('link', { name: 'Tickets' }).first()).toBeVisible();
  await api.dispose();
});

// Regression: the "Unsolved" default filter once made the list refetch forever.
test('the ticket list loads once with the unsolved filter', async ({ page, baseURL }) => {
  const env = loadE2EEnv();
  const api = await ApiClient.login(baseURL!, env.users.admin.email, E2E_PASSWORD, env.account_id);
  const stamp = Date.now();
  const contact = await api.createContact(`Lista ${stamp}`, `lista-${stamp}@example.test`);
  await api.createConversation(env.api_inbox_id, contact.id, `Lista ${stamp}`);

  let listRequests = 0;
  page.on('request', request => {
    if (/\/api\/v1\/accounts\/\d+\/conversations\?/.test(request.url())) listRequests += 1;
  });
  await page.goto(`/app/accounts/${env.account_id}/dashboard`);
  await expect(page.getByRole('heading', { level: 4 }).first()).toBeVisible();
  await page.waitForTimeout(5000);
  expect(listRequests).toBeLessThan(5);
  await api.dispose();
});
