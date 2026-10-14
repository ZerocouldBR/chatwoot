import { test, expect } from '@playwright/test';
import { ApiClient } from '@helpers/api';
import { E2E_PASSWORD, loadE2EEnv } from '@helpers/e2e-env';

// The ticket audit trail shows who changed what and through which path.
test('ticket events list the agent changes and comments', async ({ page, baseURL }) => {
  const env = loadE2EEnv();
  const api = await ApiClient.login(baseURL!, env.users.admin.email, E2E_PASSWORD, env.account_id);
  const stamp = Date.now();
  const contact = await api.createContact(`Agência ${stamp}`, `agencia-${stamp}@example.test`);
  const ticket = await api.createConversation(env.api_inbox_id, contact.id, `Fatura ${stamp}`);
  await api.call('post', `/conversations/${ticket.id}/toggle_status`, { status: 'on_hold' });
  await api.call('post', `/conversations/${ticket.id}/messages`, { content: 'Aguardando o hotel', private: true });

  await api.updateUISettings({ is_contact_sidebar_open: true, is_ticket_events_open: true });

  await page.goto(`/app/accounts/${env.account_id}/tickets/${ticket.id}`);
  const events = page.getByTestId('ticket-events');
  await expect(events.getByText('Ana Admin alterou Status')).toBeVisible();
  await expect(events.getByText('Novo → Em espera')).toBeVisible();
  await expect(events.getByText('Ana Admin adicionou uma nota interna')).toBeVisible();
  await expect(events.getByText(/criou o ticket/)).toBeVisible();
  await api.ctx.dispose();
});
