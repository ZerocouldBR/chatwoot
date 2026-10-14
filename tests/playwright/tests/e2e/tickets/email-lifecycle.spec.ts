import { test, expect } from '@playwright/test';
import { ApiClient } from '@helpers/api';
import { E2E_PASSWORD, loadE2EEnv } from '@helpers/e2e-env';
import { mailbox, sendMail, waitForMail } from '@helpers/mail';
import { railsRunner } from '@helpers/rails';

// Real e-mail between the customer alias and the support mailbox (IMAP polling every minute).
test.describe('e-mail tickets', () => {
  test.describe.configure({ timeout: 10 * 60 * 1000 });

  const env = loadE2EEnv();
  test.skip(!env.email_inbox_id, 'test mailbox not configured in tests/playwright/.env');

  const support = mailbox('SUPPORT');
  const customer = mailbox('CUSTOMER');
  const copied = mailbox('CUSTOMER2');
  let api: ApiClient;

  test.beforeEach(async ({ baseURL }) => {
    api = await ApiClient.login(baseURL!, env.users.admin.email, E2E_PASSWORD, env.account_id);
  });

  test.afterEach(async () => {
    await api.ctx.dispose();
  });

  test('customer e-mail opens a ticket, pending waits for the customer and the reply reopens it', async () => {
    const stamp = Date.now();
    const subject = `[E2E ${stamp}] Cartão recusado`;
    const since = new Date(Date.now() - 60_000);
    await sendMail(customer, { to: support.address, subject, text: `Olá, o cartão foi recusado. Ref ${stamp}` });

    const ticket = await api.waitForConversation(env.email_inbox_id!, c => c.subject === subject);
    expect(ticket.status).toBe('new_ticket');

    // Default triggers: the requester is told the request was received and the empty priority becomes Normal.
    await waitForMail(customer, mail => (mail.subject || '') === `[Pedido recebido] ${subject}`, { since });
    expect((await api.getConversation(Number(ticket.id))).priority).toBe('medium');

    await api.call('post', `/conversations/${ticket.id}/messages`, {
      content: `Pode nos enviar o localizador? Ref ${stamp}`,
      ticket_status: 'waiting_on_customer',
    });
    expect((await api.getConversation(Number(ticket.id))).status).toBe('waiting_on_customer');

    const agentReply = await waitForMail(
      customer,
      mail => (mail.subject || '').includes(String(stamp)) && (mail.text || '').includes('localizador'),
      { since }
    );

    await sendMail(customer, {
      to: support.address,
      subject: `Re: ${subject}`,
      text: `O localizador é ABC123. Ref ${stamp}`,
      inReplyTo: agentReply.messageId,
      references: [agentReply.messageId!],
    });

    await expect
      .poll(async () => (await api.getConversation(Number(ticket.id))).status, { timeout: 240_000, intervals: [5_000] })
      .toBe('open');
    expect((await api.listConversations(env.email_inbox_id!)).filter(c => c.subject === subject)).toHaveLength(1);
  });

  test('people copied on the e-mail become CCs and receive public replies only', async () => {
    const stamp = Date.now();
    const subject = `[E2E ${stamp}] Reserva com cópia`;
    const since = new Date(Date.now() - 60_000);
    await sendMail(customer, { to: support.address, cc: [copied.address], subject, text: `Com o gerente em cópia. Ref ${stamp}` });

    const ticket = await api.waitForConversation(env.email_inbox_id!, c => c.subject === subject);
    expect(ticket.cc_emails).toEqual([copied.address]);

    await api.call('post', `/conversations/${ticket.id}/messages`, { content: `Nota interna ${stamp}`, private: true });
    await api.call('post', `/conversations/${ticket.id}/messages`, { content: `Resposta pública ${stamp}` });

    const reply = await waitForMail(
      copied,
      mail =>
        (mail.text || '').includes(`Resposta pública ${stamp}`) &&
        JSON.stringify(mail.cc || '').includes(copied.address),
      { since }
    );
    expect(reply.subject).toContain(String(stamp));
    await expect(
      waitForMail(copied, mail => (mail.text || '').includes(`Nota interna ${stamp}`), { since, timeoutMs: 30_000 })
    ).rejects.toThrow(/no matching mail/);
  });

  test('a reply to a closed ticket opens a linked follow-up', async () => {
    const stamp = Date.now();
    const subject = `[E2E ${stamp}] Reserva cancelada`;
    const originalId = await sendMail(customer, { to: support.address, subject, text: `Reserva cancelada. Ref ${stamp}` });

    const ticket = await api.waitForConversation(env.email_inbox_id!, c => c.subject === subject);
    await api.call('post', `/conversations/${ticket.id}/toggle_status`, { status: 'resolved' });
    railsRunner('tests/playwright/support/close_solved_tickets.rb', {
      E2E_ACCOUNT_ID: String(env.account_id),
      E2E_TICKET_IDS: String(ticket.id),
    });
    expect((await api.getConversation(Number(ticket.id))).status).toBe('closed');

    await sendMail(customer, {
      to: support.address,
      subject: `Re: ${subject}`,
      text: `Preciso reabrir esse caso. Ref ${stamp}`,
      inReplyTo: originalId,
      references: [originalId],
    });

    const followup = await api.waitForConversation(env.email_inbox_id!, c => c.followup_source_id === ticket.id);
    expect(followup).toMatchObject({ status: 'new_ticket', subject });
    expect((await api.getConversation(Number(ticket.id))).status).toBe('closed');
  });
});
