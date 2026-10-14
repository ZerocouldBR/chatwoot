<script setup>
// ServiceDesk: o que falta para ativar a integração (dependências D1–D4 do ROADMAP + mapa de ramais + ativação).
import { useI18n } from 'vue-i18n';

defineProps({
  items: { type: Array, default: () => [] },
});
const { t } = useI18n();

const detail = item => {
  const i = item.info || {};
  switch (item.id) {
    case 'D1':
      return i.last_poll_ok_at
        ? t('SD_TELEPHONY.CHECKLIST.D1.LAST_POLL', { at: i.last_poll_ok_at })
        : '';
    case 'D2':
      if (!i.secret_defined) return t('SD_TELEPHONY.CHECKLIST.D2.NO_SECRET');
      return i.last_webhook_at
        ? t('SD_TELEPHONY.CHECKLIST.D2.LAST_WEBHOOK', { at: i.last_webhook_at })
        : t('SD_TELEPHONY.CHECKLIST.D2.WAITING');
    case 'D3':
      return t('SD_TELEPHONY.CHECKLIST.D3.STORED', {
        n: i.recordings_stored || 0,
      });
    case 'D4':
      return i.credentials
        ? t('SD_TELEPHONY.CHECKLIST.D4.MODE', { mode: i.mode })
        : t('SD_TELEPHONY.CHECKLIST.D4.NO_CREDENTIALS');
    case 'MAPS':
      return t('SD_TELEPHONY.CHECKLIST.MAPS.COUNT', { n: i.branches || 0 });
    case 'ENABLED':
      return i.force_disabled ? t('SD_TELEPHONY.CHECKLIST.ENABLED.FORCED') : '';
    default:
      return '';
  }
};
</script>

<template>
  <ul class="grid gap-2 sm:grid-cols-2" data-test="checklist">
    <li
      v-for="item in items"
      :key="item.id"
      class="flex items-start gap-2 p-3 rounded-lg border border-n-weak"
      :data-test="`check-${item.id}`"
    >
      <span
        class="mt-0.5 size-4 shrink-0"
        :class="
          item.done
            ? 'i-lucide-circle-check text-n-teal-10'
            : 'i-lucide-circle-dashed text-n-amber-10'
        "
      />
      <div class="flex flex-col gap-0.5 min-w-0">
        <span class="text-body-main text-n-slate-12">
          <strong v-if="item.id.startsWith('D')">{{ item.id }} · </strong>
          {{ t(`SD_TELEPHONY.CHECKLIST.${item.id}.LABEL`) }}
        </span>
        <span class="text-label-small text-n-slate-11">
          {{ t(`SD_TELEPHONY.CHECKLIST.${item.id}.HELP`) }}
        </span>
        <span v-if="detail(item)" class="text-label-small text-n-slate-11">
          {{ detail(item) }}
        </span>
      </div>
    </li>
  </ul>
</template>
