<script setup>
import { computed } from 'vue';
import { useSnakeCase } from 'dashboard/composables/useTransformKeys';

import Avatar from 'dashboard/components-next/avatar/Avatar.vue';
import MessagePreview from 'dashboard/components-next/Conversation/ConversationCard/MessagePreview.vue';
import CardLabels from 'dashboard/components-next/Conversation/ConversationCard/CardLabels.vue';
import TicketSlaBadge from 'dashboard/components-next/Conversation/Sla/TicketSlaBadge.vue';

const props = defineProps({
  conversation: {
    type: Object,
    required: true,
  },
  accountLabels: {
    type: Array,
    required: true,
  },
  contact: {
    type: Object,
    required: true,
  },
  hasLabels: {
    type: Boolean,
    default: false,
  },
});

const lastNonActivityMessage = computed(() =>
  useSnakeCase(props.conversation.lastNonActivityMessage ?? {}, { deep: true })
);

const assignee = computed(() => {
  const { meta: { assignee: agent = {} } = {} } = props.conversation;
  return {
    name: agent.name ?? agent.availableName,
    thumbnail: agent.thumbnail,
    status: agent.availabilityStatus,
  };
});

const unreadMessagesCount = computed(() => {
  const { unreadCount } = props.conversation;
  return unreadCount;
});

const hasSlaThreshold = computed(() => {
  return !props.contact?.blocked && !!props.conversation?.slaPolicyId;
});

defineExpose({
  hasSlaThreshold,
});
</script>

<template>
  <div class="flex flex-col w-full gap-1">
    <div class="flex items-center justify-between w-full gap-2 py-1 h-7">
      <MessagePreview
        :message="lastNonActivityMessage"
        class="flex-1 min-w-0"
        :class="unreadMessagesCount > 0 ? 'text-n-slate-12' : 'text-n-slate-11'"
      />

      <div
        v-if="unreadMessagesCount > 0"
        class="inline-flex items-center justify-center flex-shrink-0 rounded-full size-5 bg-n-brand"
      >
        <span class="text-xs font-semibold text-white">
          {{ unreadMessagesCount }}
        </span>
      </div>
    </div>

    <div
      class="grid items-center gap-2.5 h-7"
      :class="
        hasSlaThreshold && hasLabels
          ? 'grid-cols-[auto_auto_1fr_20px]'
          : 'grid-cols-[1fr_20px]'
      "
    >
      <TicketSlaBadge
        v-if="hasSlaThreshold"
        :next-breach-at="conversation.nextSlaBreachAt"
        :breached="conversation.slaBreached"
      />
      <div v-if="hasSlaThreshold && hasLabels" class="w-px h-3 bg-n-slate-4" />
      <div v-if="hasLabels" class="overflow-hidden">
        <CardLabels
          :conversation-labels="conversation.labels"
          :account-labels="accountLabels"
        />
      </div>
      <Avatar
        v-if="assignee.name"
        :name="assignee.name"
        :src="assignee.thumbnail"
        :size="20"
        :status="assignee.status"
        rounded-full
      />
    </div>
  </div>
</template>
