import { defineConfig, devices } from '@playwright/test';

import dotenv from 'dotenv';
import path from 'path';
dotenv.config({ path: path.resolve(__dirname, '.env') });

export default defineConfig({
  testDir: './tests',
  globalSetup: require.resolve('./global-setup'),
  timeout: 60 * 1000,
  expect: {
    timeout: 30 * 1000,
  },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    actionTimeout: 30 * 1000,
    navigationTimeout: 30 * 1000,
    baseURL: process.env.BASE_URL || 'http://localhost:3000',
    trace: 'retain-on-failure',
    headless: !process.env.HEADED,
    viewport: {
      width: 1440,
      height: 1080,
    },
  },

  projects: [
    {
      name: 'chromium',
      testIgnore: /e2e\/tickets\//,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'tickets',
      testMatch: /e2e\/tickets\/.*\.spec\.ts/,
      use: { ...devices['Desktop Chrome'], storageState: '.auth/admin.json' },
    },
  ],
});
