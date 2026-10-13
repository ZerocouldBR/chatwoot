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

  await page.goto(`/app/accounts/${env.account_id}/conversations/${ticket.id}`);
  await expect(page.getByText(`Primeira mensagem ${stamp}`)).toBeVisible();
  await api.ctx.dispose();
});
