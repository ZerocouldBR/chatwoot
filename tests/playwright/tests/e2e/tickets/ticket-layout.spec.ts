import { test, expect } from '@playwright/test';
import { ApiClient } from '@helpers/api';
import { E2E_PASSWORD, loadE2EEnv } from '@helpers/e2e-env';

// Zendesk-like ticket screen: properties on the left, subject and channel in the header, customer on the right,
// "Apply macro" and "Submit as" in the footer; views list tickets by subject, the menu has no channel list and
// notifications sit behind a bell.
test('the ticket screen follows the Zendesk layout', async ({ page, baseURL }) => {
  const env = loadE2EEnv();
  const api = await ApiClient.login(baseURL!, env.users.admin.email, E2E_PASSWORD, env.account_id);
  const stamp = Date.now();
  const contact = await api.createContact(`Layout ${stamp}`, `layout-${stamp}@example.test`);
  const ticket = await api.createCustomerTicket(env.api_inbox_id, contact.id, `Assunto do layout ${stamp}`);
  const macroName = `Macro ${stamp}`;
  await api.call('post', '/macros', {
    name: macroName,
    visibility: 'global',
    actions: [{ action_name: 'add_label', action_params: [`macro${stamp}`] }],
  });
  await api.updateUISettings({ is_contact_sidebar_open: true });

  await page.goto(`/app/accounts/${env.account_id}/tickets/${ticket.id}`);
  const header = page.getByTestId('ticket-header');
  await expect(header.getByTestId('ticket-header-subject')).toHaveText(`Assunto do layout ${stamp}`);
  await expect(header).toContainText(`Ticket #${ticket.id}`);
  await expect(header.getByTestId('ticket-header-channel')).toHaveText('Pela API');
  await expect(page.getByTestId('ticket-properties').getByTestId('ticket-requester')).toContainText(`layout-${stamp}@example.test`);
  await expect(page.getByRole('button', { name: /^Enviar como Novo/ })).toBeVisible();

  await page.getByTestId('apply-macro').getByRole('button', { name: 'Aplicar macro' }).click();
  await page.getByTestId('apply-macro').getByText(macroName).click();
  await expect.poll(async () => (await api.getConversation(ticket.id)).labels).toContain(`macro${stamp}`);

  await page.goto(`/app/accounts/${env.account_id}/dashboard`);
  await page.getByRole('tab', { name: /Todos/ }).or(page.getByText(/^Todos\s*\d+$/)).first().click();
  await expect(page.getByTestId('ticket-list-subject').filter({ hasText: `Assunto do layout ${stamp}` })).toBeVisible();
  await expect(page.getByText('Página inicial', { exact: true })).toBeVisible();
  await expect(page.getByText('Caixa de Entrada', { exact: true })).toBeHidden();
  await expect(page.getByText('Canais', { exact: true })).toBeHidden();
  await page.getByTestId('notifications-bell').click();
  await expect(page.getByTestId('notifications-panel')).toContainText('Notificações');
  // The panel is wider than the sidebar: it must open outside it, without scrolling the menu sideways.
  expect(await page.locator('aside').first().evaluate(el => el.scrollLeft)).toBe(0);
  await api.dispose();
});
