<script setup>
// ServiceDesk: selo da trava "envio externo bloqueado" (conta isolada), só para administradores.
import { computed } from 'vue';
import { useAccount } from 'dashboard/composables/useAccount';
import { useAdmin } from 'dashboard/composables/useAdmin';
import Banner from 'dashboard/components-next/banner/Banner.vue';

const { currentAccount } = useAccount();
const { isAdmin } = useAdmin();

const isOutboundBlocked = computed(
  () => currentAccount.value?.servicedesk?.outbound_blocked === true
);
</script>

<!-- eslint-disable-next-line vue/no-root-v-if -->
<template>
  <Banner
    v-if="isAdmin && isOutboundBlocked"
    color="amber"
    role="status"
    data-testid="outbound-blocked-banner"
    class="!rounded-none !justify-center flex-wrap shrink-0"
  >
    {{ $t('SD_OUTBOUND_GUARD.BANNER') }}
  </Banner>
</template>
