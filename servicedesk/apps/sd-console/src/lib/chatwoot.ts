/**
 * Contexto do Dashboard App do Chatwoot (documentação oficial "How to use Dashboard Apps" e
 * app/javascript/dashboard/components/widgets/DashboardApp/Frame.vue do fork):
 * - o app pede o contexto com window.parent.postMessage('chatwoot-dashboard-app:fetch-info', '*');
 * - o Chatwoot responde com postMessage(JSON.stringify({event: 'appContext', data: {conversation,
 *   contact, currentAgent, customAttributes?, theme?}}), '*') ao carregar, ao abrir a aba e ao trocar o tema.
 * O contexto vem do navegador e NÃO prova identidade (CTI_AUTH.md): serve só para saber qual
 * conversa/contato mostrar; toda autorização é do sd-ops/qa-pipeline no servidor.
 */
import { useEffect, useState } from 'react';

export const FETCH_INFO = 'chatwoot-dashboard-app:fetch-info';

export interface AppContext {
  conversation?: {
    id?: number;
    account_id?: number;
    inbox_id?: number;
    status?: string;
    custom_attributes?: Record<string, unknown>;
    additional_attributes?: Record<string, unknown>;
    meta?: { sender?: { id?: number; name?: string; phone_number?: string; email?: string }; assignee?: { name?: string } };
  };
  contact?: { id?: number; name?: string; phone_number?: string; email?: string; custom_attributes?: Record<string, unknown> };
  currentAgent?: { id?: number; name?: string; email?: string };
  theme?: 'dark' | 'light';
}

/** Origens aceitas (separadas por vírgula) em VITE_CHATWOOT_ORIGINS; vazio = mesma origem e localhost. */
export function originAllowed(origin: string, allowed = (import.meta.env.VITE_CHATWOOT_ORIGINS as string) || ''): boolean {
  const list = allowed.split(',').map((s) => s.trim()).filter(Boolean);
  if (list.length === 0) {
    return origin === window.location.origin || /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin);
  }
  return list.includes(origin) || list.includes('*');
}

export function parseContextMessage(data: unknown): AppContext | null {
  if (typeof data !== 'string') return null;
  try {
    const msg = JSON.parse(data);
    if (msg && msg.event === 'appContext' && msg.data && typeof msg.data === 'object') return msg.data as AppContext;
  } catch {
    /* não é mensagem do Chatwoot */
  }
  return null;
}

export function applyTheme(theme?: string) {
  const dark = theme ? theme === 'dark' : window.matchMedia?.('(prefers-color-scheme: dark)').matches;
  document.documentElement.classList.toggle('dark', !!dark);
}

export function useAppContext(): { ctx: AppContext | null; embedded: boolean } {
  const embedded = typeof window !== 'undefined' && window.parent !== window;
  const [ctx, setCtx] = useState<AppContext | null>(null);
  useEffect(() => {
    function onMessage(ev: MessageEvent) {
      if (!originAllowed(ev.origin)) return;
      const c = parseContextMessage(ev.data);
      if (c) {
        setCtx(c);
        if (c.theme) applyTheme(c.theme);
      }
    }
    window.addEventListener('message', onMessage);
    if (embedded) window.parent.postMessage(FETCH_INFO, '*');
    return () => window.removeEventListener('message', onMessage);
  }, [embedded]);
  return { ctx, embedded };
}
