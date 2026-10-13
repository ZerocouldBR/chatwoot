<script setup>
// Selo de status da tabela: rótulo zd_status (status personalizado) quando
// existe, com a cor da categoria; senão o rótulo da categoria do status nativo.
// Cores e rótulos vêm dos tokens oficiais do tema (statusTokens.js), então
// funcionam nos modos claro e escuro.
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { STATUS_TOKENS } from 'dashboard/servicedesk/statusTokens';

const props = defineProps({
  // Resultado de getTicketStatus(chat)
  status: { type: Object, required: true },
});

const { t } = useI18n();

const token = computed(
  () => STATUS_TOKENS[props.status.category] || STATUS_TOKENS.open
);

const categoryLabel = computed(() => t(token.value.labelKey));

const label = computed(() =>
  props.status.source === 'custom' ? props.status.label : categoryLabel.value
);

const tooltip = computed(() =>
  props.status.source === 'custom'
    ? t('SD_TICKET_TABLE.STATUS_TOOLTIP', {
        label: props.status.label,
        category: categoryLabel.value,
      })
    : categoryLabel.value
);
</script>

<template>
  <span
    v-tooltip.top="{ content: tooltip, delay: { show: 400, hide: 0 } }"
    class="inline-flex items-center max-w-full h-5 px-2 rounded-full text-xs font-semibold leading-none ring-1 ring-inset ring-black/5 dark:ring-white/10"
    :class="token.classes.badge"
    :data-category="token.category"
  >
    <span class="truncate">{{ label }}</span>
  </span>
</template>
