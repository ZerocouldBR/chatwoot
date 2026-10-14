import { test, expect } from '@playwright/test';
import { ApiClient } from '@helpers/api';
import { E2E_PASSWORD, loadE2EEnv } from '@helpers/e2e-env';

// Agent home: your tickets, tickets you are CC'd on or following, and the stats panel.
test('agent home lists my tickets, CCs and followed tickets', async ({ page, baseURL }) => {
  const env = loadE2EEnv();
  const admin = env.users.admin;
  const api = await ApiClient.login(baseURL!, admin.email, E2E_PASSWORD, env.account_id);
  const stamp = Date.now();
  const contact = await api.createContact(`Hotel Home ${stamp}`, `hotel-home-${stamp}@example.test`);

  const mine = await api.createConversation(env.api_inbox_id, contact.id, `Meu ticket ${stamp}`);
  await api.call('post', `/conversations/${mine.id}/assignments`, { assignee_id: admin.id });
  const copied = await api.createConversation(env.api_inbox_id, contact.id, `Em cópia ${stamp}`);
  await api.call('post', `/conversations/${copied.id}/ccs`, { email: admin.email });
  const followed = await api.createConversation(env.api_inbox_id, contact.id, `Seguindo ${stamp}`);
  await api.call('post', `/conversations/${followed.id}/participants`, { user_ids: [admin.id] });

  await page.goto(`/app/accounts/${env.account_id}/home`);
  await expect(page.getByTestId('home-ticket').filter({ hasText: `Meu ticket ${stamp}` })).toBeVisible();

  await page.getByTestId('home-view-ccs').click();
  await expect(page.getByTestId('home-ticket').filter({ hasText: `Em cópia ${stamp}` })).toBeVisible();

  await page.getByTestId('home-view-following').click();
  await expect(page.getByTestId('home-ticket').filter({ hasText: `Seguindo ${stamp}` })).toBeVisible();

  await expect(page.getByTestId('home-stats').getByText('Estatísticas do ticket')).toBeVisible();

  await page.getByTestId('home-ticket').filter({ hasText: `Seguindo ${stamp}` }).click();
  await expect(page).toHaveURL(new RegExp(`/tickets/${followed.id}$`));
  await api.ctx.dispose();
});
