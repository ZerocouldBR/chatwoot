<script setup>
// ServiceDesk: segredo mascarado. O valor salvo nunca chega ao navegador: só "definido", os últimos 4 caracteres e
// a origem (tela/ambiente). Vazio = manter o atual; "Apagar" volta ao valor do ambiente.
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import Button from 'dashboard/components-next/button/Button.vue';
import Input from 'dashboard/components-next/input/Input.vue';

const props = defineProps({
  meta: { type: Object, required: true },
  vaultEnabled: { type: Boolean, default: true },
  inputId: { type: String, default: '' },
});
const model = defineModel({ type: Object, required: true });
const { t } = useI18n();
const editing = ref(false);

const status = computed(() => {
  if (model.value.clear) return t('SD_TELEPHONY.SECRET.WILL_CLEAR');
  if (!props.meta.defined) return t('SD_TELEPHONY.SECRET.NOT_DEFINED');
  return props.meta.last4
    ? t('SD_TELEPHONY.SECRET.DEFINED_LAST4', { last4: props.meta.last4 })
    : t('SD_TELEPHONY.SECRET.DEFINED');
});

const update = patch => {
  model.value = { ...model.value, ...patch };
};
const startEdit = () => {
  editing.value = true;
  update({ clear: false });
};
const cancelEdit = () => {
  editing.value = false;
  update({ value: '' });
};
const toggleClear = () => {
  editing.value = false;
  update({ value: '', clear: !model.value.clear });
};
</script>

<template>
  <div class="flex flex-col gap-2" data-test="secret-field">
    <div class="flex flex-wrap items-center gap-2">
      <span
        class="inline-flex items-center gap-1.5 text-body-main"
        :class="meta.defined ? 'text-n-slate-12' : 'text-n-slate-11'"
        data-test="secret-status"
      >
        <span
          class="size-2 rounded-full"
          :class="meta.defined && !model.clear ? 'bg-n-teal-9' : 'bg-n-slate-8'"
        />
        {{ status }}
      </span>
      <span
        v-if="meta.defined && !model.clear"
        class="text-label-small text-n-slate-11"
      >
        {{ t(`SD_TELEPHONY.SOURCE.${(meta.source || 'none').toUpperCase()}`) }}
      </span>
      <span v-if="meta.error" class="text-label-small text-n-ruby-11">
        {{ meta.error }}
      </span>
      <div class="flex items-center gap-1 ltr:ml-auto rtl:mr-auto">
        <Button
          v-if="!editing"
          size="xs"
          variant="faded"
          color="slate"
          :disabled="!vaultEnabled"
          :label="
            meta.defined
              ? t('SD_TELEPHONY.SECRET.REPLACE')
              : t('SD_TELEPHONY.SECRET.SET')
          "
          data-test="secret-edit"
          @click="startEdit"
        />
        <Button
          v-else
          size="xs"
          variant="ghost"
          color="slate"
          :label="t('SD_TELEPHONY.ACTIONS.CANCEL')"
          @click="cancelEdit"
        />
        <Button
          v-if="meta.source === 'panel'"
          size="xs"
          variant="ghost"
          :color="model.clear ? 'slate' : 'ruby'"
          :label="
            model.clear
              ? t('SD_TELEPHONY.ACTIONS.UNDO')
              : t('SD_TELEPHONY.SECRET.CLEAR')
          "
          data-test="secret-clear"
          @click="toggleClear"
        />
      </div>
    </div>
    <Input
      v-if="editing"
      :id="inputId"
      :model-value="model.value"
      type="password"
      autocomplete="new-password"
      :placeholder="t('SD_TELEPHONY.SECRET.PLACEHOLDER')"
      data-test="secret-input"
      @update:model-value="v => update({ value: v })"
    />
    <p v-if="!vaultEnabled" class="text-label-small text-n-amber-11">
      {{ t('SD_TELEPHONY.SECRET.VAULT_MISSING') }}
    </p>
  </div>
</template>
