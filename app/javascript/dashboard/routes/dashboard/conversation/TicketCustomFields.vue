<script setup>
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useAlert } from 'dashboard/composables';
import { useMapGetter, useStore } from 'dashboard/composables/store';
import { useTicketPanelFields } from 'dashboard/composables/useTicketPanelFields';
import { customFieldId } from 'dashboard/constants/ticketPanelFields';
import { copyTextToClipboard } from 'shared/helpers/clipboard';
import CustomAttribute from 'dashboard/components/CustomAttribute.vue';

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

const attributes = computed(() =>
  attributesByModel.value('conversation_attribute')
);
const values = computed(() => props.conversation.custom_attributes || {});

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
      <CustomAttribute
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
