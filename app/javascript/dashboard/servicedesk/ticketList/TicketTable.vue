<script setup>
import { ref, computed, inject, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useNow } from '@vueuse/core';
import { useStore, useMapGetter } from 'dashboard/composables/store';
import { useUISettings } from 'dashboard/composables/useUISettings';
import { frontendURL, conversationUrl } from 'dashboard/helper/URLHelper';
import { dynamicTime, shortTimestamp } from 'shared/helpers/timeHelper';
import { useExactTimestamp } from 'shared/composables/useExactTimestamp';
import wootConstants from 'dashboard/constants/globals';

import Checkbox from 'dashboard/components-next/checkbox/Checkbox.vue';
import Avatar from 'next/avatar/Avatar.vue';
import Icon from 'dashboard/components-next/icon/Icon.vue';
import Spinner from 'dashboard/components-next/spinner/Spinner.vue';
import InboxName from 'dashboard/components-next/Conversation/InboxName.vue';
import CardPriorityIcon from 'dashboard/components-next/Conversation/ConversationCard/CardPriorityIcon.vue';
import IntersectionObserver from 'dashboard/components/IntersectionObserver.vue';
import TicketStatusBadge from './TicketStatusBadge.vue';

import {
  TICKET_COLUMNS,
  SORT_DIRECTION,
  SERVER_SORT_BY_COLUMN,
  isServerSortColumn,
  serverSortToColumn,
  getTicketSubject,
  getTicketRequester,
  getTicketOrganization,
  getTicketStatus,
  statusCategoryRank,
  priorityRank,
  sortRows,
  rangeBetween,
} from './ticketTableHelpers';

const props = defineProps({
  conversationList: { type: Array, default: () => [] },
  isLoading: { type: Boolean, default: false },
  showEndOfListMessage: { type: Boolean, default: false },
  allConversationsSelected: { type: Boolean, default: false },
  label: { type: String, default: '' },
  teamId: { type: [String, Number], default: 0 },
  foldersId: { type: [String, Number], default: 0 },
  conversationType: { type: String, default: '' },
});

const emit = defineEmits(['loadMore', 'selectAll', 'sortChange']);

const store = useStore();
const router = useRouter();
const { t } = useI18n();
const { updateUISettings } = useUISettings();
const exactTimestamp = useExactTimestamp();
// Atualiza a coluna "Atualizado" a cada minuto.
const now = useNow({ interval: 60000 });

// Fornecidos pela ChatList (mesmas funcoes usadas pelos cards da lista).
const selectConversation = inject('selectConversation');
const deSelectConversation = inject('deSelectConversation');
const isConversationSelected = inject('isConversationSelected');

const accountId = useMapGetter('getCurrentAccountId');
const activeInbox = useMapGetter('getSelectedInbox');
const chatSortFilter = useMapGetter('getChatSortFilter');
const chatStatusFilter = useMapGetter('getChatStatusFilter');
const selectedIds = useMapGetter('bulkActions/getSelectedConversationIds');

const scrollContainerRef = ref(null);
const clientSort = ref(null);
const lastToggledIndex = ref(null);
const shiftPressed = ref(false);

const COLUMNS = [
  { key: TICKET_COLUMNS.NUMBER, i18n: 'NUMBER', width: 'w-24' },
  { key: TICKET_COLUMNS.SUBJECT, i18n: 'SUBJECT', width: 'w-auto' },
  { key: TICKET_COLUMNS.REQUESTER, i18n: 'REQUESTER', width: 'w-44' },
  { key: TICKET_COLUMNS.ORGANIZATION, i18n: 'ORGANIZATION', width: 'w-40' },
  { key: TICKET_COLUMNS.STATUS, i18n: 'STATUS', width: 'w-44' },
  { key: TICKET_COLUMNS.PRIORITY, i18n: 'PRIORITY', width: 'w-28' },
  { key: TICKET_COLUMNS.GROUP, i18n: 'GROUP', width: 'w-36' },
  { key: TICKET_COLUMNS.ASSIGNEE, i18n: 'ASSIGNEE', width: 'w-40' },
  { key: TICKET_COLUMNS.UPDATED, i18n: 'UPDATED', width: 'w-28' },
  { key: TICKET_COLUMNS.CHANNEL, i18n: 'CHANNEL', width: 'w-40' },
];

const PRIORITY_LABEL_KEYS = {
  urgent: 'CONVERSATION.PRIORITY.OPTIONS.URGENT',
  high: 'CONVERSATION.PRIORITY.OPTIONS.HIGH',
  medium: 'CONVERSATION.PRIORITY.OPTIONS.MEDIUM',
  low: 'CONVERSATION.PRIORITY.OPTIONS.LOW',
};

const buildRow = chat => {
  const meta = chat.meta || {};
  const senderId = meta.sender?.id;
  const storeContact = senderId
    ? store.getters['contacts/getContact'](senderId)
    : null;
  const requester = getTicketRequester(chat, storeContact);
  const inbox = chat.inbox_id
    ? store.getters['inboxes/getInbox'](chat.inbox_id) || {}
    : {};
  return {
    id: chat.id,
    chat,
    subject: getTicketSubject(chat),
    requester,
    organization: getTicketOrganization(chat, requester),
    status: getTicketStatus(chat),
    priority: chat.priority || '',
    teamName: meta.team?.name || '',
    assignee: meta.assignee || null,
    inbox,
    updatedAt: chat.last_activity_at || chat.timestamp || 0,
    isUnread: (chat.unread_count || 0) > 0,
  };
};

const sortValue = (row, column) => {
  switch (column) {
    case TICKET_COLUMNS.NUMBER:
      return Number(row.id) || 0;
    case TICKET_COLUMNS.SUBJECT:
      return row.subject.text;
    case TICKET_COLUMNS.REQUESTER:
      return row.requester.name || row.requester.email || '';
    case TICKET_COLUMNS.ORGANIZATION:
      return row.organization;
    case TICKET_COLUMNS.STATUS:
      // Categoria (novo > aberto > pendente > em espera > resolvido) e rotulo.
      return `${statusCategoryRank(row.status.category)}-${
        row.status.label || row.status.nativeStatus
      }`;
    case TICKET_COLUMNS.PRIORITY:
      return priorityRank(row.priority) || '';
    case TICKET_COLUMNS.GROUP:
      return row.teamName;
    case TICKET_COLUMNS.ASSIGNEE:
      return row.assignee?.name || '';
    case TICKET_COLUMNS.UPDATED:
      return row.updatedAt;
    case TICKET_COLUMNS.CHANNEL:
      return row.inbox.name || '';
    default:
      return '';
  }
};

const activeSort = computed(
  () => clientSort.value || serverSortToColumn(chatSortFilter.value)
);

const rows = computed(() => {
  const built = props.conversationList.map(buildRow);
  if (!clientSort.value) return built;
  return sortRows(
    built,
    clientSort.value.column,
    clientSort.value.direction,
    sortValue
  );
});

// Se o sort mudar pelo menu do cabecalho, a ordem do servidor volta a valer.
watch(chatSortFilter, () => {
  clientSort.value = null;
});

// Nova lista (troca de aba/filtro): zera a ancora do shift+clique.
watch(
  () => props.conversationList.length === 0,
  isEmpty => {
    if (isEmpty) lastToggledIndex.value = null;
  }
);

const ariaSort = column => {
  if (activeSort.value?.column !== column) return 'none';
  return activeSort.value.direction === SORT_DIRECTION.ASC
    ? 'ascending'
    : 'descending';
};

const sortIcon = column => {
  if (activeSort.value?.column !== column) return 'i-lucide-arrow-up-down';
  return activeSort.value.direction === SORT_DIRECTION.ASC
    ? 'i-lucide-arrow-up'
    : 'i-lucide-arrow-down';
};

const sortHint = column =>
  isServerSortColumn(column)
    ? t('SD_TICKET_TABLE.SORT.SERVER_HINT')
    : t('SD_TICKET_TABLE.SORT.CLIENT_HINT');

const onSortColumn = column => {
  const current = activeSort.value;
  const isServer = isServerSortColumn(column);
  let direction;
  if (current?.column === column) {
    direction =
      current.direction === SORT_DIRECTION.ASC
        ? SORT_DIRECTION.DESC
        : SORT_DIRECTION.ASC;
  } else {
    // Datas/numero/prioridade comecam do mais recente/maior; textos de A-Z.
    direction = isServer ? SORT_DIRECTION.DESC : SORT_DIRECTION.ASC;
  }

  if (!isServer) {
    clientSort.value = { column, direction };
    return;
  }

  const sortBy = SERVER_SORT_BY_COLUMN[column][direction];
  clientSort.value = null;
  if (sortBy === chatSortFilter.value) return;
  // Mesmo fluxo do menu "Ordenar" (ConversationBasicFilter).
  store.dispatch('setChatSortFilter', sortBy);
  updateUISettings({
    conversations_filter_by: {
      status: chatStatusFilter.value || wootConstants.STATUS_TYPE.OPEN,
      order_by: sortBy,
    },
  });
  emit('sortChange', sortBy);
};

// ---- Selecao (integrada as acoes em massa existentes) ----
const isSelected = row => isConversationSelected(row.id);

const someSelected = computed(
  () =>
    selectedIds.value.length > 0 &&
    rows.value.some(row => selectedIds.value.includes(row.id))
);

const headerChecked = computed(
  () => rows.value.length > 0 && props.allConversationsSelected
);

const onSelectAll = event => {
  emit('selectAll', event.target.checked);
  lastToggledIndex.value = null;
};

const setRowSelection = (row, checked) => {
  const inboxId = row.chat.inbox_id;
  if (checked && !isSelected(row)) selectConversation(row.id, inboxId);
  if (!checked && isSelected(row)) deSelectConversation(row.id, inboxId);
};

const onRowCheckbox = (row, index, checked) => {
  if (shiftPressed.value && lastToggledIndex.value !== null) {
    rangeBetween(lastToggledIndex.value, index).forEach(i => {
      if (rows.value[i]) setRowSelection(rows.value[i], checked);
    });
  } else {
    setRowSelection(row, checked);
  }
  lastToggledIndex.value = index;
  shiftPressed.value = false;
};

const onCheckboxCellClick = event => {
  shiftPressed.value = event.shiftKey;
};

// ---- Abrir ticket ----
const ticketPath = row =>
  frontendURL(
    conversationUrl({
      accountId: accountId.value,
      activeInbox: activeInbox.value,
      id: row.id,
      label: props.label,
      teamId: props.teamId,
      conversationType: props.conversationType,
      foldersId: props.foldersId,
    })
  );

const openTicket = (row, event) => {
  const path = ticketPath(row);
  if (event && (event.metaKey || event.ctrlKey)) {
    window.open(
      `${window.chatwootConfig.hostURL}${path}`,
      '_blank',
      'noopener,noreferrer'
    );
    return;
  }
  router.push({ path });
};

const onRowKeydownSpace = (row, index) => {
  onRowCheckbox(row, index, !isSelected(row));
};

// ---- Formatacao ----
const formatUpdated = timestamp => {
  // Le "now" para recalcular o tempo relativo a cada minuto.
  if (!timestamp || !now.value) return '';
  return shortTimestamp(dynamicTime(timestamp));
};

const priorityLabel = priority =>
  PRIORITY_LABEL_KEYS[priority] ? t(PRIORITY_LABEL_KEYS[priority]) : '';

const intersectionObserverOptions = computed(() => ({
  root: scrollContainerRef.value,
  rootMargin: '200px 0px 200px 0px',
}));
</script>

<template>
  <div
    ref="scrollContainerRef"
    class="flex-1 min-h-0 overflow-auto ticket-table-scroll"
    data-testid="ticket-table"
  >
    <table
      class="w-full min-w-[1360px] table-fixed border-separate border-spacing-0 text-sm text-n-slate-12"
      :aria-label="$t('SD_TICKET_TABLE.TABLE_LABEL')"
      :aria-rowcount="rows.length"
    >
      <colgroup>
        <col class="w-10" />
        <col v-for="column in COLUMNS" :key="column.key" :class="column.width" />
      </colgroup>
      <thead>
        <tr>
          <th
            scope="col"
            class="sticky top-0 z-[2] h-10 ps-3 pe-1 bg-n-surface-1 border-b border-n-weak"
          >
            <div class="flex items-center">
              <Checkbox
                :model-value="headerChecked"
                :indeterminate="!headerChecked && someSelected"
                :disabled="!rows.length"
                :aria-label="$t('SD_TICKET_TABLE.COLUMNS.SELECT_ALL')"
                @change="onSelectAll"
              />
            </div>
          </th>
          <th
            v-for="column in COLUMNS"
            :key="column.key"
            scope="col"
            :aria-sort="ariaSort(column.key)"
            class="sticky top-0 z-[2] h-10 px-2 bg-n-surface-1 border-b border-n-weak text-start font-semibold text-xs text-n-slate-11"
          >
            <button
              v-tooltip.top="{
                content: sortHint(column.key),
                delay: { show: 600, hide: 0 },
              }"
              type="button"
              class="group/sort inline-flex items-center gap-1 max-w-full rounded px-1 -mx-1 py-0.5 hover:text-n-slate-12 hover:bg-n-alpha-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-n-brand"
              :class="{
                'text-n-slate-12': activeSort?.column === column.key,
              }"
              @click="onSortColumn(column.key)"
            >
              <span class="truncate">
                {{ $t(`SD_TICKET_TABLE.COLUMNS.${column.i18n}`) }}
              </span>
              <Icon
                :icon="sortIcon(column.key)"
                class="size-3.5 flex-shrink-0"
                :class="
                  activeSort?.column === column.key
                    ? 'text-n-brand'
                    : 'opacity-0 group-hover/sort:opacity-60'
                "
              />
            </button>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(row, index) in rows"
          :key="row.id"
          tabindex="0"
          :aria-selected="isSelected(row)"
          :aria-label="$t('SD_TICKET_TABLE.OPEN_TICKET', { id: row.id })"
          class="group/row cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-n-brand"
          :class="
            isSelected(row)
              ? 'bg-n-slate-2 dark:bg-n-slate-3'
              : 'hover:bg-n-alpha-1'
          "
          @click="openTicket(row, $event)"
          @keydown.enter.self="openTicket(row, $event)"
          @keydown.space.self.prevent="onRowKeydownSpace(row, index)"
        >
          <td
            class="h-10 ps-3 pe-1 border-b border-n-weak"
            @click.stop="onCheckboxCellClick"
          >
            <div class="flex items-center">
              <Checkbox
                :model-value="isSelected(row)"
                :aria-label="
                  $t('SD_TICKET_TABLE.COLUMNS.SELECT_ROW', { id: row.id })
                "
                @change="onRowCheckbox(row, index, $event.target.checked)"
              />
            </div>
          </td>
          <td class="px-2 border-b border-n-weak tabular-nums text-n-slate-11">
            {{ `#${row.id}` }}
          </td>
          <td class="px-2 border-b border-n-weak">
            <div class="flex items-center gap-1.5 min-w-0">
              <span
                v-if="row.isUnread"
                class="size-2 rounded-full bg-n-brand flex-shrink-0"
                :title="$t('SD_TICKET_TABLE.UNREAD')"
              />
              <span
                v-if="row.subject.text"
                class="truncate"
                :class="[
                  row.subject.isPreview ? 'text-n-slate-11' : 'text-n-slate-12',
                  row.isUnread ? 'font-semibold' : 'font-medium',
                ]"
                :title="
                  row.subject.isPreview
                    ? `${$t('SD_TICKET_TABLE.PREVIEW_HINT')}: ${row.subject.text}`
                    : row.subject.text
                "
              >
                {{ row.subject.text }}
              </span>
              <span v-else class="truncate italic text-n-slate-10">
                {{ $t('SD_TICKET_TABLE.NO_SUBJECT') }}
              </span>
            </div>
          </td>
          <td class="px-2 border-b border-n-weak">
            <div
              class="flex items-center gap-2 min-w-0"
              :title="row.requester.email || row.requester.name"
            >
              <Avatar
                :name="row.requester.name || ''"
                :src="row.requester.thumbnail || ''"
                :size="20"
                rounded-full
              />
              <span class="truncate">{{ row.requester.name || '—' }}</span>
            </div>
          </td>
          <td class="px-2 border-b border-n-weak">
            <span
              class="block truncate"
              :class="row.organization ? 'text-n-slate-12' : 'text-n-slate-10'"
              :title="row.organization"
            >
              {{ row.organization || '—' }}
            </span>
          </td>
          <td class="px-2 border-b border-n-weak">
            <TicketStatusBadge :status="row.status" />
          </td>
          <td class="px-2 border-b border-n-weak">
            <div v-if="row.priority" class="flex items-center gap-1.5 min-w-0">
              <CardPriorityIcon :priority="row.priority" />
              <span class="truncate">{{ priorityLabel(row.priority) }}</span>
            </div>
            <span v-else class="text-n-slate-10">{{ '—' }}</span>
          </td>
          <td class="px-2 border-b border-n-weak">
            <span
              class="block truncate"
              :class="row.teamName ? 'text-n-slate-12' : 'text-n-slate-10'"
              :title="row.teamName"
            >
              {{ row.teamName || '—' }}
            </span>
          </td>
          <td class="px-2 border-b border-n-weak">
            <div
              v-if="row.assignee?.name"
              class="flex items-center gap-2 min-w-0"
              :title="row.assignee.name"
            >
              <Avatar
                :name="row.assignee.name"
                :src="row.assignee.thumbnail || ''"
                :size="20"
                rounded-full
              />
              <span class="truncate">{{ row.assignee.name }}</span>
            </div>
            <span v-else class="block truncate text-n-slate-10">
              {{ $t('SD_TICKET_TABLE.UNASSIGNED') }}
            </span>
          </td>
          <td
            class="px-2 border-b border-n-weak text-n-slate-11 tabular-nums"
            :title="exactTimestamp(row.updatedAt)"
          >
            {{ formatUpdated(row.updatedAt) }}
          </td>
          <td class="px-2 border-b border-n-weak">
            <InboxName v-if="row.inbox.name" :inbox="row.inbox" />
            <span v-else class="text-n-slate-10">{{ '—' }}</span>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-if="isLoading" class="flex justify-center my-4">
      <Spinner class="text-n-brand" />
    </div>
    <p v-else-if="showEndOfListMessage" class="p-4 text-center text-n-slate-11">
      {{ $t('CHAT_LIST.EOF') }}
    </p>
    <IntersectionObserver
      v-else
      :options="intersectionObserverOptions"
      @observed="emit('loadMore')"
    />
  </div>
</template>
