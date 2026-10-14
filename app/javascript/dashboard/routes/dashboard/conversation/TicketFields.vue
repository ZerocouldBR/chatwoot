<script setup>
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useAlert } from 'dashboard/composables';
import ConversationApi from 'dashboard/api/inbox/conversation';
import ContactDetailsItem from './ContactDetailsItem.vue';
import MultiselectDropdown from 'shared/components/ui/MultiselectDropdown.vue';
import Button from 'dashboard/components-next/button/Button.vue';

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
const ccs = ref(props.conversation.cc_emails || []);
const newCc = ref('');
watch(
  () => props.conversation.cc_emails,
  value => {
    ccs.value = value || [];
  }
);
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
const isIncident = computed(
  () => props.conversation.ticket_type === 'incident'
);
const isProblem = computed(() => props.conversation.ticket_type === 'problem');
const problemId = ref(props.conversation.problem_id || '');
watch(
  () => props.conversation.problem_id,
  value => {
    problemId.value = value || '';
  }
);
const ticketPath = id =>
  `/app/accounts/${props.conversation.account_id}/tickets/${id}`;

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

const saveProblem = () => {
  const value = problemId.value ? Number(problemId.value) : null;
  if (value === (props.conversation.problem_id || null)) return;
  update({ problem_id: value });
};

const addCc = async () => {
  const email = newCc.value.trim();
  if (!email) return;
  try {
    const { data } = await ConversationApi.addCc({
      conversationId: props.conversation.id,
      email,
    });
    ccs.value = data.payload;
    newCc.value = '';
  } catch (error) {
    useAlert(
      error?.response?.data?.error ||
        t('CONVERSATION.TICKET_FIELDS.UPDATE_FAILED')
    );
  }
};

const removeCc = async email => {
  const { data } = await ConversationApi.removeCc({
    conversationId: props.conversation.id,
    email,
  });
  ccs.value = data.payload;
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
    <template v-if="isIncident">
      <ContactDetailsItem
        compact
        :title="$t('CONVERSATION.TICKET_FIELDS.PROBLEM')"
      />
      <input
        v-model="problemId"
        data-testid="ticket-problem"
        type="number"
        min="1"
        :placeholder="$t('CONVERSATION.TICKET_FIELDS.PROBLEM_PLACEHOLDER')"
        class="w-full mb-2 text-sm"
        @blur="saveProblem"
        @keydown.enter.prevent="saveProblem"
      />
    </template>
    <template v-if="isProblem">
      <ContactDetailsItem
        compact
        :title="
          $t('CONVERSATION.TICKET_FIELDS.INCIDENTS', {
            count: conversation.incident_ids?.length || 0,
          })
        "
      />
      <p
        class="flex flex-wrap gap-2 mb-2 text-sm"
        data-testid="ticket-incidents"
      >
        <router-link
          v-for="id in conversation.incident_ids"
          :key="id"
          :to="ticketPath(id)"
          class="text-n-blue-11 hover:underline"
        >
          #{{ id }}
        </router-link>
      </p>
    </template>
    <ContactDetailsItem compact :title="$t('CONVERSATION.TICKET_FIELDS.CC')" />
    <div data-testid="ticket-ccs" class="flex flex-col gap-1 mb-2">
      <p v-if="!ccs.length" class="text-sm text-n-slate-11">
        {{ $t('CONVERSATION.TICKET_FIELDS.CC_EMPTY') }}
      </p>
      <div
        v-for="email in ccs"
        :key="email"
        class="flex items-center justify-between gap-2 text-sm text-n-slate-12"
      >
        <span class="truncate">{{ email }}</span>
        <Button
          icon="i-lucide-x"
          ghost
          slate
          xs
          :aria-label="$t('CONVERSATION.TICKET_FIELDS.CC_REMOVE', { email })"
          @click="removeCc(email)"
        />
      </div>
      <form class="flex gap-2" @submit.prevent="addCc">
        <input
          v-model="newCc"
          data-testid="ticket-cc-input"
          type="email"
          :placeholder="$t('CONVERSATION.TICKET_FIELDS.CC_PLACEHOLDER')"
          class="flex-1 min-w-0 text-sm"
        />
        <Button
          type="submit"
          :label="$t('CONVERSATION.TICKET_FIELDS.CC_ADD')"
          sm
          slate
        />
      </form>
    </div>
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
