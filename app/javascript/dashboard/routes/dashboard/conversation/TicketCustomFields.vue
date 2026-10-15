<script setup>
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useAlert } from 'dashboard/composables';
import { useMapGetter, useStore } from 'dashboard/composables/store';
import { useTicketPanelFields } from 'dashboard/composables/useTicketPanelFields';
import { customFieldId } from 'dashboard/constants/ticketPanelFields';
import { copyTextToClipboard } from 'shared/helpers/clipboard';
import CustomAttribute from 'dashboard/components/CustomAttribute.vue';
import ContactDetailsItem from './ContactDetailsItem.vue';
import { useSdRolePermissions } from 'dashboard/servicedesk/roles/useSdRolePermissions';
import { formatDate } from 'shared/helpers/timeHelper';

// The account's custom ticket fields in the ticket's left column, each placed (or hidden) by Settings > Ticket fields.
const props = defineProps({
  conversation: {
    type: Object,
    required: true,
  },
});

const { t } = useI18n();
const store = useStore();
const { fieldClass } = useTicketPanelFields();
const attributesByModel = useMapGetter('attributes/getAttributesByModel');
// ServiceDesk M13: sem ticket.edit (Agente light, Colaborador) os campos aparecem só para leitura;
// o backend recusa (403) a gravação dos atributos do ticket.
const { canEditTicket } = useSdRolePermissions();

const attributes = computed(() =>
  attributesByModel.value('conversation_attribute')
);
const values = computed(() => props.conversation.custom_attributes || {});

const readonlyValue = attribute => {
  const value = values.value[attribute.attribute_key];
  if (value === undefined || value === null || value === '')
    return t('CONVERSATION.TICKET_FIELDS.EMPTY');
  if (attribute.attribute_display_type === 'checkbox') {
    return value
      ? t('CONVERSATION.TICKET_FIELDS.YES')
      : t('CONVERSATION.TICKET_FIELDS.NO');
  }
  if (attribute.attribute_display_type === 'date') {
    return formatDate(value, 'MMM d, yyyy');
  }
  return String(value);
};

const save = async customAttributes => {
  try {
    await store.dispatch('updateCustomAttributes', {
      conversationId: props.conversation.id,
      customAttributes,
    });
    useAlert(t('CUSTOM_ATTRIBUTES.FORM.UPDATE.SUCCESS'));
  } catch (error) {
    useAlert(
      error?.response?.message || t('CUSTOM_ATTRIBUTES.FORM.UPDATE.ERROR')
    );
  }
};

const onUpdate = (key, value) => save({ ...values.value, [key]: value });
const onDelete = key => {
  const { [key]: removed, ...rest } = values.value;
  save(rest);
};
const onCopy = async value => {
  await copyTextToClipboard(value);
  useAlert(t('CUSTOM_ATTRIBUTES.COPY_SUCCESSFUL'));
};
</script>

<template>
  <div class="contents">
    <div
      v-for="attribute in attributes"
      :key="attribute.id"
      :data-testid="`ticket-custom-field-${attribute.attribute_key}`"
      class="-mx-4 -mt-2"
      :class="fieldClass(customFieldId(attribute.attribute_key))"
    >
      <div v-if="!canEditTicket" class="px-4 pt-2" data-readonly="true">
        <ContactDetailsItem compact :title="attribute.attribute_display_name" />
        <p class="mb-2 text-sm break-words text-n-slate-12">
          {{ readonlyValue(attribute) }}
        </p>
      </div>
      <CustomAttribute
        v-else
        :attribute-key="attribute.attribute_key"
        :attribute-type="attribute.attribute_display_type"
        :values="attribute.attribute_values"
        :label="attribute.attribute_display_name"
        :description="attribute.attribute_description"
        :value="values[attribute.attribute_key] ?? ''"
        :attribute-regex="attribute.regex_pattern"
        :regex-cue="attribute.regex_cue"
        show-actions
        @update="onUpdate"
        @delete="onDelete"
        @copy="onCopy"
      />
    </div>
  </div>
</template>
