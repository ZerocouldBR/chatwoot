/**
 * Porta de autenticação (CTI_AUTH.md): tenta a sessão existente (cookie same-site) com /auth/me;
 * senão pede o "Token de acesso" do Chatwoot (Perfil > Token de acesso), troca por sessão curta no
 * sd-ops e guarda o session_token SÓ EM MEMÓRIA. O token do Chatwoot é descartado logo após o uso.
 */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { errorText, onUnauthorized, setSession } from '../lib/http';
import * as sdops from '../lib/sdops';
import { ErrorBox, Loading, Notice } from './ui';

interface SessionValue {
  me: sdops.Me;
  isManager: boolean;
  has: (...roles: sdops.Role[]) => boolean;
  logout: () => void;
}
const Ctx = createContext<SessionValue | null>(null);

export function useSession(): SessionValue {
  const v = useContext(Ctx);
  if (!v) throw new Error('useSession fora de <SessionGate>');
  return v;
}

export function SessionGate({ accountId, children }: { accountId?: number | string; children: ReactNode }) {
  const [me, setMe] = useState<sdops.Me | null>(null);
  const [state, setState] = useState<'checking' | 'login' | 'ready' | 'error'>('checking');
  const [error, setError] = useState('');
  const [token, setToken] = useState('');
  const [account, setAccount] = useState(String(accountId ?? ''));
  const [busy, setBusy] = useState(false);

  const check = useCallback(async () => {
    setState('checking');
    try {
      setMe(await sdops.me());
      setState('ready');
    } catch (e) {
      const msg = errorText(e);
      if (msg.startsWith('Sessão')) setState('login');
      else {
        setError(msg);
        setState('error');
      }
    }
  }, []);

  useEffect(() => {
    check();
    const off = onUnauthorized(() => setState('login'));
    return () => {
      off();
    };
  }, [check]);
  useEffect(() => {
    if (accountId !== undefined && accountId !== null) setAccount(String(accountId));
  }, [accountId]);

  async function login(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const s = await sdops.createSession(token.trim(), account.trim());
      setSession(s.session_token, s.csrf_token || null);
      setToken('');
      await check();
    } catch (err) {
      setError(errorText(err).replace('Sessão expirada ou inválida. Entre novamente.', 'Token do Chatwoot inválido.'));
    } finally {
      setBusy(false);
    }
  }

  if (state === 'checking') return <div className="main"><Loading label="Verificando sessão" /></div>;
  if (state === 'error')
    return (
      <div className="main">
        <ErrorBox error={`Não foi possível falar com o sd-ops: ${error}`} onRetry={check} />
      </div>
    );
  if (state === 'login' || !me)
    return (
      <div className="main" style={{ maxWidth: 480 }}>
        <form className="card" onSubmit={login} aria-labelledby="login-title">
          <h1 id="login-title">Entrar no ServiceDesk CTI</h1>
          <p className="muted small">
            Cole o seu <strong>Token de acesso</strong> do ServiceDesk (Perfil &gt; Token de acesso). Ele é validado no
            servidor e trocado por uma sessão de 30 minutos; não fica salvo neste navegador.
          </p>
          <label>
            Token de acesso
            <input type="password" autoComplete="off" required value={token} onChange={(e) => setToken(e.target.value)} />
          </label>
          <label>
            Conta (ID)
            <input inputMode="numeric" required value={account} onChange={(e) => setAccount(e.target.value)} />
          </label>
          {error ? <Notice kind="danger">{error}</Notice> : null}
          <div className="row">
            <button className="primary" type="submit" disabled={busy}>
              {busy ? 'Validando…' : 'Entrar'}
            </button>
          </div>
        </form>
      </div>
    );

  const has = (...roles: sdops.Role[]) => me.roles.includes('admin') || roles.some((r) => me.roles.includes(r));
  const value: SessionValue = {
    me,
    isManager: has('supervisor', 'qa'),
    has,
    logout: () => {
      sdops.logout();
      setSession(null);
      setMe(null);
      setState('login');
    },
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
