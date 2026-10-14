<script setup>
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import { useAlert } from 'dashboard/composables';
import ConversationAPI from 'dashboard/api/inbox/conversation';
import TicketsAPI from 'dashboard/api/tickets';
import Dialog from 'dashboard/components-next/dialog/Dialog.vue';
import { frontendURL, conversationUrl } from 'dashboard/helper/URLHelper';

const props = defineProps({
  ticket: {
    type: Object,
    required: true,
  },
});

const { t } = useI18n();
const router = useRouter();
const dialog = ref(null);
const targetId = ref('');
const target = ref(null);
const sourceComment = ref('');
const targetComment = ref('');
const isPublic = ref(false);
const isMerging = ref(false);

const canMerge = computed(
  () => target.value && target.value.id !== props.ticket.id
);

const findTarget = async () => {
  target.value = null;
  if (!targetId.value) return;
  try {
    const { data } = await ConversationAPI.show(targetId.value);
    target.value = data;
  } catch {
    useAlert(t('TICKET_MERGE.NOT_FOUND'));
  }
};

const merge = async () => {
  isMerging.value = true;
  try {
    const { data } = await TicketsAPI.merge(props.ticket.id, {
      targetId: target.value.id,
      sourceComment: sourceComment.value,
      targetComment: targetComment.value,
      isPublic: isPublic.value,
    });
    useAlert(t('TICKET_MERGE.DONE', { id: data.id }));
    dialog.value.close();
    router.push(
      frontendURL(conversationUrl({ accountId: data.account_id, id: data.id }))
    );
  } catch (error) {
    useAlert(error?.response?.data?.message || t('TICKET_MERGE.ERROR'));
  } finally {
    isMerging.value = false;
  }
};

defineExpose({ open: () => dialog.value.open() });
</script>

<template>
  <Dialog
    ref="dialog"
    :title="$t('TICKET_MERGE.TITLE', { id: ticket.id })"
    :description="$t('TICKET_MERGE.DESCRIPTION')"
    :confirm-button-label="$t('TICKET_MERGE.CONFIRM')"
    :disable-confirm-button="!canMerge"
    :is-loading="isMerging"
    @confirm="merge"
  >
    <div class="flex flex-col gap-4" data-testid="merge-ticket-dialog">
      <label class="flex flex-col gap-1 text-sm text-n-slate-12">
        {{ $t('TICKET_MERGE.TARGET') }}
        <input
          v-model="targetId"
          data-testid="merge-target-id"
          type="number"
          min="1"
          @change="findTarget"
        />
      </label>
      <p
        v-if="target"
        data-testid="merge-target-preview"
        class="text-sm text-n-slate-11"
      >
        #{{ target.id }} · {{ target.subject }}
      </p>
      <label class="flex flex-col gap-1 text-sm text-n-slate-12">
        {{ $t('TICKET_MERGE.SOURCE_COMMENT', { id: ticket.id }) }}
        <textarea
          v-model="sourceComment"
          rows="2"
          :placeholder="$t('TICKET_MERGE.COMMENT_PLACEHOLDER')"
        />
      </label>
      <label class="flex flex-col gap-1 text-sm text-n-slate-12">
        {{ $t('TICKET_MERGE.TARGET_COMMENT') }}
        <textarea
          v-model="targetComment"
          rows="2"
          :placeholder="$t('TICKET_MERGE.COMMENT_PLACEHOLDER')"
        />
      </label>
      <label class="flex items-center gap-2 text-sm text-n-slate-12">
        <input v-model="isPublic" type="checkbox" />
        {{ $t('TICKET_MERGE.PUBLIC') }}
      </label>
      <p class="text-xs text-n-slate-11">
        {{ $t('TICKET_MERGE.IRREVERSIBLE') }}
      </p>
    </div>
  </Dialog>
</template>
