<script setup>
import { computed, onUnmounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useSdRolePermissions } from 'dashboard/servicedesk/roles/useSdRolePermissions';
import TicketsAPI from 'dashboard/api/tickets';
import { UNSOLVED_STATUSES } from 'dashboard/constants/ticketStatuses';
import MergeTicketDialog from './MergeTicketDialog.vue';
import Dialog from 'dashboard/components-next/dialog/Dialog.vue';
import { frontendURL } from 'dashboard/helper/URLHelper';
import { useToggle } from '@vueuse/core';
import { useStore } from 'vuex';
import { useAlert } from 'dashboard/composables';
import { useI18n } from 'vue-i18n';
import { emitter } from 'shared/helpers/mitt';
import EmailTranscriptModal from './EmailTranscriptModal.vue';
import ResolveAction from '../../buttons/ResolveAction.vue';
import ButtonV4 from 'dashboard/components-next/button/Button.vue';
import DropdownMenu from 'dashboard/components-next/dropdown-menu/DropdownMenu.vue';

import {
  CMD_MUTE_CONVERSATION,
  CMD_SEND_TRANSCRIPT,
  CMD_UNMUTE_CONVERSATION,
} from 'dashboard/helper/commandbar/events';

// No props needed as we're getting currentChat from the store directly
const store = useStore();
const { t } = useI18n();

const [showEmailActionsModal, toggleEmailModal] = useToggle(false);
const [showActionsDropdown, toggleDropdown] = useToggle(false);

const currentChat = computed(() => store.getters.getSelectedChat);
const router = useRouter();
// ServiceDesk M13: mesclar (ticket.merge), spam (ticket.delete) e status (ticket.edit) conforme o papel
const { canEditTicket, canMergeTicket, canDeleteTicket } =
  useSdRolePermissions();
const mergeDialog = ref(null);
const spamDialog = ref(null);

const actionMenuItems = computed(() => {
  const items = [];

  if (!currentChat.value.muted) {
    items.push({
      icon: 'i-lucide-volume-off',
      label: t('CONTACT_PANEL.MUTE_CONTACT'),
      action: 'mute',
      value: 'mute',
    });
  } else {
    items.push({
      icon: 'i-lucide-volume-1',
      label: t('CONTACT_PANEL.UNMUTE_CONTACT'),
      action: 'unmute',
      value: 'unmute',
    });
  }

  items.push({
    icon: 'i-lucide-share',
    label: t('CONTACT_PANEL.SEND_TRANSCRIPT'),
    action: 'send_transcript',
    value: 'send_transcript',
  });

  if (
    canMergeTicket.value &&
    UNSOLVED_STATUSES.includes(currentChat.value.status)
  ) {
    items.push({
      icon: 'i-lucide-merge',
      label: t('TICKET_MERGE.ACTION'),
      action: 'merge',
      value: 'merge',
    });
  }

  if (canDeleteTicket.value) {
    items.push({
      icon: 'i-lucide-shield-ban',
      label: t('TICKET_SPAM.ACTION'),
      action: 'spam',
      value: 'spam',
    });
  }

  return items;
});

const markAsSpam = async () => {
  await TicketsAPI.markAsSpam(currentChat.value.id);
  spamDialog.value.close();
  useAlert(t('TICKET_SPAM.DONE'));
  router.push(
    frontendURL(`accounts/${currentChat.value.account_id}/dashboard`)
  );
};

const handleActionClick = ({ action }) => {
  toggleDropdown(false);

  if (action === 'mute') {
    store.dispatch('muteConversation', currentChat.value.id);
    useAlert(t('CONTACT_PANEL.MUTED_SUCCESS'));
  } else if (action === 'unmute') {
    store.dispatch('unmuteConversation', currentChat.value.id);
    useAlert(t('CONTACT_PANEL.UNMUTED_SUCCESS'));
  } else if (action === 'send_transcript') {
    toggleEmailModal();
  } else if (action === 'merge') {
    mergeDialog.value.open();
  } else if (action === 'spam') {
    spamDialog.value.open();
  }
};

// These functions are needed for the event listeners
const mute = () => {
  store.dispatch('muteConversation', currentChat.value.id);
  useAlert(t('CONTACT_PANEL.MUTED_SUCCESS'));
};

const unmute = () => {
  store.dispatch('unmuteConversation', currentChat.value.id);
  useAlert(t('CONTACT_PANEL.UNMUTED_SUCCESS'));
};

emitter.on(CMD_MUTE_CONVERSATION, mute);
emitter.on(CMD_UNMUTE_CONVERSATION, unmute);
emitter.on(CMD_SEND_TRANSCRIPT, toggleEmailModal);

onUnmounted(() => {
  emitter.off(CMD_MUTE_CONVERSATION, mute);
  emitter.off(CMD_UNMUTE_CONVERSATION, unmute);
  emitter.off(CMD_SEND_TRANSCRIPT, toggleEmailModal);
});
</script>

<template>
  <div class="relative flex items-center gap-2 actions--container">
    <ResolveAction
      v-if="canEditTicket"
      :conversation-id="currentChat.id"
      :status="currentChat.status"
    />
    <div
      v-on-clickaway="() => toggleDropdown(false)"
      class="relative flex items-center group"
    >
      <ButtonV4
        v-tooltip="$t('CONVERSATION.HEADER.MORE_ACTIONS')"
        data-testid="ticket-more-actions"
        size="sm"
        variant="ghost"
        color="slate"
        icon="i-lucide-more-vertical"
        class="rounded-md group-hover:bg-n-alpha-2"
        @click="toggleDropdown()"
      />
      <DropdownMenu
        v-if="showActionsDropdown"
        :menu-items="actionMenuItems"
        class="mt-1 ltr:right-0 rtl:left-0 top-full"
        @action="handleActionClick"
      />
    </div>
    <MergeTicketDialog ref="mergeDialog" :ticket="currentChat" />
    <Dialog
      ref="spamDialog"
      type="alert"
      :title="$t('TICKET_SPAM.TITLE')"
      :description="$t('TICKET_SPAM.DESCRIPTION')"
      :confirm-button-label="$t('TICKET_SPAM.CONFIRM')"
      @confirm="markAsSpam"
    />
    <EmailTranscriptModal
      v-if="showEmailActionsModal"
      :show="showEmailActionsModal"
      :current-chat="currentChat"
      @cancel="toggleEmailModal"
    />
  </div>
</template>
