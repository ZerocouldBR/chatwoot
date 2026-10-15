<script setup>
import { computed, onMounted } from 'vue';
import { useMapGetter, useStore } from 'dashboard/composables/store';
import Avatar from 'next/avatar/Avatar.vue';
import ContactDetailsItem from './ContactDetailsItem.vue';
import ConversationAction from './ConversationAction.vue';
import ConversationParticipant from './ConversationParticipant.vue';
import TicketCustomFields from './TicketCustomFields.vue';
import { useTicketPanelFields } from 'dashboard/composables/useTicketPanelFields';

// Zendesk-style left column of a ticket: the requester, then the fields the account chose to show, in its order.
const props = defineProps({
  conversation: {
    type: Object,
    required: true,
  },
});

const store = useStore();
const { fieldClass } = useTicketPanelFields();
const getContact = useMapGetter('contacts/getContact');
const requester = computed(() =>
  getContact.value(props.conversation.meta.sender.id)
);
const requesterPath = computed(
  () =>
    `/app/accounts/${props.conversation.account_id}/contacts/${requester.value.id}`
);

// Fresh field settings and custom field definitions, in case an admin changed them since this tab loaded.
onMounted(() => {
  store.dispatch('accounts/get', { silent: true });
  store.dispatch('attributes/get');
});
</script>

<template>
  <aside
    data-testid="ticket-properties"
    class="flex-col hidden h-full gap-1 px-4 py-4 overflow-y-auto border-e border-n-weak bg-n-surface-2 lg:flex w-72 shrink-0"
  >
    <div class="order-first">
      <ContactDetailsItem compact :title="$t('CONVERSATION.REQUESTER')" />
      <router-link
        :to="requesterPath"
        data-testid="ticket-requester"
        class="flex items-center min-w-0 gap-2 p-2 mb-2 rounded-lg hover:bg-n-alpha-1"
      >
        <Avatar :name="requester.name" :src="requester.thumbnail" :size="28" />
        <span class="flex flex-col min-w-0">
          <span class="text-sm font-medium truncate text-n-slate-12">
            {{ requester.name }}
          </span>
          <span v-if="requester.email" class="text-xs truncate text-n-slate-11">
            {{ requester.email }}
          </span>
        </span>
      </router-link>
    </div>
    <ConversationAction
      :conversation-id="conversation.id"
      :inbox-id="conversation.inbox_id"
    />
    <div :class="fieldClass('followers')">
      <ContactDetailsItem
        compact
        :title="$t('CONVERSATION_PARTICIPANTS.SIDEBAR_TITLE')"
      />
      <ConversationParticipant
        :conversation-id="conversation.id"
        :inbox-id="conversation.inbox_id"
      />
    </div>
    <TicketCustomFields :conversation="conversation" />
  </aside>
</template>
