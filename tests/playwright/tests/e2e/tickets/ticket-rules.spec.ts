import { test, expect } from '@playwright/test';
import { ApiClient } from '@helpers/api';
import { E2E_PASSWORD, loadE2EEnv } from '@helpers/e2e-env';
import { railsRunner } from '@helpers/rails';

type Rule = { id: number; title: string };
type TicketEvent = { via: string; field_name: string | null; value: unknown; author: { name: string | null } };

// Triggers (on every update, in order) and automations (hourly, time-based), Zendesk style.
test.describe('triggers and automations', () => {
  const env = loadE2EEnv();
  let api: ApiClient;
  const created: number[] = [];

  test.beforeEach(async ({ baseURL }) => {
    api = await ApiClient.login(baseURL!, env.users.admin.email, E2E_PASSWORD, env.account_id);
  });

  test.afterEach(async () => {
    while (created.length) await api.call('delete', `/ticket_rules/${created.pop()}`);
    await api.dispose();
  });

  test('a trigger made in settings raises the priority of tickets tagged vip', async ({ page }) => {
    const stamp = Date.now();
    const tag = `vip${stamp}`;
    const title = `VIP ${stamp}`;

    await page.goto(`/app/accounts/${env.account_id}/settings/triggers`);
    await expect(page.getByText('Notificar solicitante e CCs sobre pedido recebido')).toBeVisible();
    await page.getByRole('button', { name: 'Novo gatilho' }).click();
    const form = page.getByTestId('ticket-rule-form');
    await form.getByTestId('rule-title').fill(title);
    const condition = form.getByTestId('rule-condition').first();
    await condition.getByTestId('rule-condition-field').selectOption('labels');
    await condition.getByTestId('rule-value').fill(tag);
    const action = form.getByTestId('rule-action').first();
    await action.getByTestId('rule-action-field').selectOption('priority');
    await action.getByTestId('rule-value').selectOption('urgent');
    await form.getByRole('button', { name: 'Salvar' }).click();
    await expect(page.getByText('Salvo')).toBeVisible();

    const { payload } = await api.call<{ payload: Rule[] }>('get', '/ticket_rules?kind=trigger');
    created.push(payload.find(rule => rule.title === title)!.id);

    const contact = await api.createContact(`Regras ${stamp}`);
    const ticket = await api.createCustomerTicket(env.api_inbox_id, contact.id, `Preciso de ajuda ${stamp}`);
    await expect.poll(async () => (await api.getConversation(ticket.id)).priority, { timeout: 30_000 }).toBe('medium');

    await api.call('post', `/conversations/${ticket.id}/labels`, { labels: [tag] });
    await expect.poll(async () => (await api.getConversation(ticket.id)).priority, { timeout: 30_000 }).toBe('urgent');

    const events = await api.call<{ payload: TicketEvent[] }>('get', `/conversations/${ticket.id}/events`);
    const byRule = events.payload.filter(event => event.via === 'rule' && event.field_name === 'priority');
    expect(byRule.map(event => [event.author.name, event.value])).toEqual([
      [title, 'urgent'],
      ['Definir prioridade Normal quando vazia', 'medium'],
    ]);
  });

  test('a trigger replies in the ticket channel with placeholders', async ({ page }) => {
    const stamp = Date.now();
    const title = `Auto resposta ${stamp}`;
    const tag = `auto${stamp}`;

    await page.goto(`/app/accounts/${env.account_id}/settings/triggers`);
    await page.getByRole('button', { name: 'Novo gatilho' }).click();
    const form = page.getByTestId('ticket-rule-form');
    await form.getByTestId('rule-title').fill(title);
    const condition = form.getByTestId('rule-condition').first();
    await condition.getByTestId('rule-condition-field').selectOption('labels');
    await condition.getByTestId('rule-value').fill(tag);
    const action = form.getByTestId('rule-action').first();
    await action.getByTestId('rule-action-field').selectOption('send_message');
    await action.getByTestId('rule-value').fill('Recebemos o ticket #{{ticket.id}}, já vamos responder.');
    await form.getByRole('button', { name: 'Salvar' }).click();
    await expect(page.getByText('Salvo')).toBeVisible();
    const { payload } = await api.call<{ payload: Rule[] }>('get', '/ticket_rules?kind=trigger');
    created.push(payload.find(rule => rule.title === title)!.id);

    const contact = await api.createContact(`Auto ${stamp}`);
    const ticket = await api.createCustomerTicket(env.api_inbox_id, contact.id, `Olá ${stamp}`);
    await api.call('post', `/conversations/${ticket.id}/labels`, { labels: [tag] });

    await page.goto(`/app/accounts/${env.account_id}/tickets/${ticket.id}`);
    await expect(page.locator('[id^=message]').getByText(`Recebemos o ticket #${ticket.id}, já vamos responder.`)).toBeVisible({
      timeout: 30_000,
    });
  });

  test('an automation puts tickets pending for too long on hold', async ({ page }) => {
    const stamp = Date.now();
    const tag = `sem_resposta${stamp}`;
    const automation = await api.call<Rule>('post', '/ticket_rules', {
      kind: 'automation',
      ticket_rule: {
        title: `Sem resposta ${stamp}`,
        conditions: {
          all: [
            { field: 'status', operator: 'is', value: 'waiting_on_customer' },
            { field: 'hours_since_waiting_on_customer', operator: 'greater_than', value: '1', business_hours: false },
          ],
          any: [],
        },
        actions: [
          { field: 'status', value: 'on_hold' },
          { field: 'add_tags', value: tag },
        ],
      },
    });
    created.push(automation.id);

    const contact = await api.createContact(`Automação ${stamp}`);
    const waiting = await api.createCustomerTicket(env.api_inbox_id, contact.id, `Aguardando ${stamp}`);
    const fresh = await api.createCustomerTicket(env.api_inbox_id, contact.id, `Recente ${stamp}`);
    for (const ticket of [waiting, fresh]) {
      await api.call('post', `/conversations/${ticket.id}/toggle_status`, { status: 'waiting_on_customer' });
    }

    const result = railsRunner<Record<string, { status: string; labels: string[] }>>('tests/playwright/support/run_automations.rb', {
      E2E_ACCOUNT_ID: String(env.account_id),
      E2E_TICKET_IDS: String(waiting.id),
      E2E_HOURS_AGO: '2',
    });
    expect(result[waiting.id]).toEqual({ status: 'on_hold', labels: [tag] });
    expect((await api.getConversation(fresh.id)).status).toBe('waiting_on_customer');

    await page.goto(`/app/accounts/${env.account_id}/settings/automations`);
    await expect(page.getByText(`Sem resposta ${stamp}`)).toBeVisible();
    await expect(page.getByText('Lembrete de pendente após 24 horas')).toBeVisible();
  });
});
