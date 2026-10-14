import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { applyTheme } from './lib/chatwoot';
import './theme.css';

applyTheme(new URLSearchParams(window.location.search).get('theme') || undefined);
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
