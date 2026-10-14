import { test, expect } from '@playwright/test';
import { ApiClient } from '@helpers/api';
import { E2E_PASSWORD, loadE2EEnv } from '@helpers/e2e-env';

type Schedule = {
  id: number;
  name: string;
  intervals: Array<{ day: number; start: number; end: number }>;
  holidays: Array<{ name: string }>;
};

// Admins define business hours and holidays used by SLA targets and business-hours rules.
test('admin creates a schedule with Saturday hours and a holiday', async ({ page, baseURL }) => {
  const env = loadE2EEnv();
  const api = await ApiClient.login(baseURL!, env.users.admin.email, E2E_PASSWORD, env.account_id);
  const name = `Comercial ${Date.now()}`;

  await page.goto(`/app/accounts/${env.account_id}/settings/business-hours`);
  await page.getByRole('button', { name: 'Novo horário' }).click();
  const form = page.getByTestId('business-schedule-form');
  await page.getByTestId('schedule-name').fill(name);
  await page.getByTestId('schedule-day-6').getByRole('button', { name: 'Adicionar horário' }).click();
  await form.getByRole('button', { name: 'Adicionar feriado' }).click();
  await form.getByPlaceholder('Nome do feriado').fill('Natal');
  await form.getByLabel('Início').fill('2026-12-25');
  await form.getByLabel('Fim').fill('2026-12-25');
  await form.getByRole('button', { name: 'Salvar' }).click();
  await expect(page.getByText('Horário salvo')).toBeVisible();

  const { payload } = await api.call<{ payload: Schedule[] }>('get', '/business_schedules');
  const schedule = payload.find(item => item.name === name)!;
  expect(schedule.intervals).toContainEqual({ day: 6, start: 540, end: 1080 });
  expect(schedule.intervals.filter(interval => interval.day >= 1 && interval.day <= 5)).toHaveLength(5);
  expect(schedule.holidays.map(holiday => holiday.name)).toEqual(['Natal']);

  await api.call('delete', `/business_schedules/${schedule.id}`);
  await api.ctx.dispose();
});
