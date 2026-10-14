<script setup>
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useAlert } from 'dashboard/composables';
import TicketsAPI from 'dashboard/api/tickets';
import Dialog from 'dashboard/components-next/dialog/Dialog.vue';

// Zendesk "Redact": permanently replaces text (or the whole comment) and deletes attachments.
const props = defineProps({
  message: {
    type: Object,
    required: true,
  },
});

const { t } = useI18n();
const dialog = ref(null);
const text = ref('');
const removeAttachments = ref(false);
const isSaving = ref(false);

const attachments = computed(() => props.message.attachments || []);

const redact = async () => {
  isSaving.value = true;
  try {
    await TicketsAPI.redact(props.message.conversation_id, props.message.id, {
      text: text.value,
      attachmentIds: removeAttachments.value
        ? attachments.value.map(attachment => attachment.id)
        : [],
    });
    useAlert(t('TICKET_REDACTION.DONE'));
    dialog.value.close();
  } catch (error) {
    useAlert(error?.response?.data?.error || t('TICKET_REDACTION.ERROR'));
  } finally {
    isSaving.value = false;
  }
};

defineExpose({ open: () => dialog.value.open() });
</script>

<template>
  <Dialog
    ref="dialog"
    type="alert"
    :title="$t('TICKET_REDACTION.TITLE')"
    :description="$t('TICKET_REDACTION.DESCRIPTION')"
    :confirm-button-label="$t('TICKET_REDACTION.CONFIRM')"
    :is-loading="isSaving"
    @confirm="redact"
  >
    <div class="flex flex-col gap-3" data-testid="redact-message-dialog">
      <label class="flex flex-col gap-1 text-sm text-n-slate-12">
        {{ $t('TICKET_REDACTION.TEXT') }}
        <input
          v-model="text"
          data-testid="redact-text"
          type="text"
          :placeholder="$t('TICKET_REDACTION.TEXT_PLACEHOLDER')"
        />
      </label>
      <label
        v-if="attachments.length"
        class="flex items-center gap-2 text-sm text-n-slate-12"
      >
        <input v-model="removeAttachments" type="checkbox" />
        {{ $t('TICKET_REDACTION.ATTACHMENTS', { count: attachments.length }) }}
      </label>
    </div>
  </Dialog>
</template>
