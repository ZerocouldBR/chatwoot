import { test, expect } from '@playwright/test';
import { ApiClient } from '@helpers/api';
import { E2E_PASSWORD, loadE2EEnv } from '@helpers/e2e-env';
import { mailbox, sendMail, waitForMail } from '@helpers/mail';
import { railsRunner } from '@helpers/rails';

type Ticket = { id: number; satisfaction: string; satisfaction_comment: string | null };

// Zendesk CSAT: an automation asks for a rating after the ticket is solved; the customer answers Good/Bad by e-mail link.
test.describe('customer satisfaction', () => {
  test.describe.configure({ timeout: 10 * 60 * 1000 });

  const env = loadE2EEnv();
  test.skip(!env.email_inbox_id, 'test mailbox not configured in tests/playwright/.env');

  const support = mailbox('SUPPORT');
  const customer = mailbox('CUSTOMER');
  let api: ApiClient;
  let automationId: number | undefined;

  test.beforeEach(async ({ baseURL }) => {
    api = await ApiClient.login(baseURL!, env.users.admin.email, E2E_PASSWORD, env.account_id);
  });

  test.afterEach(async () => {
    if (automationId) await api.call('delete', `/ticket_rules/${automationId}`);
    await api.dispose();
  });

  test('a solved ticket gets a Good/Bad survey by e-mail and the rating shows on the ticket', async ({ page }) => {
    const stamp = Date.now();
    const subject = `[E2E ${stamp}] Reembolso`;
    const since = new Date(Date.now() - 60_000);
    await sendMail(customer, { to: support.address, subject, text: `Quero o reembolso. Ref ${stamp}` });
    const ticket = await api.waitForConversation(env.email_inbox_id!, c => c.subject === subject);

    await api.call('post', `/conversations/${ticket.id}/messages`, { content: `Reembolso feito. Ref ${stamp}`, ticket_status: 'resolved' });
    const automation = await api.call<{ id: number }>('post', '/ticket_rules', {
      kind: 'automation',
      ticket_rule: {
        title: `CSAT ${stamp}`,
        conditions: {
          all: [
            { field: 'status', operator: 'is', value: 'resolved' },
            { field: 'hours_since_resolved', operator: 'greater_than', value: '1', business_hours: false },
            { field: 'satisfaction', operator: 'is', value: 'unoffered' },
          ],
          any: [],
        },
        actions: [{ field: 'request_satisfaction', value: '' }],
      },
    });
    automationId = automation.id;
    railsRunner('tests/playwright/support/run_automations.rb', {
      E2E_ACCOUNT_ID: String(env.account_id),
      E2E_TICKET_IDS: String(ticket.id),
      E2E_HOURS_AGO: '2',
    });
    expect((await api.call<Ticket>('get', `/conversations/${ticket.id}`)).satisfaction).toBe('offered');

    const survey = await waitForMail(
      customer,
      mail => (mail.subject || '').includes(String(stamp)) && /\/survey\/responses\//.test(`${mail.text}${mail.html}`),
      { since }
    );
    const surveyUrl = `${survey.text}${survey.html}`.match(/https?:\/\/[^\s"<>]+\/survey\/responses\/[0-9a-f-]+/)![0];

    await page.goto(surveyUrl);
    await page.getByTestId('good-bad-rating').getByRole('button', { name: 'Bom, estou satisfeito' }).click();
    await page.getByPlaceholder('Sua avaliação (opcional)').fill('Resolveram rápido');
    await page.getByRole('button', { name: 'Enviar avaliação' }).click();

    await expect
      .poll(async () => {
        const rated = await api.call<Ticket>('get', `/conversations/${ticket.id}`);
        return [rated.satisfaction, rated.satisfaction_comment];
      }, { timeout: 30_000 })
      .toEqual(['good', 'Resolveram rápido']);

    await api.updateUISettings({ is_contact_sidebar_open: true });
    await page.goto(`/app/accounts/${env.account_id}/tickets/${ticket.id}`);
    await expect(page.getByTestId('ticket-satisfaction')).toContainText('Boa · Resolveram rápido');
  });
});
