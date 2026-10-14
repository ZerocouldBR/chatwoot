<script setup>
import { ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import ConversationApi from 'dashboard/api/inbox/conversation';
import { dynamicTime } from 'shared/helpers/timeHelper';
import Button from 'dashboard/components-next/button/Button.vue';

const props = defineProps({
  conversationId: {
    type: [Number, String],
    required: true,
  },
  // Changes whenever the ticket is updated, so the trail refreshes without a reload.
  revision: {
    type: [Number, String],
    default: 0,
  },
});

const PAGE_SIZE = 50;

const { t } = useI18n();
const events = ref([]);
const hasMore = ref(false);
const isLoading = ref(false);

const fetchEvents = async before => {
  isLoading.value = true;
  try {
    const { data } = await ConversationApi.getEvents({
      conversationId: props.conversationId,
      before,
    });
    events.value = before ? [...events.value, ...data.payload] : data.payload;
    hasMore.value = data.payload.length === PAGE_SIZE;
  } finally {
    isLoading.value = false;
  }
};

watch(
  () => [props.conversationId, props.revision],
  () => fetchEvents(),
  { immediate: true }
);

const loadMore = () => fetchEvents(events.value[events.value.length - 1]?.id);

const authorName = event =>
  event.author?.name || t('CONVERSATION.TICKET_EVENTS.SYSTEM');

const formatValue = (event, value, label) => {
  if (value === null || value === undefined || value === '') {
    return t('CONVERSATION.TICKET_EVENTS.EMPTY_VALUE');
  }
  switch (event.field_name) {
    case 'status':
      return t(`CONVERSATION.TICKET_STATUS.${value}`);
    case 'priority':
      return t(`CONVERSATION.PRIORITY.OPTIONS.${value.toUpperCase()}`);
    case 'ticket_type':
      return t(`CONVERSATION.TICKET_FIELDS.TYPES.${value}`);
    case 'due_at':
      return new Date(value).toLocaleDateString();
    default:
      return label || value;
  }
};

const description = event => {
  const author = authorName(event);
  if (event.event_type === 'create') {
    return t('CONVERSATION.TICKET_EVENTS.CREATED', { author });
  }
  if (event.event_type === 'comment') {
    return event.value?.public
      ? t('CONVERSATION.TICKET_EVENTS.PUBLIC_COMMENT', { author })
      : t('CONVERSATION.TICKET_EVENTS.PRIVATE_COMMENT', { author });
  }
  return t('CONVERSATION.TICKET_EVENTS.CHANGED', {
    author,
    field: t(`CONVERSATION.TICKET_EVENTS.FIELDS.${event.field_name}`),
  });
};
</script>

<template>
  <div data-testid="ticket-events" class="flex flex-col gap-3 py-2">
    <p v-if="!events.length && !isLoading" class="text-sm text-n-slate-11">
      {{ $t('CONVERSATION.TICKET_EVENTS.EMPTY') }}
    </p>
    <div
      v-for="event in events"
      :key="event.id"
      class="flex flex-col gap-0.5 text-sm"
    >
      <span class="text-n-slate-12">{{ description(event) }}</span>
      <span
        v-if="event.event_type === 'change'"
        class="text-n-slate-11 break-words"
      >
        {{
          $t('CONVERSATION.TICKET_EVENTS.CHANGE_VALUES', {
            from: formatValue(
              event,
              event.previous_value,
              event.previous_value_label
            ),
            to: formatValue(event, event.value, event.value_label),
          })
        }}
      </span>
      <span class="text-xs text-n-slate-10">
        {{
          $t('CONVERSATION.TICKET_EVENTS.META', {
            via: $t(`CONVERSATION.TICKET_EVENTS.VIA.${event.via}`),
            time: dynamicTime(event.created_at),
          })
        }}
      </span>
    </div>
    <Button
      v-if="hasMore"
      :label="$t('CONVERSATION.TICKET_EVENTS.LOAD_MORE')"
      :is-loading="isLoading"
      link
      sm
      @click="loadMore"
    />
  </div>
</template>
