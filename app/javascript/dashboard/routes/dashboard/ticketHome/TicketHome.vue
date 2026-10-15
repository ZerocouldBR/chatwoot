<script setup>
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import TicketHomeAPI from 'dashboard/api/ticketHome';
import { dynamicTime } from 'shared/helpers/timeHelper';
import CardStatusIcon from 'dashboard/components-next/Conversation/ConversationCard/CardStatusIcon.vue';
import Avatar from 'next/avatar/Avatar.vue';
import Button from 'dashboard/components-next/button/Button.vue';

const route = useRoute();
const router = useRouter();

const SECTIONS = [
  {
    title: 'TICKET_HOME.YOUR_WORK',
    views: [{ id: 'mine', icon: 'i-lucide-ticket' }],
  },
  {
    title: 'TICKET_HOME.SHARED_WORK',
    views: [
      { id: 'ccs', icon: 'i-lucide-user-plus' },
      { id: 'following', icon: 'i-lucide-users' },
    ],
  },
  {
    title: 'TICKET_HOME.DONE_WORK',
    views: [{ id: 'solved', icon: 'i-lucide-package-check' }],
  },
];

const activeView = ref('mine');
const tickets = ref([]);
const counts = ref({});
const page = ref(1);
const totalPages = ref(1);
const isLoading = ref(false);
const stats = ref(null);

const loadView = async ({ append = false } = {}) => {
  isLoading.value = true;
  try {
    const { data } = await TicketHomeAPI.getView({
      view: activeView.value,
      page: page.value,
    });
    tickets.value = append ? [...tickets.value, ...data.payload] : data.payload;
    counts.value = data.meta.counts;
    totalPages.value = data.meta.total_pages;
  } finally {
    isLoading.value = false;
  }
};

const selectView = view => {
  activeView.value = view;
  page.value = 1;
  loadView();
};

const loadMore = () => {
  page.value += 1;
  loadView({ append: true });
};

const openTicket = id => {
  router.push({
    name: 'inbox_conversation',
    params: { accountId: route.params.accountId, conversation_id: id },
  });
};

const lastMessage = ticket => ticket.messages?.[0]?.content || '';

const hasMore = computed(() => page.value < totalPages.value);

onMounted(async () => {
  loadView();
  const { data } = await TicketHomeAPI.getStats();
  stats.value = data;
});
</script>

<template>
  <div
    class="flex w-full h-full overflow-hidden bg-n-background"
    data-testid="ticket-home"
  >
    <nav class="flex flex-col gap-5 p-4 border-e border-n-weak w-60 shrink-0">
      <h1 class="text-heading-2 text-n-slate-12">
        {{ $t('TICKET_HOME.TITLE') }}
      </h1>
      <div
        v-for="section in SECTIONS"
        :key="section.title"
        class="flex flex-col gap-1"
      >
        <span class="text-xs font-medium text-n-slate-11">
          {{ $t(section.title) }}
        </span>
        <button
          v-for="view in section.views"
          :key="view.id"
          type="button"
          :data-testid="`home-view-${view.id}`"
          class="flex items-center justify-between gap-2 px-2 py-1.5 text-sm rounded-lg text-n-slate-12"
          :class="
            activeView === view.id
              ? 'bg-n-alpha-2 font-medium'
              : 'hover:bg-n-alpha-1'
          "
          @click="selectView(view.id)"
        >
          <span class="flex items-center gap-2">
            <span :class="view.icon" class="size-4" />
            {{ $t(`TICKET_HOME.VIEWS.${view.id}`) }}
          </span>
          <span class="text-xs text-n-slate-11">{{
            counts[view.id] ?? ''
          }}</span>
        </button>
      </div>
    </nav>

    <section class="flex flex-col flex-1 min-w-0 overflow-y-auto">
      <header class="px-5 py-4 border-b border-n-weak">
        <h2 class="text-heading-3 text-n-slate-12">
          {{
            $t('TICKET_HOME.TICKETS_COUNT', { count: counts[activeView] ?? 0 })
          }}
        </h2>
      </header>
      <p
        v-if="!isLoading && !tickets.length"
        class="p-5 text-sm text-n-slate-11"
      >
        {{ $t('TICKET_HOME.EMPTY') }}
      </p>
      <button
        v-for="ticket in tickets"
        :key="ticket.id"
        type="button"
        data-testid="home-ticket"
        class="flex gap-3 px-5 py-3 text-start border-b border-n-weak hover:bg-n-alpha-1"
        @click="openTicket(ticket.id)"
      >
        <Avatar
          :name="ticket.meta?.sender?.name"
          :src="ticket.meta?.sender?.thumbnail"
          :size="32"
          rounded-full
        />
        <span class="flex flex-col flex-1 min-w-0 gap-0.5">
          <span class="text-sm truncate text-n-slate-12">
            <span class="font-medium">{{ ticket.meta?.sender?.name }}</span>
            <span class="text-n-slate-11"> | </span>
            <span class="font-medium">{{ ticket.subject }}</span>
          </span>
          <span class="flex items-center gap-2 text-sm text-n-slate-11">
            <CardStatusIcon :status="ticket.status" />
            <span>{{ $t(`CONVERSATION.TICKET_STATUS.${ticket.status}`) }}</span>
            <span class="truncate">{{ lastMessage(ticket) }}</span>
          </span>
          <span class="text-xs text-n-slate-10">
            {{ dynamicTime(ticket.timestamp) }} | #{{ ticket.id }}
          </span>
        </span>
      </button>
      <div v-if="hasMore" class="p-4">
        <Button
          :label="$t('TICKET_HOME.LOAD_MORE')"
          :is-loading="isLoading"
          slate
          sm
          @click="loadMore"
        />
      </div>
    </section>

    <aside
      v-if="stats"
      class="flex flex-col gap-4 p-4 overflow-y-auto border-s border-n-weak w-80 shrink-0"
      data-testid="home-stats"
    >
      <div
        class="flex flex-col gap-3 p-4 rounded-xl outline outline-1 outline-n-container"
      >
        <div>
          <h3 class="text-sm font-medium text-n-slate-12">
            {{ $t('TICKET_HOME.STATS.TICKET_TITLE') }}
          </h3>
          <span class="text-xs text-n-slate-11">
            {{ $t('TICKET_HOME.STATS.THIS_WEEK') }}
          </span>
        </div>
        <div class="grid grid-cols-3 text-center">
          <div v-for="key in ['good', 'bad', 'solved']" :key="key">
            <div class="text-lg font-medium text-n-blue-11">
              {{ stats.week[key] }}
            </div>
            <div class="text-xs text-n-slate-11">
              {{ $t(`TICKET_HOME.STATS.${key.toUpperCase()}`) }}
            </div>
          </div>
        </div>
      </div>

      <div
        class="flex flex-col gap-3 p-4 rounded-xl outline outline-1 outline-n-container"
      >
        <div>
          <h3 class="text-sm font-medium text-n-slate-12">
            {{ $t('TICKET_HOME.STATS.SATISFACTION_TITLE') }}
          </h3>
          <span class="text-xs text-n-slate-11">
            {{ $t('TICKET_HOME.STATS.LAST_60_DAYS') }}
          </span>
        </div>
        <div class="grid grid-cols-2 text-center">
          <div v-for="key in ['you', 'support']" :key="key">
            <div class="text-lg font-medium text-n-slate-12">
              {{
                stats.satisfaction[key] === null
                  ? $t('TICKET_HOME.STATS.NO_RATINGS')
                  : `${stats.satisfaction[key]}%`
              }}
            </div>
            <div class="text-xs text-n-slate-11">
              {{ $t(`TICKET_HOME.STATS.${key.toUpperCase()}`) }}
            </div>
          </div>
        </div>
      </div>

      <div
        class="flex flex-col gap-1 p-4 text-center rounded-xl outline outline-1 outline-n-container"
      >
        <h3 class="text-sm font-medium text-start text-n-slate-12">
          {{ $t('TICKET_HOME.STATS.OPEN_TITLE') }}
        </h3>
        <div class="text-lg font-medium text-n-blue-11">
          {{ stats.group_open_tickets }}
        </div>
        <div class="text-xs text-n-slate-11">
          {{ $t('TICKET_HOME.STATS.YOUR_GROUPS') }}
        </div>
      </div>

      <div
        class="flex flex-col gap-3 p-4 rounded-xl outline outline-1 outline-n-container"
      >
        <h3 class="text-sm font-medium text-n-slate-12">
          {{ $t('TICKET_HOME.STATS.UPDATES_TITLE') }}
        </h3>
        <p v-if="!stats.updates.length" class="text-sm text-n-slate-11">
          {{ $t('TICKET_HOME.STATS.NO_UPDATES') }}
        </p>
        <button
          v-for="update in stats.updates"
          :key="update.id"
          type="button"
          class="flex flex-col gap-0.5 px-2 py-1.5 -mx-2 rounded-lg text-start hover:bg-n-alpha-1"
          @click="openTicket(update.ticket_id)"
        >
          <span class="text-sm text-n-slate-12">
            {{
              $t(
                update.event_type === 'comment'
                  ? 'TICKET_HOME.STATS.COMMENTED'
                  : 'TICKET_HOME.STATS.CHANGED',
                {
                  author: update.author_name || $t('TICKET_HOME.STATS.SOMEONE'),
                  subject: update.subject || `#${update.ticket_id}`,
                }
              )
            }}
          </span>
          <span class="text-xs text-n-slate-10">
            {{ dynamicTime(update.created_at) }}
          </span>
        </button>
      </div>
    </aside>
  </div>
</template>
