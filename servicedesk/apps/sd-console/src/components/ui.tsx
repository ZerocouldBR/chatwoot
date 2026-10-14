import type { ReactNode } from 'react';
import type { Capability } from '../lib/sdops';

export function Notice({ kind = 'info', children, role }: { kind?: 'info' | 'warn' | 'danger' | 'mock' | 'plain'; children: ReactNode; role?: string }) {
  return (
    <div className={`notice ${kind}`} role={role || (kind === 'danger' ? 'alert' : 'status')}>
      <span aria-hidden="true">{kind === 'danger' ? '⚠' : kind === 'warn' || kind === 'mock' ? '!' : 'i'}</span>
      <div>{children}</div>
    </div>
  );
}

export function Badge({ kind = '', children, title }: { kind?: string; children: ReactNode; title?: string }) {
  return (
    <span className={`badge ${kind}`} title={title}>
      {children}
    </span>
  );
}

export function Kpi({ label, value, hint, title }: { label: string; value: ReactNode; hint?: ReactNode; title?: string }) {
  return (
    <div className="card kpi" title={title}>
      <span className="label">{label}</span>
      <span className="value">{value}</span>
      {hint ? <span className="hint">{hint}</span> : null}
    </div>
  );
}

export function Loading({ lines = 3, label = 'Carregando' }: { lines?: number; label?: string }) {
  return (
    <div className="stack" aria-busy="true" aria-label={label}>
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="skeleton" style={{ width: `${90 - i * 15}%` }} />
      ))}
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <Notice kind="danger">
      <span>{error}</span>{' '}
      {onRetry ? (
        <button className="link" onClick={onRetry}>
          Tentar de novo
        </button>
      ) : null}
    </Notice>
  );
}

/**
 * Botão que só fica ativo se o sd-ops reportar a capacidade. Sem informação => desabilitado com
 * explicação (nunca simula sucesso).
 */
export function CapButton({
  cap,
  capName,
  children,
  onClick,
  busy,
  primary,
}: {
  cap: Capability | undefined | null;
  capName: string;
  children: ReactNode;
  onClick: () => void;
  busy?: boolean;
  primary?: boolean;
}) {
  const enabled = !!cap?.enabled;
  const why = !cap
    ? `O sd-ops não informou a capacidade "${capName}". Função desabilitada.`
    : cap.enabled
      ? cap.mode === 'mock'
        ? 'Modo MOCK (DEV): nenhuma ação real será feita.'
        : undefined
      : cap.reason || 'Função desabilitada no sd-ops.';
  const id = `why-${capName}`;
  return (
    <span className="stack" style={{ gap: 2 }}>
      <button className={primary ? 'primary' : ''} disabled={!enabled || busy} onClick={onClick} aria-describedby={why ? id : undefined}>
        {busy ? 'Aguarde…' : children}
      </button>
      {why ? (
        <span id={id} className="small muted" style={{ maxWidth: 240 }}>
          {why}
        </span>
      ) : null}
    </span>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="muted small">{children}</p>;
}
