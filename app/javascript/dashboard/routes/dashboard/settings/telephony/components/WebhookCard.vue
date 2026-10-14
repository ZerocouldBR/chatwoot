<script setup>
// ServiceDesk: URL do "Tempo real por URL" para cadastrar no painel da 55PBX (método POST). O segredo vai no caminho
// e o sd-ops guarda só o hash: a URL completa aparece UMA vez, logo depois de "Gerar novo"; depois disso, mascarada.
// Gerar um novo segredo invalida o anterior na hora (a 55PBX precisa receber a URL nova).
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import Button from 'dashboard/components-next/button/Button.vue';
import { copyTextToClipboard } from 'shared/helpers/clipboard';
import { useAlert } from 'dashboard/composables';

defineProps({
  webhook: { type: Object, required: true },
  fullUrl: { type: String, default: '' },
  isRotating: { type: Boolean, default: false },
});
const emit = defineEmits(['rotate']);
const { t } = useI18n();
const confirming = ref(false);

const copy = async url => {
  await copyTextToClipboard(url);
  useAlert(t('SD_TELEPHONY.WEBHOOK.COPIED'));
};
const confirmRotate = () => {
  confirming.value = false;
  emit('rotate');
};
</script>

<template>
  <div class="flex flex-col gap-3" data-test="webhook-card">
    <div class="flex flex-col gap-1">
      <span class="text-label-small text-n-slate-11">
        {{ t('SD_TELEPHONY.WEBHOOK.URL_LABEL') }}
      </span>
      <div
        v-if="fullUrl"
        class="flex flex-wrap items-center gap-2 p-3 rounded-lg bg-n-amber-2 outline outline-1 outline-n-amber-6"
      >
        <code
          class="text-sm break-all text-n-slate-12"
          data-test="webhook-full-url"
        >
          {{ fullUrl }}
        </code>
        <Button
          size="xs"
          icon="i-lucide-copy"
          :label="t('SD_TELEPHONY.WEBHOOK.COPY')"
          data-test="webhook-copy"
          @click="copy(fullUrl)"
        />
        <p class="w-full text-label-small text-n-amber-11">
          {{ t('SD_TELEPHONY.WEBHOOK.ONLY_ONCE') }}
        </p>
      </div>
      <code
        v-else-if="webhook.url_masked"
        class="p-3 text-sm rounded-lg bg-n-slate-2 text-n-slate-12 break-all"
        data-test="webhook-masked-url"
      >
        {{ webhook.url_masked }}
      </code>
      <p v-else class="text-body-main text-n-amber-11">
        {{ t('SD_TELEPHONY.WEBHOOK.NOT_DEFINED') }}
      </p>
      <p class="text-label-small text-n-slate-11">
        {{
          t(
            `SD_TELEPHONY.WEBHOOK.SOURCE_${(webhook.source || 'none').toUpperCase()}`
          )
        }}
        <template v-if="webhook.rotated_at">
          ·
          {{ t('SD_TELEPHONY.WEBHOOK.ROTATED_AT', { at: webhook.rotated_at }) }}
        </template>
      </p>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <template v-if="!confirming">
        <Button
          size="sm"
          variant="faded"
          color="amber"
          icon="i-lucide-refresh-cw"
          :is-loading="isRotating"
          :label="t('SD_TELEPHONY.WEBHOOK.ROTATE')"
          data-test="webhook-rotate"
          @click="confirming = true"
        />
      </template>
      <template v-else>
        <span class="text-body-main text-n-amber-11">
          {{ t('SD_TELEPHONY.WEBHOOK.ROTATE_CONFIRM') }}
        </span>
        <Button
          size="sm"
          color="amber"
          :label="t('SD_TELEPHONY.WEBHOOK.ROTATE_YES')"
          data-test="webhook-rotate-confirm"
          @click="confirmRotate"
        />
        <Button
          size="sm"
          variant="ghost"
          color="slate"
          :label="t('SD_TELEPHONY.ACTIONS.CANCEL')"
          @click="confirming = false"
        />
      </template>
    </div>
  </div>
</template>
