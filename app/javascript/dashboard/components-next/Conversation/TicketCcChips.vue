<script setup>
import { ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useAlert } from 'dashboard/composables';
import ConversationApi from 'dashboard/api/inbox/conversation';

// The ticket's CCs as removable chips with an inline input (Zendesk "CC" line): Enter, comma or leaving the field
// adds the typed address; the list is saved on the ticket, so every public reply copies these people.
const props = defineProps({
  conversationId: {
    type: Number,
    required: true,
  },
  emails: {
    type: Array,
    default: () => [],
  },
  // ServiceDesk M13: sem ticket.edit os CCs aparecem sem remover nem adicionar (o backend responde 403)
  readonly: {
    type: Boolean,
    default: false,
  },
});

const { t } = useI18n();
const ccs = ref([...props.emails]);
const draft = ref('');
watch(
  () => props.emails,
  value => {
    ccs.value = [...value];
  }
);

const save = async request => {
  try {
    const { data } = await request;
    ccs.value = data.payload;
  } catch (error) {
    useAlert(
      error?.response?.data?.error ||
        t('CONVERSATION.TICKET_FIELDS.UPDATE_FAILED')
    );
  }
};

const add = () => {
  const email = draft.value.replace(/,$/, '').trim();
  if (!email) return;
  draft.value = '';
  save(ConversationApi.addCc({ conversationId: props.conversationId, email }));
};

const remove = email =>
  save(
    ConversationApi.removeCc({ conversationId: props.conversationId, email })
  );

const removeLast = () => {
  if (!draft.value && ccs.value.length) remove(ccs.value[ccs.value.length - 1]);
};
</script>

<template>
  <div
    data-testid="ticket-ccs"
    class="flex flex-wrap items-center flex-1 min-w-0 gap-1 py-1"
  >
    <span
      v-for="email in ccs"
      :key="email"
      class="inline-flex items-center gap-1 py-0.5 ps-1 pe-1.5 text-xs rounded-full bg-n-alpha-2 text-n-slate-12"
    >
      <span class="i-lucide-circle-user-round size-4 text-n-slate-10" />
      {{ email }}
      <button
        v-if="!readonly"
        type="button"
        class="flex items-center text-n-slate-10 hover:text-n-slate-12"
        :aria-label="$t('CONVERSATION.TICKET_FIELDS.CC_REMOVE', { email })"
        @click="remove(email)"
      >
        <span class="i-lucide-x size-3" />
      </button>
    </span>
    <span v-if="readonly && !ccs.length" class="text-sm text-n-slate-10">{{
      $t('CONVERSATION.TICKET_FIELDS.EMPTY')
    }}</span>
    <input
      v-if="!readonly"
      v-model="draft"
      data-testid="ticket-cc-input"
      type="email"
      class="flex-1 min-w-32 !mb-0 !h-7 !p-0 !text-sm !border-0 !bg-transparent !outline-none"
      :placeholder="
        ccs.length ? '' : $t('CONVERSATION.TICKET_FIELDS.CC_PLACEHOLDER')
      "
      @keydown.enter.prevent="add"
      @keydown.,.prevent="add"
      @keydown.backspace="removeLast"
      @blur="add"
    />
  </div>
</template>
