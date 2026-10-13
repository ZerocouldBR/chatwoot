/**
 * ServiceDesk — layout "Agent Workspace" da tela do ticket.
 *
 *   [ Propriedades (300px, à esquerda) ] [ Conversa ] [ Contexto (direita) ]
 *
 * - A coluna de propriedades só existe quando há largura para as três colunas
 *   (ver minWidthFor). Abaixo disso o layout volta ao clássico: as propriedades
 *   ficam no topo do painel da direita, como antes.
 * - A coluna pode ser recolhida para um trilho estreito; a preferência é salva
 *   por usuário no localStorage (`servicedesk.ticketWorkspace:<id>`), sempre
 *   com try/catch (aba anônima, storage bloqueado: vale só para a sessão).
 * - O painel de contexto (direita) continua usando a preferência nativa
 *   `is_contact_sidebar_open` (ui_settings do usuário, salva no servidor), o
 *   mesmo botão lateral e o atalho Alt+O.
 */
import { computed, ref } from 'vue';
import { useWindowSize } from '@vueuse/core';
import { useMapGetter } from 'dashboard/composables/store';
import { useUISettings } from 'dashboard/composables/useUISettings';

export const WORKSPACE_STORAGE_PREFIX = 'servicedesk.ticketWorkspace';

// Largura mínima da janela para as três colunas.
// Layout expandido (lista oculta com o ticket aberto): barra lateral (~200) +
// propriedades (300) + conversa (>= 360) + contexto (320).
// Layout condensado: soma ainda a lista de tickets (~360).
export const WORKSPACE_MIN_WIDTH = Object.freeze({
  EXPANDED: 1200,
  CONDENSED: 1600,
});

export const DEFAULT_WORKSPACE_PREFS = Object.freeze({
  propertiesOpen: true,
});

const storageKey = userKey => `${WORKSPACE_STORAGE_PREFIX}:${userKey}`;

export const sanitizePrefs = value => {
  const prefs = { ...DEFAULT_WORKSPACE_PREFS };
  if (value && typeof value === 'object') {
    if (typeof value.propertiesOpen === 'boolean') {
      prefs.propertiesOpen = value.propertiesOpen;
    }
  }
  return prefs;
};

export const readWorkspacePrefs = userKey => {
  try {
    const raw = window.localStorage.getItem(storageKey(userKey));
    return raw ? sanitizePrefs(JSON.parse(raw)) : null;
  } catch (error) {
    // storage bloqueado ou JSON inválido: usa o padrão
    return null;
  }
};

export const writeWorkspacePrefs = (userKey, prefs) => {
  try {
    window.localStorage.setItem(
      storageKey(userKey),
      JSON.stringify(sanitizePrefs(prefs))
    );
  } catch (error) {
    // sem persistência: a preferência vale só para esta sessão
  }
};

export const minWidthFor = isOnExpandedLayout =>
  isOnExpandedLayout
    ? WORKSPACE_MIN_WIDTH.EXPANDED
    : WORKSPACE_MIN_WIDTH.CONDENSED;

// Estado compartilhado (singleton do módulo) entre a ConversationView, a
// coluna de propriedades e o painel de contexto, indexado pelo usuário.
const prefsByUser = ref({});

export function useTicketWorkspace() {
  const currentUser = useMapGetter('getCurrentUser');
  const { isOnExpandedLayout } = useUISettings();
  const { width } = useWindowSize();

  const userKey = computed(() => currentUser.value?.id ?? 'anonymous');

  const prefs = computed(() => {
    const key = userKey.value;
    if (prefsByUser.value[key]) return prefsByUser.value[key];
    return readWorkspacePrefs(key) || { ...DEFAULT_WORKSPACE_PREFS };
  });

  // Há largura para propriedades à esquerda + conversa + contexto?
  const isWorkspaceLayout = computed(
    () => width.value >= minWidthFor(isOnExpandedLayout.value)
  );
  const isPropertiesOpen = computed(() => prefs.value.propertiesOpen);

  const setPrefs = changes => {
    const next = sanitizePrefs({ ...prefs.value, ...changes });
    prefsByUser.value = { ...prefsByUser.value, [userKey.value]: next };
    writeWorkspacePrefs(userKey.value, next);
  };

  const setPropertiesOpen = value => setPrefs({ propertiesOpen: !!value });
  const toggleProperties = () => setPropertiesOpen(!isPropertiesOpen.value);

  return {
    isWorkspaceLayout,
    isPropertiesOpen,
    setPropertiesOpen,
    toggleProperties,
  };
}

// Só para testes: limpa o estado compartilhado.
export const resetWorkspaceState = () => {
  prefsByUser.value = {};
};
