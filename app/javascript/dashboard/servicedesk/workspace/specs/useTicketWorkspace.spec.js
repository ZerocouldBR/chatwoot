import { ref } from 'vue';
import {
  DEFAULT_WORKSPACE_PREFS,
  WORKSPACE_MIN_WIDTH,
  minWidthFor,
  readWorkspacePrefs,
  resetWorkspaceState,
  sanitizePrefs,
  useTicketWorkspace,
  writeWorkspacePrefs,
} from '../useTicketWorkspace';

const currentUser = ref({ id: 42 });
const isOnExpandedLayout = ref(true);
const width = ref(1440);

vi.mock('dashboard/composables/store', async () => {
  const { computed } = await import('vue');
  return { useMapGetter: () => computed(() => currentUser.value) };
});
vi.mock('dashboard/composables/useUISettings', () => ({
  useUISettings: () => ({ isOnExpandedLayout }),
}));
vi.mock('@vueuse/core', () => ({ useWindowSize: () => ({ width }) }));

describe('useTicketWorkspace', () => {
  beforeEach(() => {
    window.localStorage.clear();
    resetWorkspaceState();
    currentUser.value = { id: 42 };
    isOnExpandedLayout.value = true;
    width.value = 1440;
    vi.restoreAllMocks();
  });

  it('sanitiza preferências inválidas', () => {
    expect(sanitizePrefs(null)).toEqual(DEFAULT_WORKSPACE_PREFS);
    expect(sanitizePrefs({ propertiesOpen: 'x' })).toEqual(
      DEFAULT_WORKSPACE_PREFS
    );
    expect(sanitizePrefs({ propertiesOpen: false, other: 1 })).toEqual({
      propertiesOpen: false,
    });
  });

  it('lê e grava por usuário no localStorage', () => {
    writeWorkspacePrefs(7, { propertiesOpen: false });
    expect(window.localStorage.getItem('servicedesk.ticketWorkspace:7')).toBe(
      '{"propertiesOpen":false}'
    );
    expect(readWorkspacePrefs(7)).toEqual({ propertiesOpen: false });
    expect(readWorkspacePrefs(8)).toBeNull();
  });

  it('não quebra com storage bloqueado ou JSON inválido', () => {
    window.localStorage.setItem('servicedesk.ticketWorkspace:9', '{oops');
    expect(readWorkspacePrefs(9)).toBeNull();
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError');
    });
    expect(readWorkspacePrefs(1)).toBeNull();
    expect(() =>
      writeWorkspacePrefs(1, { propertiesOpen: false })
    ).not.toThrow();
    const { isPropertiesOpen, toggleProperties } = useTicketWorkspace();
    toggleProperties();
    expect(isPropertiesOpen.value).toBe(false); // vale para a sessão
  });

  it('só usa três colunas quando há largura (expandido x condensado)', () => {
    expect(minWidthFor(true)).toBe(WORKSPACE_MIN_WIDTH.EXPANDED);
    expect(minWidthFor(false)).toBe(WORKSPACE_MIN_WIDTH.CONDENSED);
    const { isWorkspaceLayout } = useTicketWorkspace();
    expect(isWorkspaceLayout.value).toBe(true);
    width.value = 1100;
    expect(isWorkspaceLayout.value).toBe(false);
    width.value = 1440;
    isOnExpandedLayout.value = false;
    expect(isWorkspaceLayout.value).toBe(false);
    width.value = 1920;
    expect(isWorkspaceLayout.value).toBe(true);
  });

  it('recolhe/expande e persiste a preferência do usuário', () => {
    const first = useTicketWorkspace();
    expect(first.isPropertiesOpen.value).toBe(true);
    first.toggleProperties();
    expect(first.isPropertiesOpen.value).toBe(false);
    expect(readWorkspacePrefs(42)).toEqual({ propertiesOpen: false });
    // outra instância (ex.: painel de contexto) vê o mesmo estado
    expect(useTicketWorkspace().isPropertiesOpen.value).toBe(false);
    // outro usuário tem a própria preferência
    currentUser.value = { id: 43 };
    expect(first.isPropertiesOpen.value).toBe(true);
  });

  it('restaura a preferência salva ao recarregar', () => {
    writeWorkspacePrefs(42, { propertiesOpen: false });
    expect(useTicketWorkspace().isPropertiesOpen.value).toBe(false);
  });
});
