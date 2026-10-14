<script setup>
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useStore, useMapGetter } from 'dashboard/composables/store';
import { dynamicTime } from 'shared/helpers/timeHelper';
import { frontendURL, conversationUrl } from 'dashboard/helper/URLHelper';
import Button from 'dashboard/components-next/button/Button.vue';
import TeleportWithDirection from 'dashboard/components-next/TeleportWithDirection.vue';
import Spinner from 'dashboard/components-next/spinner/Spinner.vue';

// Agent notifications behind a bell (Zendesk), instead of a separate inbox page in the menu.
defineProps({
  collapsed: {
    type: Boolean,
    default: false,
  },
});

const PAGE_SIZE = 15;

const store = useStore();
const router = useRouter();
const accountId = useMapGetter('getCurrentAccountId');
const unreadCount = useMapGetter('notifications/getUnreadCount');
const uiFlags = useMapGetter('notifications/getUIFlags');
const getNotifications = useMapGetter(
  'notifications/getFilteredNotificationsV4'
);
const isOpen = ref(false);

const notifications = computed(() =>
  getNotifications.value({ sortOrder: 'desc' }).slice(0, PAGE_SIZE)
);
const badge = computed(() =>
  unreadCount.value > 99 ? '99+' : unreadCount.value
);

const toggle = () => {
  isOpen.value = !isOpen.value;
  if (isOpen.value)
    store.dispatch('notifications/index', { page: 1, sortOrder: 'desc' });
};

const open = async notification => {
  isOpen.value = false;
  const { id, primaryActorId, primaryActorType, primaryActor } = notification;
  if (!notification.readAt) {
    await store.dispatch('notifications/read', {
      id,
      primaryActorId,
      primaryActorType,
      unreadCount: unreadCount.value,
    });
  }
  router.push(
    frontendURL(
      conversationUrl({ accountId: accountId.value, id: primaryActor.id })
    )
  );
};

const readAll = () => store.dispatch('notifications/readAll');

onMounted(() => store.dispatch('notifications/unReadCount'));
</script>

<template>
  <div class="relative">
    <Button
      data-testid="notifications-bell"
      icon="i-lucide-bell"
      color="slate"
      size="sm"
      :aria-label="$t('NOTIFICATIONS_BELL.TITLE')"
      class="relative dark:hover:!bg-n-slate-9/30"
      :class="
        collapsed
          ? '!size-8 !outline-n-weak !text-n-slate-11'
          : '!h-7 !outline-n-weak !text-n-slate-11'
      "
      @click="toggle"
    />
    <span
      v-if="unreadCount"
      data-testid="notifications-badge"
      class="absolute -top-1.5 -end-1.5 min-w-4 h-4 px-1 rounded-full bg-n-ruby-9 text-white text-[0.625rem] leading-4 text-center pointer-events-none"
    >
      {{ badge }}
    </span>
    <!-- Teleported: the panel is wider than the sidebar and must not make it scroll sideways. -->
    <TeleportWithDirection to="body">
      <div v-if="isOpen" class="fixed inset-0 z-50" @click="isOpen = false" />
      <div
        v-if="isOpen"
        data-testid="notifications-panel"
        class="fixed z-50 overflow-hidden border shadow-xl top-14 start-3 w-80 rounded-xl border-n-weak bg-n-solid-2"
      >
        <header
          class="flex items-center justify-between px-4 py-3 border-b border-n-weak"
        >
          <span class="text-sm font-medium text-n-slate-12">
            {{ $t('NOTIFICATIONS_BELL.TITLE') }}
          </span>
          <Button
            v-if="unreadCount"
            :label="$t('NOTIFICATIONS_BELL.READ_ALL')"
            link
            xs
            @click="readAll"
          />
        </header>
        <div
          v-if="uiFlags.isFetching && !notifications.length"
          class="flex justify-center py-6"
        >
          <Spinner />
        </div>
        <p
          v-else-if="!notifications.length"
          class="px-4 py-6 text-sm text-center text-n-slate-11"
        >
          {{ $t('NOTIFICATIONS_BELL.EMPTY') }}
        </p>
        <ul class="overflow-y-auto max-h-96">
          <li v-for="notification in notifications" :key="notification.id">
            <button
              type="button"
              class="flex flex-col w-full gap-0.5 px-4 py-2.5 text-start hover:bg-n-alpha-1"
              @click="open(notification)"
            >
              <span class="flex items-center gap-2 text-sm text-n-slate-12">
                <span
                  v-if="!notification.readAt"
                  class="rounded-full shrink-0 size-2 bg-n-brand"
                />
                <span class="line-clamp-2">{{
                  notification.pushMessageTitle
                }}</span>
              </span>
              <span class="text-xs text-n-slate-11">
                {{ dynamicTime(notification.lastActivityAt) }}
              </span>
            </button>
          </li>
        </ul>
      </div>
    </TeleportWithDirection>
  </div>
</template>
