<script setup>
import { computed, nextTick, ref } from 'vue';
import { useRoute } from 'vue-router';
import { useStore } from 'vuex';
import BackButton from '../BackButton.vue';
import MoreActions from './MoreActions.vue';
import ChannelIcon from 'next/icon/ChannelIcon.vue';
import TicketSlaBadge from 'dashboard/components-next/Conversation/Sla/TicketSlaBadge.vue';
import ConversationCallButton from './ConversationCallButton.vue';
import {
  conversationListPageURL,
  conversationUrl,
  frontendURL,
} from 'dashboard/helper/URLHelper';
import { useInbox } from 'dashboard/composables/useInbox';
import { useAlert } from 'dashboard/composables';
import { useI18n } from 'vue-i18n';
import { copyTextToClipboard } from 'shared/helpers/clipboard';
import { dynamicTime } from 'shared/helpers/timeHelper';
import ConversationApi from 'dashboard/api/inbox/conversation';
import { STATUS_BADGE_CLASSES } from 'dashboard/constants/ticketStatuses';

const props = defineProps({
  chat: {
    type: Object,
    default: () => ({}),
  },
  showBackButton: {
    type: Boolean,
    default: false,
  },
});

const { t, te } = useI18n();
const store = useStore();
const route = useRoute();
const { isAWebWidgetInbox, isAnEmailChannel } = useInbox();

const currentChat = computed(() => store.getters.getSelectedChat);
const accountId = computed(() => store.getters.getCurrentAccountId);

const chatMetadata = computed(() => props.chat.meta);

const backButtonUrl = computed(() => {
  const {
    params: { inbox_id: inboxId, label, teamId, id: customViewId },
    name,
  } = route;

  const conversationTypeMap = {
    conversation_through_mentions: 'mention',
    conversation_through_participating: 'participating',
    conversation_through_unattended: 'unattended',
  };
  return conversationListPageURL({
    accountId: accountId.value,
    inboxId,
    label,
    teamId,
    conversationType: conversationTypeMap[name],
    customViewId,
  });
});

const isHMACVerified = computed(() => {
  if (!isAWebWidgetInbox.value) {
    return true;
  }
  return chatMetadata.value.hmac_verified;
});

const mailSubject = computed(() => {
  if (props.chat.subject) return props.chat.subject;
  if (!isAnEmailChannel.value) return '';
  return props.chat.additional_attributes?.mail_subject;
});

const currentContact = computed(() =>
  store.getters['contacts/getContact'](props.chat.meta.sender.id)
);

const followupSourceLink = computed(() => {
  const sourceId = props.chat.followup_source_id;
  if (!sourceId) return null;
  return frontendURL(
    conversationUrl({ accountId: route.params.accountId, id: sourceId })
  );
});

const mergedIntoLink = computed(() => {
  const targetId = props.chat.merged_into_id;
  if (!targetId) return null;
  return frontendURL(
    conversationUrl({ accountId: route.params.accountId, id: targetId })
  );
});

const statusLabel = computed(() =>
  t(`CONVERSATION.TICKET_STATUS.${currentChat.value.status}`)
);

const inbox = computed(() => {
  const { inbox_id: inboxId } = props.chat;
  return store.getters['inboxes/getInbox'](inboxId);
});

// "Pelo e-mail", "Pelo WhatsApp"... (Zendesk shows the channel as a small chip under the subject).
const channelKey = computed(() =>
  (inbox.value?.channel_type || '')
    .replace('Channel::', '')
    .replace(/([a-z])([A-Z])/g, '$1_$2')
    .toLowerCase()
);
const channelLabel = computed(() => {
  const key = `CONVERSATION.CHANNEL_CHIP.${channelKey.value}`;
  return te(key) ? t(key) : inbox.value?.name;
});
const createdAt = computed(() => dynamicTime(props.chat.created_at));

// Zendesk edits the subject right in the ticket header.
const SUBJECT_MAX_LENGTH = 150;
const isEditingSubject = ref(false);
const subjectDraft = ref('');
const subjectInput = ref(null);
const editSubject = async () => {
  subjectDraft.value = props.chat.subject || '';
  isEditingSubject.value = true;
  await nextTick();
  subjectInput.value?.focus();
};
const saveSubject = async () => {
  if (!isEditingSubject.value) return;
  isEditingSubject.value = false;
  const value = subjectDraft.value.trim();
  if (!value || value === props.chat.subject) return;
  try {
    await ConversationApi.update(props.chat.id, { subject: value });
  } catch (error) {
    useAlert(
      error?.response?.data?.error ||
        t('CONVERSATION.TICKET_FIELDS.UPDATE_FAILED')
    );
  }
};

const SATISFACTION_ICONS = {
  offered: 'i-lucide-meh',
  good: 'i-lucide-smile',
  bad: 'i-lucide-frown',
};
const STATUS_TEXT_CLASSES = {
  closed: 'text-n-slate-12',
  on_hold: 'text-n-slate-1',
};
const statusBadgeClass = computed(() => {
  const { status } = currentChat.value;
  return [
    STATUS_BADGE_CLASSES[status],
    STATUS_TEXT_CLASSES[status] || 'text-white',
  ];
});

const hasSlaPolicyId = computed(
  () => !!props.chat?.sla_policy_id && !currentContact.value?.blocked
);

const copyConversationId = async () => {
  try {
    await copyTextToClipboard(String(props.chat.id));
    useAlert(t('CONVERSATION.HEADER.COPY_ID_SUCCESS'));
  } catch (error) {
    // error
  }
};
</script>

<template>
  <div
    data-testid="ticket-header"
    class="flex items-start justify-between w-full min-w-0 gap-3 px-4 pt-3 pb-3"
  >
    <div class="flex items-start min-w-0 gap-2">
      <BackButton
        v-if="showBackButton"
        :back-url="backButtonUrl"
        class="mt-1"
      />
      <div class="flex flex-col min-w-0 gap-1">
        <div class="flex items-center gap-2 text-xs text-n-slate-11">
          <span
            data-testid="ticket-header-status"
            class="px-1.5 py-0.5 rounded font-medium uppercase tracking-wide"
            :class="statusBadgeClass"
          >
            {{ statusLabel }}
          </span>
          <button
            type="button"
            class="font-medium text-n-slate-12 hover:underline !p-0"
            @click="copyConversationId"
          >
            {{ $t('CONVERSATION.TICKET_NUMBER', { id: chat.id }) }}
          </button>
        </div>
        <input
          v-if="isEditingSubject"
          ref="subjectInput"
          v-model="subjectDraft"
          data-testid="ticket-subject"
          type="text"
          :maxlength="SUBJECT_MAX_LENGTH"
          class="!mb-0 !h-8 !py-0 !px-1 text-lg font-semibold"
          @blur="saveSubject"
          @keydown.enter.prevent="saveSubject"
          @keydown.esc="isEditingSubject = false"
        />
        <h1
          v-else
          v-tooltip="$t('CONVERSATION.EDIT_SUBJECT')"
          data-testid="ticket-header-subject"
          class="text-lg font-semibold leading-snug truncate cursor-text text-n-slate-12 hover:bg-n-alpha-1 rounded px-1 -mx-1"
          @click="editSubject"
        >
          {{ mailSubject || $t('CONVERSATION.NO_SUBJECT') }}
        </h1>
        <div
          class="flex flex-wrap items-center gap-1.5 text-xs text-n-slate-11"
        >
          <span
            data-testid="ticket-header-channel"
            class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-n-alpha-2"
          >
            <ChannelIcon v-if="inbox" :inbox="inbox" class="size-3" />
            {{ channelLabel }}
          </span>
          <span class="px-1.5 py-0.5 rounded bg-n-alpha-2">
            {{ $t('CONVERSATION.CREATED_AGO', { time: createdAt }) }}
          </span>
          <span
            class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-n-alpha-2"
          >
            {{ currentContact.name }}
            <fluent-icon
              v-if="!isHMACVerified"
              v-tooltip="$t('CONVERSATION.UNVERIFIED_SESSION')"
              size="12"
              class="text-n-amber-10"
              icon="warning"
            />
          </span>
          <span
            v-if="chat.satisfaction && chat.satisfaction !== 'unoffered'"
            v-tooltip="chat.satisfaction_comment"
            data-testid="ticket-satisfaction"
            class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-n-alpha-2"
            :class="{
              'text-n-teal-11': chat.satisfaction === 'good',
              'text-n-ruby-11': chat.satisfaction === 'bad',
            }"
          >
            <span
              :class="SATISFACTION_ICONS[chat.satisfaction]"
              class="size-3"
            />
            {{ $t(`CONVERSATION.SATISFACTION.${chat.satisfaction}`) }}
            <template v-if="chat.satisfaction_comment">
              · {{ chat.satisfaction_comment }}
            </template>
          </span>
          <router-link
            v-if="followupSourceLink"
            :to="followupSourceLink"
            data-testid="followup-source-link"
            class="px-1.5 py-0.5 rounded bg-n-alpha-2 text-n-blue-11 hover:underline"
          >
            {{
              $t('CONVERSATION.FOLLOWUP_OF', { id: chat.followup_source_id })
            }}
          </router-link>
          <router-link
            v-if="mergedIntoLink"
            :to="mergedIntoLink"
            data-testid="merged-into-link"
            class="px-1.5 py-0.5 rounded bg-n-alpha-2 text-n-blue-11 hover:underline"
          >
            {{ $t('CONVERSATION.MERGED_INTO', { id: chat.merged_into_id }) }}
          </router-link>
        </div>
      </div>
    </div>
    <div class="flex items-center flex-shrink-0 gap-2">
      <TicketSlaBadge
        v-if="hasSlaPolicyId"
        :next-breach-at="chat.next_sla_breach_at"
        :breached="chat.sla_breached"
      />
      <ConversationCallButton :inbox="inbox" :chat="currentChat" />
      <MoreActions :conversation-id="currentChat.id" />
    </div>
  </div>
</template>
