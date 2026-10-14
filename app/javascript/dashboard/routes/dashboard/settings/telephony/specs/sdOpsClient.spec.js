import { createSdOpsClient, resetSession, SdOpsError } from '../sdOpsClient';

const json = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  json: () => Promise.resolve(body),
});

describe('sdOpsClient (mesmo domínio, sessão do sd-ops só em memória)', () => {
  let calls;
  beforeEach(() => {
    resetSession();
    calls = [];
    global.fetch = vi.fn((url, init) => {
      calls.push({ url, init });
      if (url.endsWith('/auth/session'))
        return Promise.resolve(
          json(200, { session_token: `s${calls.length}` })
        );
      return Promise.resolve(json(200, { ok: true }));
    });
  });

  const client = () =>
    createSdOpsClient({
      getAccessToken: () => 'token-pessoal-ficticio',
      getAccountId: () => 4,
    });

  it('cria a sessão com o token do usuário e usa Bearer nas chamadas', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    await client().getSettings();
    expect(calls[0].url).toBe('/sd-ops/api/v1/auth/session');
    expect(JSON.parse(calls[0].init.body)).toEqual({
      chatwoot_token: 'token-pessoal-ficticio',
      account_id: 4,
    });
    expect(calls[1].url).toBe('/sd-ops/api/v1/admin/settings');
    expect(calls[1].init.headers.Authorization).toBe('Bearer s1');
    expect(setItem).not.toHaveBeenCalled();
    // a sessão é reaproveitada
    await client().saveSettings({ values: {} });
    expect(calls).toHaveLength(3);
    expect(calls[2].init.method).toBe('PUT');
  });

  it('sessão expirada (401): cria outra e repete uma vez', async () => {
    let first = true;
    global.fetch = vi.fn((url, init) => {
      calls.push({ url, init });
      if (url.endsWith('/auth/session'))
        return Promise.resolve(
          json(200, { session_token: `s${calls.length}` })
        );
      if (first) {
        first = false;
        return Promise.resolve(json(401, { error: 'session_expired' }));
      }
      return Promise.resolve(json(200, { items: [] }));
    });
    const r = await client().testSettings();
    expect(r).toEqual({ items: [] });
    expect(calls.map(c => c.url.split('/').pop())).toEqual([
      'session',
      'test',
      'session',
      'test',
    ]);
  });

  it('erro do servidor vira SdOpsError com código e campos', async () => {
    global.fetch = vi.fn(url =>
      Promise.resolve(
        url.endsWith('/auth/session')
          ? json(200, { session_token: 's' })
          : json(422, {
              error: 'validation',
              message: 'há campos inválidos',
              fields: { a: 'x' },
            })
      )
    );
    await expect(client().saveSettings({})).rejects.toMatchObject({
      status: 422,
      code: 'validation',
      extra: { fields: { a: 'x' } },
    });
    global.fetch = vi.fn(() => Promise.reject(new Error('offline')));
    resetSession();
    await expect(client().getSettings()).rejects.toBeInstanceOf(SdOpsError);
  });
});
