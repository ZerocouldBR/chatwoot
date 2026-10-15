<script setup>
import { computed, ref, watch } from 'vue';
import { useVuelidate } from '@vuelidate/core';
import { useMapGetter } from 'dashboard/composables/store';
import {
  validEmailsByComma,
  getDefaultSubject,
} from './helpers/emailHeadHelper';
import ButtonV4 from 'dashboard/components-next/button/Button.vue';
import TicketCcChips from 'dashboard/components-next/Conversation/TicketCcChips.vue';
import { useSdRolePermissions } from 'dashboard/servicedesk/roles/useSdRolePermissions';

const ccEmails = defineModel('ccEmails', { type: String, default: '' });
const bccEmails = defineModel('bccEmails', { type: String, default: '' });
const toEmails = defineModel('toEmails', { type: String, default: '' });
const subject = defineModel('subject', { type: String, default: '' });

const currentChat = useMapGetter('getSelectedChat');
// ServiceDesk M13: os CCs do ticket só mudam com ticket.edit
const { canEditTicket } = useSdRolePermissions();
const defaultSubject = computed(() => getDefaultSubject(currentChat.value));
if (!subject.value) subject.value = defaultSubject.value;

const showBcc = ref(false);
const isEditingTo = ref(false);
const ccEmailsVal = ref(ccEmails.value);
const bccEmailsVal = ref(bccEmails.value);
const toEmailsVal = ref(toEmails.value);

// Zendesk shows the recipient as a chip with a pencil; editing switches to the address field.
const requesterLabel = computed(
  () =>
    currentChat.value?.meta?.sender?.name ||
    currentChat.value?.meta?.sender?.email
);
const showToChip = computed(
  () =>
    !isEditingTo.value &&
    (!toEmails.value ||
      toEmails.value === currentChat.value?.meta?.sender?.email)
);
const isBccVisible = computed(() => showBcc.value || !!bccEmails.value);

const emailRules = { hasValidEmails: validEmailsByComma };
const v$ = useVuelidate(
  {
    ccEmailsVal: emailRules,
    bccEmailsVal: emailRules,
    toEmailsVal: emailRules,
  },
  { ccEmailsVal, bccEmailsVal, toEmailsVal }
);

watch(bccEmails, value => {
  bccEmailsVal.value = value;
});

watch(toEmails, value => {
  toEmailsVal.value = value;
});

// The field follows the default only until the agent edits it
watch(defaultSubject, (value, previousValue) => {
  if (subject.value === previousValue) subject.value = value;
});

const onBlur = () => {
  v$.value.$touch();
  ccEmails.value = ccEmailsVal.value;
  bccEmails.value = bccEmailsVal.value;
  toEmails.value = toEmailsVal.value;
};
</script>

<template>
  <div data-testid="reply-email-head">
    <div
      class="flex items-center gap-2 my-1 border-b border-solid input-group small"
      :class="v$.toEmailsVal.$error ? 'error border-n-ruby-8' : 'border-n-weak'"
    >
      <label
        class="w-8 text-sm font-normal shrink-0"
        :class="v$.toEmailsVal.$error ? 'text-n-ruby-8' : 'text-n-slate-11'"
      >
        {{ $t('CONVERSATION.REPLYBOX.EMAIL_HEAD.TO') }}
      </label>
      <div v-if="showToChip" class="flex-1 min-w-0 py-1">
        <span
          data-testid="reply-to-chip"
          class="inline-flex items-center gap-1 py-0.5 ps-1 pe-1.5 text-xs font-medium rounded-full bg-n-alpha-2 text-n-slate-12"
        >
          <span class="i-lucide-circle-user-round size-4 text-n-slate-10" />
          {{ requesterLabel }}
          <button
            type="button"
            class="flex items-center text-n-slate-10 hover:text-n-slate-12"
            :aria-label="$t('CONVERSATION.REPLYBOX.EMAIL_HEAD.EDIT_TO')"
            @click="isEditingTo = true"
          >
            <span class="i-lucide-pencil size-3" />
          </button>
        </span>
      </div>
      <div v-else class="flex-1 min-w-0 m-0 rounded-none whitespace-nowrap">
        <woot-input
          v-model="v$.toEmailsVal.$model"
          type="text"
          class="[&>input]:!mb-0 [&>input]:border-transparent [&>input]:!outline-none [&>input]:h-8 [&>input]:!text-sm [&>input]:!border-0 [&>input]:border-none [&>input]:!bg-transparent dark:[&>input]:!bg-transparent"
          :class="{ error: v$.toEmailsVal.$error }"
          :placeholder="$t('CONVERSATION.REPLYBOX.EMAIL_HEAD.CC.PLACEHOLDER')"
          @blur="onBlur"
        />
      </div>
    </div>
    <div
      class="flex items-center gap-2 my-1 border-b border-solid border-n-weak input-group small"
    >
      <label class="w-8 text-sm font-normal shrink-0 text-n-slate-11">
        {{ $t('CONVERSATION.REPLYBOX.EMAIL_HEAD.CC.LABEL') }}
      </label>
      <TicketCcChips
        :conversation-id="currentChat.id"
        :emails="currentChat.cc_emails || []"
        :readonly="!canEditTicket"
      />
      <ButtonV4
        v-if="!isBccVisible"
        :label="$t('CONVERSATION.REPLYBOX.EMAIL_HEAD.BCC.LABEL')"
        link
        xs
        @click="showBcc = true"
      />
    </div>
    <div v-if="isBccVisible">
      <div
        class="flex items-center gap-2 my-1 border-b border-solid input-group small"
        :class="
          v$.bccEmailsVal.$error ? 'error border-n-ruby-8' : 'border-n-weak'
        "
      >
        <label
          class="w-8 text-sm font-normal shrink-0"
          :class="v$.bccEmailsVal.$error ? 'text-n-ruby-8' : 'text-n-slate-11'"
        >
          {{ $t('CONVERSATION.REPLYBOX.EMAIL_HEAD.BCC.LABEL') }}
        </label>
        <div class="flex-1 min-w-0 m-0 rounded-none whitespace-nowrap">
          <woot-input
            v-model="v$.bccEmailsVal.$model"
            type="text"
            class="[&>input]:!mb-0 [&>input]:border-transparent [&>input]:!outline-none [&>input]:h-8 [&>input]:!text-sm [&>input]:!border-0 [&>input]:border-none [&>input]:!bg-transparent dark:[&>input]:!bg-transparent"
            :class="{ error: v$.bccEmailsVal.$error }"
            :placeholder="
              $t('CONVERSATION.REPLYBOX.EMAIL_HEAD.BCC.PLACEHOLDER')
            "
            @blur="onBlur"
          />
        </div>
      </div>
      <span v-if="v$.bccEmailsVal.$error" class="text-sm text-n-ruby-8">
        {{ $t('CONVERSATION.REPLYBOX.EMAIL_HEAD.BCC.ERROR') }}
      </span>
    </div>
  </div>
</template>
