<script setup>
// ServiceDesk: resultado do "Testar conexão", item a item (ok / erro / aviso / falta / ignorado) com o motivo do sd-ops.
import { useI18n } from 'vue-i18n';

defineProps({
  result: { type: Object, required: true },
});
const { t } = useI18n();

const ICONS = {
  ok: 'i-lucide-circle-check text-n-teal-10',
  error: 'i-lucide-circle-x text-n-ruby-10',
  warning: 'i-lucide-triangle-alert text-n-amber-10',
  missing: 'i-lucide-circle-dashed text-n-amber-10',
  skipped: 'i-lucide-circle-minus text-n-slate-10',
};
</script>

<template>
  <div class="flex flex-col gap-2" data-test="test-results">
    <ul class="grid gap-1.5">
      <li
        v-for="item in result.items"
        :key="item.id"
        class="grid grid-cols-[auto_10rem_1fr] items-start gap-2"
        :data-test="`test-${item.id}`"
        :data-status="item.status"
      >
        <span
          class="mt-0.5 size-4"
          :class="ICONS[item.status] || ICONS.skipped"
        />
        <span class="text-body-main text-n-slate-12">
          {{ t(`SD_TELEPHONY.TEST.ITEMS.${item.id.toUpperCase()}`) }}
          <span class="block text-label-small text-n-slate-11">
            {{ t(`SD_TELEPHONY.TEST.STATUS.${item.status.toUpperCase()}`) }}
          </span>
        </span>
        <span class="text-body-main text-n-slate-11 break-words">
          {{ item.detail }}
        </span>
      </li>
    </ul>
    <p class="text-label-small text-n-slate-11">
      {{ t('SD_TELEPHONY.TEST.TESTED_AT', { at: result.tested_at }) }}
    </p>
  </div>
</template>
