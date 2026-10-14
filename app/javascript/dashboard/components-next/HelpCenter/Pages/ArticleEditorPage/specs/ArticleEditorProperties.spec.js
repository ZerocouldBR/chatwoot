import { shallowMount, flushPromises } from '@vue/test-utils';
import ArticleEditorProperties from '../ArticleEditorProperties.vue';

const getUserSegments = vi.fn();

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: key => key }),
}));

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { portalSlug: 'central-b2b' } }),
}));

vi.mock('dashboard/api/helpCenter/portals', () => ({
  default: class {
    // eslint-disable-next-line class-methods-use-this
    getUserSegments(...args) {
      return getUserSegments(...args);
    }
  },
}));

const SEGMENTS = [
  { id: 7, name: 'Usuários conectados', user_type: 'signed_in' },
  { id: 9, name: 'Agentes e administradores', user_type: 'staff' },
];

const mountProperties = article =>
  shallowMount(ArticleEditorProperties, {
    props: { article: { meta: {}, ...article } },
  });

describe('ArticleEditorProperties: visibilidade por segmento (ServiceDesk B2B)', () => {
  beforeEach(() => {
    getUserSegments.mockReset();
  });

  it('lista "Todos (público)" e os segmentos do portal, marcando o atual', async () => {
    getUserSegments.mockResolvedValue({ data: { payload: SEGMENTS } });
    const wrapper = mountProperties({ portalUserSegmentId: 7 });
    await flushPromises();

    expect(getUserSegments).toHaveBeenCalledWith('central-b2b');
    const options = wrapper.findAll('#article-visibility-select option');
    expect(options.map(option => option.text())).toEqual([
      'HELP_CENTER.EDIT_ARTICLE_PAGE.ARTICLE_PROPERTIES.VISIBILITY_PUBLIC',
      'Usuários conectados',
      'Agentes e administradores (HELP_CENTER.EDIT_ARTICLE_PAGE.ARTICLE_PROPERTIES.VISIBILITY_STAFF)',
    ]);
    expect(wrapper.find('#article-visibility-select').element.value).toBe('7');
  });

  it('emite saveSegment com o id escolhido ou null para público', async () => {
    getUserSegments.mockResolvedValue({ data: { payload: SEGMENTS } });
    const wrapper = mountProperties({ portalUserSegmentId: null });
    await flushPromises();

    const select = wrapper.find('#article-visibility-select');
    await select.setValue('9');
    await select.setValue('');
    expect(wrapper.emitted('saveSegment')).toEqual([[9], [null]]);
  });

  it('esconde o seletor quando o portal não tem segmentos ou a API falha', async () => {
    getUserSegments.mockRejectedValue(new Error('403'));
    const wrapper = mountProperties({});
    await flushPromises();
    expect(wrapper.find('[data-testid="article-visibility"]').exists()).toBe(
      false
    );
  });
});
