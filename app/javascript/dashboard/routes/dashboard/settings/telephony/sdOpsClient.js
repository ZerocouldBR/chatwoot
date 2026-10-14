// ServiceDesk: cliente do sd-ops para a tela Configurações > Telefonia 55PBX.
//
// Mesmo domínio (/sd-ops/... pela rota do Traefik), sem proxy no Rails: a sessão do sd-ops é criada com o token de
// acesso do próprio usuário logado (o mesmo fluxo do CTI, docs/integrations/CTI_AUTH.md). O sd-ops valida o token no
// GET /api/v1/profile real do Chatwoot e só libera a configuração para o administrator da conta. O token de sessão
// fica SÓ em memória (nunca localStorage) e vai no header Authorization (Bearer), então não há CSRF por cookie.

const BASE = '/sd-ops/api/v1';

let session = null; // { token, accountId }

export class SdOpsError extends Error {
  constructor(status, code, message, extra = {}) {
    super(message || code);
    this.status = status;
    this.code = code;
    this.extra = extra;
  }
}

async function request(path, { method = 'GET', body, token } = {}) {
  const headers = { Accept: 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let res;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      credentials: 'same-origin',
    });
  } catch {
    throw new SdOpsError(0, 'network', '');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new SdOpsError(
      res.status,
      data.error || `http_${res.status}`,
      data.message || '',
      data
    );
  }
  return data;
}

export async function openSession({ accessToken, accountId }) {
  if (!accessToken) throw new SdOpsError(401, 'no_access_token', '');
  const data = await request('/auth/session', {
    method: 'POST',
    body: { chatwoot_token: accessToken, account_id: Number(accountId) },
  });
  session = { token: data.session_token, accountId: Number(accountId) };
  return data;
}

export function resetSession() {
  session = null;
}

export function hasSession() {
  return !!session;
}

export function createSdOpsClient({ getAccessToken, getAccountId }) {
  async function call(path, opts = {}, retry = true) {
    const accountId = Number(getAccountId());
    if (!session || session.accountId !== accountId) {
      await openSession({ accessToken: getAccessToken(), accountId });
    }
    try {
      return await request(path, { ...opts, token: session.token });
    } catch (e) {
      // sessão do sd-ops expirada (30 min ociosa / 8 h): uma nova, com o token do usuário, e repete uma vez
      if (e.status === 401 && retry) {
        session = null;
        return call(path, opts, false);
      }
      throw e;
    }
  }

  return {
    getSettings: () => call('/admin/settings'),
    saveSettings: payload =>
      call('/admin/settings', { method: 'PUT', body: payload }),
    testSettings: payload =>
      call('/admin/settings/test', { method: 'POST', body: payload }),
    rotateWebhookSecret: () =>
      call('/admin/settings/webhook-secret', { method: 'POST' }),
  };
}
