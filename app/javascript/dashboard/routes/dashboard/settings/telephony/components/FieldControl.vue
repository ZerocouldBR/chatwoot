<script setup>
// ServiceDesk: um campo da tela Telefonia 55PBX, desenhado pelo tipo que o sd-ops informa (bool, enum, número,
// texto/URL, lista, mapa, segredo), com a origem do valor (tela / ambiente / padrão) e "voltar ao ambiente".
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import SettingsFieldSection from 'dashboard/components-next/Settings/SettingsFieldSection.vue';
import Input from 'dashboard/components-next/input/Input.vue';
import Select from 'dashboard/components-next/select/Select.vue';
import Switch from 'dashboard/components-next/switch/Switch.vue';
import Button from 'dashboard/components-next/button/Button.vue';
import SecretField from './SecretField.vue';
import KeyValueEditor from './KeyValueEditor.vue';
import { listToText, textToList } from '../settingsForm';

const props = defineProps({
  fieldKey: { type: String, required: true },
  meta: { type: Object, required: true },
  vaultEnabled: { type: Boolean, default: true },
  teamOptions: { type: Array, default: () => [] },
  reset: { type: Boolean, default: false },
});
const emit = defineEmits(['reset']);
const model = defineModel({ type: [String, Number, Boolean, Array, Object] });
const { t, te } = useI18n();

const base = computed(
  () => `SD_TELEPHONY.FIELDS.${props.fieldKey.toUpperCase()}`
);
const label = computed(() => t(`${base.value}.LABEL`));
const help = computed(() =>
  te(`${base.value}.HELP`) ? t(`${base.value}.HELP`) : ''
);
const inputId = computed(() => `sd-telephony-${props.fieldKey}`);
const isSecret = computed(() => props.meta.kind === 'secret');

const choiceLabel = c => {
  const k = `SD_TELEPHONY.CHOICES.${String(c).toUpperCase()}`;
  return te(k) ? t(k) : String(c);
};
const options = computed(() => {
  if (props.fieldKey === 'default_team') {
    const opts = props.teamOptions.map(name => ({ value: name, label: name }));
    if (model.value && !props.teamOptions.includes(model.value))
      opts.unshift({ value: model.value, label: model.value });
    return opts;
  }
  return (props.meta.choices || []).map(c => ({
    value: c,
    label: choiceLabel(c),
  }));
});

// lista editada como texto ("a, b, c")
const listText = ref(props.meta.kind === 'list' ? listToText(model.value) : '');
watch(
  () => model.value,
  v => {
    if (
      props.meta.kind === 'list' &&
      JSON.stringify(textToList(listText.value)) !== JSON.stringify(v || [])
    )
      listText.value = listToText(v);
  }
);
const onListInput = v => {
  listText.value = v;
  model.value = textToList(v);
};
const onNumber = v => {
  model.value = v === '' ? null : Number(v);
};

const source = computed(() =>
  props.reset ? 'env' : props.meta.source || 'default'
);
</script>

<template>
  <SettingsFieldSection :label="label" :help-text="help">
    <div class="flex flex-col gap-1.5" :data-test="`field-${fieldKey}`">
      <SecretField
        v-if="isSecret"
        v-model="model"
        :meta="meta"
        :vault-enabled="vaultEnabled"
        :input-id="inputId"
      />
      <div v-else-if="meta.kind === 'bool'" class="flex items-center gap-2">
        <Switch v-model="model" />
        <span class="text-body-main text-n-slate-11">
          {{ model ? t('SD_TELEPHONY.ON') : t('SD_TELEPHONY.OFF') }}
        </span>
      </div>
      <Select
        v-else-if="meta.kind === 'enum' || fieldKey === 'default_team'"
        v-model="model"
        :options="options"
        :aria-label="label"
      />
      <Input
        v-else-if="meta.kind === 'int' || meta.kind === 'float'"
        :id="inputId"
        type="number"
        :model-value="model ?? ''"
        @update:model-value="onNumber"
      />
      <Input
        v-else-if="meta.kind === 'list'"
        :id="inputId"
        :model-value="listText"
        :placeholder="t('SD_TELEPHONY.LIST_PLACEHOLDER')"
        @update:model-value="onListInput"
      />
      <KeyValueEditor
        v-else-if="meta.kind === 'map'"
        v-model="model"
        :field-key="fieldKey"
        :team-options="teamOptions"
      />
      <Input
        v-else
        :id="inputId"
        :model-value="model ?? ''"
        :type="meta.kind === 'url' ? 'url' : 'text'"
        @update:model-value="v => (model = v)"
      />
      <div
        v-if="!isSecret"
        class="flex items-center gap-2 text-label-small text-n-slate-11"
      >
        <span data-test="field-source">
          {{ t(`SD_TELEPHONY.SOURCE.${source.toUpperCase()}`) }}
          <template v-if="meta.env && !meta.env.includes('.')">
            · {{ meta.env }}
          </template>
        </span>
        <Button
          v-if="meta.source === 'panel' && !reset"
          size="xs"
          variant="link"
          color="slate"
          :label="t('SD_TELEPHONY.ACTIONS.RESET_TO_ENV')"
          @click="emit('reset', true)"
        />
        <Button
          v-if="reset"
          size="xs"
          variant="link"
          color="slate"
          :label="t('SD_TELEPHONY.ACTIONS.UNDO')"
          @click="emit('reset', false)"
        />
      </div>
    </div>
  </SettingsFieldSection>
</template>
