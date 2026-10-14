import { test, expect } from '@playwright/test';
import { ApiClient } from '@helpers/api';
import { E2E_PASSWORD, loadE2EEnv } from '@helpers/e2e-env';

type Ticket = { id: number; status: string; labels: string[]; merged_into_id: number | null; problem_id: number | null };

// Merge, problem/incident, the trash and redaction.
test.describe('merge, problems and trash', () => {
  const env = loadE2EEnv();
  let api: ApiClient;

  test.beforeEach(async ({ baseURL }) => {
    api = await ApiClient.login(baseURL!, env.users.admin.email, E2E_PASSWORD, env.account_id);
  });

  test.afterEach(async () => {
    await api.dispose();
  });

  const ticketUrl = (id: number) => `/app/accounts/${env.account_id}/tickets/${id}`;
  const ticket = (id: number) => api.call<Ticket>('get', `/conversations/${id}`);

  test('an agent merges a ticket into another one', async ({ page }) => {
    const stamp = Date.now();
    const contact = await api.createContact(`Mescla ${stamp}`);
    const source = await api.createCustomerTicket(env.api_inbox_id, contact.id, `Duplicado ${stamp}`);
    const target = await api.createCustomerTicket(env.api_inbox_id, contact.id, `Original ${stamp}`);

    await page.goto(ticketUrl(source.id));
    await page.getByTestId('ticket-more-actions').click();
    await page.getByText('Mesclar em outro ticket').click();
    const dialog = page.getByTestId('merge-ticket-dialog');
    await dialog.getByTestId('merge-target-id').fill(String(target.id));
    await dialog.getByTestId('merge-target-id').blur();
    await expect(dialog.getByTestId('merge-target-preview')).toContainText(`Original ${stamp}`);
    await page.getByRole('button', { name: 'Mesclar', exact: true }).click();

    await expect(page).toHaveURL(new RegExp(`/tickets/${target.id}`));
    const merged = await ticket(source.id);
    expect(merged).toMatchObject({ status: 'closed', merged_into_id: target.id });
    expect(merged.labels).toContain('closed_by_merge');

    await page.goto(ticketUrl(source.id));
    await expect(page.getByTestId('merged-into-link')).toHaveText(`Mesclado no #${target.id}`);
  });

  test('solving a problem solves its incidents with the same reply', async ({ page }) => {
    const stamp = Date.now();
    const contact = await api.createContact(`Problema ${stamp}`);
    const problem = await api.createCustomerTicket(env.api_inbox_id, contact.id, `Fora do ar ${stamp}`);
    const incident = await api.createCustomerTicket(env.api_inbox_id, contact.id, `Não consigo entrar ${stamp}`);
    await api.call('patch', `/conversations/${problem.id}`, { ticket_type: 'problem' });
    await api.call('patch', `/conversations/${incident.id}`, { ticket_type: 'incident' });
    await api.updateUISettings({ is_contact_sidebar_open: true });

    await page.goto(ticketUrl(incident.id));
    await page.getByTestId('ticket-problem').fill(String(problem.id));
    await page.getByTestId('ticket-problem').press('Enter');
    await expect.poll(async () => (await ticket(incident.id)).problem_id).toBe(problem.id);

    await api.call('post', `/conversations/${problem.id}/messages`, { content: `Sistema normalizado ${stamp}` });
    await api.call('post', `/conversations/${problem.id}/toggle_status`, { status: 'resolved' });

    await expect.poll(async () => (await ticket(incident.id)).status, { timeout: 30_000 }).toBe('resolved');
    await page.goto(ticketUrl(incident.id));
    await expect(page.locator('[id^=message]').getByText(`Sistema normalizado ${stamp}`)).toBeVisible();
  });

  test('deleted tickets can be restored from the trash', async ({ page }) => {
    const stamp = Date.now();
    const contact = await api.createContact(`Lixeira ${stamp}`);
    const deleted = await api.createCustomerTicket(env.api_inbox_id, contact.id, `Apagar ${stamp}`);
    await expect.poll(async () => (await ticket(deleted.id)).status).toBeTruthy();
    await api.call('delete', `/conversations/${deleted.id}`);
    await expect(ticket(deleted.id)).rejects.toThrow(/404/);

    await page.goto(`/app/accounts/${env.account_id}/deleted-tickets`);
    const item = page.getByTestId('ticket-queue-item').filter({ hasText: `#${deleted.id}` });
    await item.getByRole('button', { name: 'Restaurar' }).click();
    await expect(page.getByText('Ticket restaurado')).toBeVisible();
    expect((await ticket(deleted.id)).status).toBeTruthy();
  });

  test('an admin redacts a card number from a comment', async ({ page }) => {
    const stamp = Date.now();
    const contact = await api.createContact(`Redação ${stamp}`);
    const redacted = await api.createCustomerTicket(env.api_inbox_id, contact.id, `Meu cartão é 4111 1111 1111 1111 ref ${stamp}`);

    await page.goto(ticketUrl(redacted.id));
    await page.locator('[id^=message]').getByText(`ref ${stamp}`).click({ button: 'right' });
    await page.getByTestId('message-redact').click();
    await page.getByTestId('redact-text').fill('4111 1111 1111 1111');
    await page.getByRole('button', { name: 'Redigir', exact: true }).click();

    await expect(page.locator('[id^=message]').getByText(`Meu cartão é ${'▇'.repeat(19)} ref ${stamp}`)).toBeVisible();
    expect((await ticket(redacted.id)).labels).toContain('redacted_content');
  });
});
