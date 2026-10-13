<script setup>
import { computed } from 'vue';
import { useStore } from 'vuex';
import SignupForm from './components/Signup/Form.vue';
import { useBranding } from 'shared/composables/useBranding';
import signupBg from 'assets/images/auth/signup-bg.jpg';

const props = defineProps({
  shopifyPendingInstall: {
    type: String,
    default: '',
  },
});

const store = useStore();
const { replaceInstallationName } = useBranding();

const globalConfig = computed(() => store.getters['globalConfig/get']);
const isShopifySignup = computed(() => Boolean(props.shopifyPendingInstall));
const loginRoute = computed(() => {
  const route = { name: 'login' };
  if (!isShopifySignup.value) return route;

  const redirectUrl = `settings/integrations/shopify?shopify_pending_install=${props.shopifyPendingInstall}`;
  return { ...route, query: { redirect_url: redirectUrl } };
});
</script>

<template>
  <div
    class="relative w-full h-full min-h-screen flex items-center justify-center bg-cover bg-center bg-no-repeat p-4"
    :style="{ backgroundImage: `url(${signupBg})` }"
  >
    <div
      class="absolute inset-0 bg-n-gray-12/60 dark:bg-n-gray-1/80 backdrop-blur-sm"
    />
    <div
      class="relative flex max-w-[960px] bg-white dark:bg-n-solid-2 rounded-lg outline outline-1 outline-n-container shadow-sm"
    >
      <div class="flex-1 flex items-center justify-center py-10 px-10">
        <div class="max-w-[420px] w-full">
          <div class="mb-6">
            <img
              :src="globalConfig.logo"
              :alt="globalConfig.installationName"
              class="block w-auto h-7 dark:hidden"
            />
            <img
              v-if="globalConfig.logoDark"
              :src="globalConfig.logoDark"
              :alt="globalConfig.installationName"
              class="hidden w-auto h-7 dark:block"
            />
            <h2 class="mt-6 text-2xl font-semibold text-n-slate-12">
              {{
                isShopifySignup
                  ? replaceInstallationName($t('REGISTER.SHOPIFY.TITLE'))
                  : $t('REGISTER.TRY_WOOT')
              }}
            </h2>
            <p v-if="isShopifySignup" class="mt-2 text-sm text-n-slate-11">
              {{ replaceInstallationName($t('REGISTER.SHOPIFY.DESCRIPTION')) }}
            </p>
            <p class="mt-2 text-sm text-n-slate-11">
              {{ $t('REGISTER.HAVE_AN_ACCOUNT') }}{{ ' '
              }}<router-link
                class="text-n-blue-10 font-medium hover:text-n-blue-11"
                :to="loginRoute"
              >
                {{ $t('LOGIN.SUBMIT') }}
              </router-link>
            </p>
          </div>
          <SignupForm :shopify-pending-install="shopifyPendingInstall" />
        </div>
      </div>
    </div>
  </div>
</template>
