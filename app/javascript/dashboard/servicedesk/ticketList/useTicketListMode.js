import { ref, computed } from 'vue';
import { useMapGetter } from 'dashboard/composables/store';

export const TICKET_LIST_MODES = Object.freeze({
  LIST: 'list',
  TABLE: 'table',
});

const STORAGE_PREFIX = 'servicedesk.ticketListMode';
const VALID_MODES = Object.values(TICKET_LIST_MODES);

// Estado compartilhado entre o botao do cabecalho e a ChatList (singleton do
// modulo), indexado pelo id do usuario logado.
const modeByUser = ref({});

const storageKey = userKey => `${STORAGE_PREFIX}:${userKey}`;

export const readStoredMode = userKey => {
  try {
    const value = window.localStorage.getItem(storageKey(userKey));
    return VALID_MODES.includes(value) ? value : null;
  } catch (error) {
    // localStorage pode estar bloqueado (aba anonima, politica do navegador).
    return null;
  }
};

export const writeStoredMode = (userKey, mode) => {
  try {
    window.localStorage.setItem(storageKey(userKey), mode);
  } catch (error) {
    // Sem persistencia: a preferencia vale apenas para esta sessao.
  }
};

/**
 * Preferencia "lista" x "tabela" da lista de tickets, salva por usuario no
 * localStorage (com try/catch). Padrao: lista (comportamento original).
 */
export function useTicketListMode() {
  const currentUser = useMapGetter('getCurrentUser');
  const userKey = computed(() => currentUser.value?.id ?? 'anonymous');

  const mode = computed(() => {
    const key = userKey.value;
    if (modeByUser.value[key]) return modeByUser.value[key];
    return readStoredMode(key) || TICKET_LIST_MODES.LIST;
  });

  const isTableMode = computed(() => mode.value === TICKET_LIST_MODES.TABLE);

  const setMode = newMode => {
    if (!VALID_MODES.includes(newMode)) return;
    modeByUser.value = { ...modeByUser.value, [userKey.value]: newMode };
    writeStoredMode(userKey.value, newMode);
  };

  return { mode, isTableMode, setMode };
}
