import { execSync } from 'child_process';
import path from 'path';

const REPO_ROOT = path.resolve(__dirname, '../../..');

// Runs a Ruby script (path relative to the repo root) through `rails runner`.
// RAILS_RUNNER_CMD lets the same suite drive a remote environment, e.g.
// `ssh servicedesk-dev "cd /opt/servicedesk-dev && ./dev.sh rails runner"`.
export function railsRunner<T>(script: string, env: Record<string, string> = {}): T {
  const runner = process.env.RAILS_RUNNER_CMD || 'bundle exec rails runner';
  const output = execSync(`${runner} ${script}`, {
    cwd: REPO_ROOT,
    env: { ...process.env, ...env },
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'inherit'],
  });
  const line = output.split('\n').find(l => l.startsWith('E2E_JSON:'));
  if (!line) throw new Error(`rails runner produced no E2E_JSON line:\n${output}`);
  return JSON.parse(line.slice('E2E_JSON:'.length)) as T;
}
