import fs from 'fs';
import path from 'path';

export const AUTH_DIR = path.resolve(__dirname, '../.auth');
export const STORAGE_STATE = path.join(AUTH_DIR, 'admin.json');
export const ENV_FILE = path.join(AUTH_DIR, 'e2e.json');

export const E2E_PASSWORD = process.env.E2E_PASSWORD || 'E2e!Tickets2026';

export type E2EUser = { id: number; email: string; name: string };
export type E2EEnv = {
  account_id: number;
  api_inbox_id: number;
  users: { admin: E2EUser; agent: E2EUser };
};

export function loadE2EEnv(): E2EEnv {
  return JSON.parse(fs.readFileSync(ENV_FILE, 'utf8')) as E2EEnv;
}
