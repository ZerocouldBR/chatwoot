<script setup>
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  STATUS_BADGE_COLORS,
  STATUS_CATEGORY,
} from './statusTokensFallback';

const props = defineProps({
  // Resultado de getTicketStatus(chat)
  status: { type: Object, required: true },
});

const { t } = useI18n();

const category = computed(() => props.status.category || STATUS_CATEGORY.OPEN);

const categoryLabel = computed(() =>
  t(`SD_TICKET_TABLE.STATUS_CATEGORY.${category.value.toUpperCase()}`)
);

const label = computed(() =>
  props.status.source === 'zendesk' ? props.status.label : categoryLabel.value
);

const tooltip = computed(() =>
  props.status.source === 'zendesk'
    ? t('SD_TICKET_TABLE.STATUS_TOOLTIP', {
        label: props.status.label,
        category: categoryLabel.value,
      })
    : categoryLabel.value
);

const badgeStyle = computed(() => {
  const colors =
    STATUS_BADGE_COLORS[category.value] ||
    STATUS_BADGE_COLORS[STATUS_CATEGORY.OPEN];
  return { backgroundColor: colors.background, color: colors.color };
});
</script>

<template>
  <span
    v-tooltip.top="{ content: tooltip, delay: { show: 400, hide: 0 } }"
    class="inline-flex items-center max-w-full h-5 px-2 rounded-full text-xs font-semibold leading-none ring-1 ring-inset ring-black/5 dark:ring-white/10"
    :style="badgeStyle"
    :data-category="category"
  >
    <span class="truncate">{{ label }}</span>
  </span>
</template>
