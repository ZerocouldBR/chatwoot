import { ref } from 'vue';
import { mount } from '@vue/test-utils';
import OutboundBlockedBanner from '../OutboundBlockedBanner.vue';

const currentAccount = ref({});
const isAdmin = ref(true);

vi.mock('dashboard/composables/useAccount', () => ({
  useAccount: () => ({ currentAccount }),
}));
vi.mock('dashboard/composables/useAdmin', () => ({
  useAdmin: () => ({ isAdmin }),
}));

const render = () =>
  mount(OutboundBlockedBanner, {
    global: { mocks: { $t: key => key } },
  });

describe('OutboundBlockedBanner', () => {
  it('shows the isolated account badge to administrators', () => {
    currentAccount.value = { servicedesk: { outbound_blocked: true } };
    isAdmin.value = true;

    const wrapper = render();

    expect(
      wrapper.find('[data-testid="outbound-blocked-banner"]').exists()
    ).toBe(true);
    expect(wrapper.text()).toContain('SD_OUTBOUND_GUARD.BANNER');
  });

  it('is hidden for agents', () => {
    currentAccount.value = { servicedesk: { outbound_blocked: true } };
    isAdmin.value = false;

    expect(
      render().find('[data-testid="outbound-blocked-banner"]').exists()
    ).toBe(false);
  });

  it('is hidden when the account sends normally', () => {
    currentAccount.value = { servicedesk: { outbound_blocked: false } };
    isAdmin.value = true;

    expect(
      render().find('[data-testid="outbound-blocked-banner"]').exists()
    ).toBe(false);
  });
});
