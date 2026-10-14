<script setup>
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { STATUS_BADGE_CLASSES } from 'dashboard/constants/ticketStatuses';

const props = defineProps({
  status: {
    type: String,
    default: '',
  },
  showEmpty: {
    type: Boolean,
    default: false,
  },
});

const { t } = useI18n();

const badgeClass = computed(() => STATUS_BADGE_CLASSES[props.status]);
const label = computed(() =>
  badgeClass.value ? t(`CONVERSATION.TICKET_STATUS.${props.status}`) : ''
);
</script>

<template>
  <span
    v-if="badgeClass || showEmpty"
    v-tooltip.top="{
      content: label,
      delay: { show: 500, hide: 0 },
    }"
    :aria-label="label"
    class="size-3 flex-shrink-0 rounded-sm"
    :class="badgeClass || 'outline outline-1 outline-n-strong'"
  />
</template>
