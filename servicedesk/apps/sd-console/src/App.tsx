import { lazy, Suspense, useState } from 'react';
import { BrowserRouter, Navigate, NavLink, Route, Routes } from 'react-router-dom';
import { SessionGate, useSession } from './components/Session';
import { Loading } from './components/ui';
import { applyTheme } from './lib/chatwoot';
import Cti from './pages/Cti';

const QaConsole = lazy(() => import('./pages/QaConsole'));
const QaEvaluation = lazy(() => import('./pages/QaEvaluation'));
const Dashboards = lazy(() => import('./pages/Dashboards'));

function TopBar() {
  const { me, logout } = useSession();
  const [dark, setDark] = useState(document.documentElement.classList.contains('dark'));
  return (
    <header className="topbar">
      <a className="brand" href="/">ServiceDesk</a>
      <nav aria-label="Principal">
        <NavLink to="/qa">Qualidade</NavLink>
        <NavLink to="/dash">Dashboards</NavLink>
      </nav>
      <span className="spacer" />
      <button
        className="link"
        aria-pressed={dark}
        onClick={() => {
          applyTheme(dark ? 'light' : 'dark');
          setDark(!dark);
        }}
      >
        {dark ? 'Tema claro' : 'Tema escuro'}
      </button>
      <span className="small muted">{me.name}</span>
      <button className="link" onClick={logout}>Sair</button>
    </header>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const account = new URLSearchParams(window.location.search).get('account_id') || (import.meta.env.VITE_CHATWOOT_ACCOUNT_ID as string) || '';
  return (
    <SessionGate accountId={account}>
      <div className="app">
        <TopBar />
        <Suspense fallback={<div className="main"><Loading /></div>}>{children}</Suspense>
      </div>
    </SessionGate>
  );
}

export default function App() {
  return (
    <BrowserRouter basename="/sd-console">
      <Routes>
        <Route path="/cti" element={<Cti />} />
        <Route path="/qa" element={<Shell><QaConsole /></Shell>} />
        <Route path="/qa/avaliacoes/:id" element={<Shell><QaEvaluation /></Shell>} />
        <Route path="/dash" element={<Shell><Dashboards /></Shell>} />
        <Route path="*" element={<Navigate to="/dash" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
