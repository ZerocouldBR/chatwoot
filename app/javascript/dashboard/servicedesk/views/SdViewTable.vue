<script setup>
/**
 * Tabela de uma view do Zendesk (colunas e ordenação do views.json), usada
 * pela lista do Victor só quando a view tem colunas e a lista está em largura
 * total. Sem colunas, a lista por assunto do Victor continua igual.
 */
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import { useMapGetter } from 'dashboard/composables/store';
import { frontendURL, conversationUrl } from 'dashboard/helper/URLHelper';
import TicketSlaBadge from 'dashboard/components-next/Conversation/Sla/TicketSlaBadge.vue';
import { STATUS_BADGE_CLASSES } from 'dashboard/constants/ticketStatuses';
import {
  VIEW_COLUMNS,
  SORT_DIRECTION,
  cellSortValue,
  formatFieldValue,
} from './viewColumns';
import { compareValues } from './sdSort';

const props = defineProps({
  conversations: { type: Array, default: () => [] },
  columns: { type: Array, default: () => [] },
  // { column, direction, sortBy } da view (ou do clique no cabeçalho)
  activeSort: { type: Object, default: null },
  foldersId: { type: [String, Number], default: 0 },
});

const emit = defineEmits(['sort']);

const { t } = useI18n();
const router = useRouter();
const accountId = useMapGetter('getCurrentAccountId');
const currentChat = useMapGetter('getSelectedChat');

const C = VIEW_COLUMNS;

const columnTitle = column =>
  column.title ||
  (column.i18n ? t(`SD_VIEW_TABLE.COLUMNS.${column.i18n}`) : column.key);

// Coluna sem ordenação no servidor: ordena as linhas carregadas
const rows = computed(() => {
  const sort = props.activeSort;
  if (!sort || sort.sortBy) return props.conversations;
  const column = props.columns.find(c => c.key === sort.column);
  if (!column) return props.conversations;
  return [...props.conversations].sort((a, b) =>
    compareValues(
      cellSortValue(a, column),
      cellSortValue(b, column),
      sort.direction
    )
  );
});

const formatTime = timestamp => {
  if (!timestamp) return '';
  const date = new Date(Number(timestamp) * 1000);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString('pt-BR', {
    dateStyle: 'short',
    timeStyle: 'short',
  });
};

const statusLabel = chat => {
  const native = chat?.status
    ? t(`CONVERSATION.TICKET_STATUS.${chat.status}`)
    : '';
  const label = chat?.custom_attributes?.zd_status;
  return label && label !== native ? `${native} · ${label}` : native;
};

const cellText = (chat, column) => {
  if (column.attributeKey) {
    return formatFieldValue(
      chat?.custom_attributes?.[column.attributeKey],
      column.attributeType,
      t
    );
  }
  switch (column.key) {
    case C.NUMBER:
      return `#${chat.id}`;
    case C.SUBJECT:
      return (
        chat.subject ||
        chat.last_non_activity_message?.content?.slice(0, 120) ||
        ''
      );
    case C.REQUESTER:
      return chat.meta?.sender?.name || chat.meta?.sender?.email || '';
    case C.ORGANIZATION:
      return chat.company_name || '';
    case C.STATUS:
      return statusLabel(chat);
    case C.PRIORITY:
      return chat.priority
        ? t(`SD_VIEW_TABLE.PRIORITY.${String(chat.priority).toUpperCase()}`)
        : '';
    case C.GROUP:
      return chat.meta?.team?.name || '';
    case C.ASSIGNEE:
      return chat.meta?.assignee?.name || '';
    case C.UPDATED:
      return formatTime(chat.last_activity_at);
    case C.CREATED:
      return formatTime(chat.created_at);
    case C.SOLVED:
      return formatTime(
        chat.sd_clock?.solved_at ||
          (['resolved', 'closed'].includes(chat.status)
            ? chat.last_activity_at
            : null)
      );
    case C.REQUESTER_UPDATED:
      return formatTime(chat.sd_clock?.requester_updated_at);
    case C.ASSIGNEE_UPDATED:
      return formatTime(chat.sd_clock?.assignee_updated_at);
    case C.CHANNEL:
      return chat.meta?.channel?.replace('Channel::', '') || '';
    case C.SATISFACTION:
      return chat.satisfaction && chat.satisfaction !== 'unoffered'
        ? t(`SD_VIEW_TABLE.SATISFACTION.${chat.satisfaction.toUpperCase()}`)
        : '';
    case C.TYPE:
      return chat.ticket_type || chat.custom_attributes?.zd_tipo || '';
    default:
      return '';
  }
};

const isSorted = column => props.activeSort?.column === column.key;

const onHeaderClick = column => {
  const direction =
    isSorted(column) && props.activeSort.direction === SORT_DIRECTION.ASC
      ? SORT_DIRECTION.DESC
      : SORT_DIRECTION.ASC;
  emit('sort', { column: column.key, direction });
};

const openTicket = chat => {
  const path = frontendURL(
    conversationUrl({
      accountId: accountId.value,
      id: chat.id,
      foldersId: props.foldersId,
    })
  );
  router.push({ path });
};
</script>

<template>
  <div class="flex-1 min-h-0 overflow-auto" data-testid="sd-view-table">
    <table class="min-w-full text-sm border-collapse table-auto">
      <thead class="sticky top-0 z-10 bg-n-surface-1">
        <tr class="border-b border-n-weak">
          <th
            v-for="column in columns"
            :key="column.key"
            class="px-3 py-2 font-medium text-left whitespace-nowrap cursor-pointer select-none text-n-slate-11 hover:text-n-slate-12"
            :aria-sort="
              isSorted(column)
                ? activeSort.direction === 'asc'
                  ? 'ascending'
                  : 'descending'
                : 'none'
            "
            @click="onHeaderClick(column)"
          >
            {{ columnTitle(column) }}
            <span
              v-if="isSorted(column)"
              class="inline-block align-middle size-3"
              :class="
                activeSort.direction === 'asc'
                  ? 'i-lucide-arrow-up'
                  : 'i-lucide-arrow-down'
              "
            />
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="chat in rows"
          :key="chat.id"
          class="border-b cursor-pointer border-n-weak hover:bg-n-alpha-1"
          :class="{ 'bg-n-alpha-2': currentChat && currentChat.id === chat.id }"
          @click="openTicket(chat)"
        >
          <td
            v-for="column in columns"
            :key="column.key"
            class="px-3 py-2 align-top text-n-slate-12"
            :class="
              column.key === 'subject'
                ? 'min-w-[16rem] font-medium'
                : 'whitespace-nowrap'
            "
          >
            <TicketSlaBadge
              v-if="column.key === 'sla'"
              :next-breach-at="chat.next_sla_breach_at || null"
              :breached="!!chat.sla_breached"
            />
            <span
              v-else-if="column.key === 'status'"
              class="inline-flex items-center gap-1.5"
            >
              <span
                class="inline-block rounded-full size-2"
                :class="STATUS_BADGE_CLASSES[chat.status] || 'bg-n-slate-9'"
              />
              {{ cellText(chat, column) }}
            </span>
            <template v-else>{{ cellText(chat, column) }}</template>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
