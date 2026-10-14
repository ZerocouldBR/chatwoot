<script setup>
// ServiceDesk M5.2/M4: parâmetros de set_custom_attribute ([chave, valor]) no construtor
// de macros e automações. O valor segue o tipo do atributo (lista, checkbox, número, data...).
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useMapGetter } from 'dashboard/composables/store';
import SingleSelect from 'dashboard/components-next/filter/inputs/SingleSelect.vue';
import NextInput from 'dashboard/components-next/input/Input.vue';
import {
  getAttributeValueOptions,
  getSettableAttributes,
  valueInputTypeFor,
} from 'dashboard/servicedesk/actionOptions';

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  dropdownMaxHeight: { type: String, default: 'max-h-80' },
});

const emit = defineEmits(['update:modelValue']);

const { t } = useI18n();
const attributesByModel = useMapGetter('attributes/getAttributesByModel');

const attributes = computed(() =>
  getSettableAttributes(attributesByModel.value('conversation_attribute'))
);
const attributeOptions = computed(() =>
  attributes.value.map(attribute => ({
    id: attribute.attribute_key,
    name: attribute.attribute_display_name,
  }))
);

const params = computed(() =>
  Array.isArray(props.modelValue) ? props.modelValue : []
);
const attributeKey = computed(() => params.value[0] ?? null);
const attributeValue = computed(() => params.value[1] ?? '');
const selectedAttribute = computed(() =>
  attributes.value.find(
    attribute => attribute.attribute_key === attributeKey.value
  )
);
const valueOptions = computed(() =>
  getAttributeValueOptions(selectedAttribute.value, t)
);

const attributeModel = computed({
  get: () =>
    attributeOptions.value.find(option => option.id === attributeKey.value) ||
    null,
  set: option => emit('update:modelValue', option ? [option.id, ''] : []),
});

const valueModel = computed({
  get: () =>
    valueOptions.value?.find(
      option => option.id === String(attributeValue.value)
    ) || null,
  set: option =>
    emit('update:modelValue', [attributeKey.value, option ? option.id : '']),
});

const textValue = computed({
  get: () => String(attributeValue.value ?? ''),
  set: value =>
    emit('update:modelValue', [attributeKey.value, String(value ?? '')]),
});
</script>

<template>
  <div class="flex items-center gap-2 min-w-0">
    <SingleSelect
      v-model="attributeModel"
      :options="attributeOptions"
      :placeholder="t('AUTOMATION.ACTION.ATTRIBUTE_PLACEHOLDER')"
      :dropdown-max-height="dropdownMaxHeight"
    />
    <template v-if="selectedAttribute">
      <SingleSelect
        v-if="valueOptions"
        v-model="valueModel"
        :options="valueOptions"
        :placeholder="t('AUTOMATION.ACTION.ATTRIBUTE_VALUE_PLACEHOLDER')"
        :dropdown-max-height="dropdownMaxHeight"
      />
      <NextInput
        v-else
        v-model="textValue"
        :type="valueInputTypeFor(selectedAttribute)"
        size="sm"
        class="flex-1 min-w-0"
        :placeholder="t('AUTOMATION.ACTION.ATTRIBUTE_VALUE_PLACEHOLDER')"
      />
    </template>
  </div>
</template>
