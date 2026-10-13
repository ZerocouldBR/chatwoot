import fs from 'fs';
import { FullConfig } from '@playwright/test';
import { railsRunner } from './helpers/rails';
import { ApiClient } from './helpers/api';
import { AUTH_DIR, E2E_PASSWORD, E2EEnv, ENV_FILE, STORAGE_STATE } from './helpers/e2e-env';

// Prepares the isolated "E2E Tickets" account and a logged-in admin storage state.
export default async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0].use.baseURL as string;
  const env = railsRunner<E2EEnv>('tests/playwright/support/setup_e2e_account.rb', { E2E_PASSWORD });
  fs.mkdirSync(AUTH_DIR, { recursive: true });
  fs.writeFileSync(ENV_FILE, JSON.stringify(env, null, 2));

  const api = await ApiClient.login(baseURL, env.users.admin.email, E2E_PASSWORD, env.account_id);
  const { hostname } = new URL(baseURL);
  fs.writeFileSync(
    STORAGE_STATE,
    JSON.stringify({
      cookies: [
        {
          name: 'cw_d_session_info',
          value: encodeURIComponent(api.sessionCookieValue()),
          domain: hostname,
          path: '/',
          expires: Number(api.auth.expiry),
          httpOnly: false,
          secure: false,
          sameSite: 'Lax',
        },
      ],
      origins: [],
    })
  );
  await api.ctx.dispose();
}
