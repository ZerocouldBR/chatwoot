import { test, expect } from '@playwright/test';
import { ApiClient } from '@helpers/api';
import { E2E_PASSWORD, loadE2EEnv } from '@helpers/e2e-env';

// Subject, type and due date edited from the ticket properties panel.
test('agent edits subject, type and due date of a ticket', async ({ page, baseURL }) => {
  const env = loadE2EEnv();
  const api = await ApiClient.login(baseURL!, env.users.admin.email, E2E_PASSWORD, env.account_id);
  const stamp = Date.now();
  const contact = await api.createContact(`Hotel ${stamp}`, `hotel-${stamp}@example.test`);
  const ticket = await api.createConversation(env.api_inbox_id, contact.id, `Reserva ${stamp} não confirmada`);

  // Chat tickets are named after the first message.
  await expect.poll(async () => (await api.getConversation(ticket.id)).subject).toBe(`Reserva ${stamp} não confirmada`);

  await page.goto(`/app/accounts/${env.account_id}/tickets/${ticket.id}`);
  const subject = page.getByTestId('ticket-subject');
  await subject.fill(`Cancelamento ${stamp}`);
  await subject.press('Enter');
  await expect(page.locator('.conversation--header--actions').getByText(`Cancelamento ${stamp}`)).toBeVisible();

  await page.getByTestId('ticket-type').click();
  await page.getByRole('button', { name: 'Tarefa' }).click();
  await page.getByTestId('ticket-due-date').fill('2030-05-20');
  await page.getByTestId('ticket-due-date').blur();

  await expect
    .poll(async () => {
      const current = await api.getConversation(ticket.id);
      return [current.subject, current.ticket_type, current.due_at ? new Date(Number(current.due_at) * 1000).toISOString().slice(0, 10) : null];
    })
    .toEqual([`Cancelamento ${stamp}`, 'task', '2030-05-20']);
  await api.ctx.dispose();
});
