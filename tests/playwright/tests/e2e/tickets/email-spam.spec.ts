import { test, expect } from '@playwright/test';
import { ApiClient } from '@helpers/api';
import { E2E_PASSWORD, loadE2EEnv } from '@helpers/e2e-env';
import { mailbox, sendMail } from '@helpers/mail';

type Suspended = { id: number; subject: string; reason: string };

// Spam blocks the requester; their next e-mail is held as a suspended ticket until an agent recovers it.
test.describe('spam and suspended tickets', () => {
  test.describe.configure({ timeout: 10 * 60 * 1000 });

  const env = loadE2EEnv();
  test.skip(!env.email_inbox_id, 'test mailbox not configured in tests/playwright/.env');

  const support = mailbox('SUPPORT');
  const spammer = mailbox('CUSTOMER2');
  let api: ApiClient;
  let contactId: number | undefined;

  test.beforeEach(async ({ baseURL }) => {
    api = await ApiClient.login(baseURL!, env.users.admin.email, E2E_PASSWORD, env.account_id);
  });

  test.afterEach(async () => {
    if (contactId) await api.call('put', `/contacts/${contactId}`, { blocked: false });
    await api.dispose();
  });

  test('marking a ticket as spam suspends the next e-mail, which can be recovered', async ({ page }) => {
    const stamp = Date.now();
    const subject = `[E2E ${stamp}] Promoção imperdível`;
    await sendMail(spammer, { to: support.address, subject, text: `Compre agora. Ref ${stamp}` });
    const ticket = await api.waitForConversation(env.email_inbox_id!, c => c.subject === subject);
    contactId = (ticket.meta as { sender: { id: number } }).sender.id;

    await page.goto(`/app/accounts/${env.account_id}/tickets/${ticket.id}`);
    await page.getByTestId('ticket-more-actions').click();
    await page.getByRole('menuitem', { name: 'Marcar como spam' }).or(page.locator('button:not(dialog button)', { hasText: 'Marcar como spam' })).first().click();
    await page.locator('dialog[open]').getByRole('button', { name: 'Marcar como spam' }).click();
    await expect(page.getByText('Ticket marcado como spam')).toBeVisible();

    const second = `[E2E ${stamp}] Última chance`;
    await sendMail(spammer, { to: support.address, subject: second, text: `De novo. Ref ${stamp}` });
    let held: Suspended | undefined;
    await expect
      .poll(
        async () => {
          const { payload } = await api.call<{ payload: Suspended[] }>('get', '/suspended_tickets');
          held = payload.find(item => item.subject === second);
          return held?.reason;
        },
        { timeout: 240_000, intervals: [10_000] }
      )
      .toBe('blocked_sender');
    expect((await api.listConversations(env.email_inbox_id!)).some(c => c.subject === second)).toBe(false);

    await page.goto(`/app/accounts/${env.account_id}/suspended-tickets`);
    await page.getByTestId('ticket-queue-item').filter({ hasText: second }).getByRole('button', { name: 'Recuperar' }).click();
    await expect(page.getByText('E-mail recuperado')).toBeVisible();
    await api.waitForConversation(env.email_inbox_id!, c => c.subject === second, { timeoutMs: 60_000 });
  });
});
