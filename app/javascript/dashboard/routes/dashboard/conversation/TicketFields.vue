<script setup>
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useAlert } from 'dashboard/composables';
import ConversationApi from 'dashboard/api/inbox/conversation';
import ContactDetailsItem from './ContactDetailsItem.vue';
import MultiselectDropdown from 'shared/components/ui/MultiselectDropdown.vue';

const props = defineProps({
  conversation: {
    type: Object,
    required: true,
  },
});

const TICKET_TYPES = ['question', 'incident', 'problem', 'task'];
const SUBJECT_MAX_LENGTH = 150;

const { t } = useI18n();

const subject = ref(props.conversation.subject || '');
watch(
  () => props.conversation.subject,
  value => {
    subject.value = value || '';
  }
);

const typeOptions = computed(() =>
  TICKET_TYPES.map(type => ({
    id: type,
    name: t(`CONVERSATION.TICKET_FIELDS.TYPES.${type}`),
  }))
);

const selectedType = computed(
  () =>
    typeOptions.value.find(
      option => option.id === props.conversation.ticket_type
    ) || { id: null, name: t('CONVERSATION.TICKET_FIELDS.NO_TYPE') }
);

const isTask = computed(() => props.conversation.ticket_type === 'task');

// The API returns due_at as a Unix timestamp; the date input wants YYYY-MM-DD.
const dueDate = computed(() => {
  if (!props.conversation.due_at) return '';
  return new Date(props.conversation.due_at * 1000).toISOString().slice(0, 10);
});

const update = async attributes => {
  try {
    await ConversationApi.update(props.conversation.id, attributes);
    useAlert(t('CONVERSATION.TICKET_FIELDS.UPDATED'));
  } catch (error) {
    useAlert(
      error?.response?.data?.error ||
        error?.response?.data?.message ||
        t('CONVERSATION.TICKET_FIELDS.UPDATE_FAILED')
    );
  }
};

const saveSubject = () => {
  const value = subject.value.trim();
  if (value === (props.conversation.subject || '')) return;
  update({ subject: value });
};

const onSelectType = option => {
  if (option.id === props.conversation.ticket_type) return;
  // A due date only exists on tasks, so it is cleared when the type changes away from task.
  update({
    ticket_type: option.id,
    ...(option.id !== 'task' && { due_at: null }),
  });
};

const onDueDateChange = event => {
  const value = event.target.value;
  update({
    due_at: value ? new Date(`${value}T12:00:00`).toISOString() : null,
  });
};
</script>

<template>
  <div>
    <ContactDetailsItem
      compact
      :title="$t('CONVERSATION.TICKET_FIELDS.SUBJECT')"
    />
    <input
      v-model="subject"
      data-testid="ticket-subject"
      type="text"
      :maxlength="SUBJECT_MAX_LENGTH"
      :placeholder="$t('CONVERSATION.TICKET_FIELDS.SUBJECT_PLACEHOLDER')"
      class="w-full mb-2 text-sm"
      @blur="saveSubject"
      @keydown.enter.prevent="saveSubject"
    />
    <ContactDetailsItem
      compact
      :title="$t('CONVERSATION.TICKET_FIELDS.TYPE')"
    />
    <MultiselectDropdown
      data-testid="ticket-type"
      :options="typeOptions"
      :selected-item="selectedType"
      :multiselector-title="$t('CONVERSATION.TICKET_FIELDS.TYPE')"
      :multiselector-placeholder="
        $t('CONVERSATION.TICKET_FIELDS.TYPE_PLACEHOLDER')
      "
      :input-placeholder="$t('CONVERSATION.TICKET_FIELDS.TYPE_PLACEHOLDER')"
      @select="onSelectType"
    />
    <template v-if="isTask">
      <ContactDetailsItem
        compact
        :title="$t('CONVERSATION.TICKET_FIELDS.DUE_DATE')"
      />
      <input
        data-testid="ticket-due-date"
        type="date"
        :value="dueDate"
        class="w-full mb-2 text-sm"
        @change="onDueDateChange"
      />
    </template>
    <ContactDetailsItem
      compact
      :title="$t('CONVERSATION.TICKET_FIELDS.COMPANY')"
    />
    <p class="mb-2 text-sm text-n-slate-12">
      {{
        conversation.company_name || $t('CONVERSATION.TICKET_FIELDS.NO_COMPANY')
      }}
    </p>
  </div>
</template>
