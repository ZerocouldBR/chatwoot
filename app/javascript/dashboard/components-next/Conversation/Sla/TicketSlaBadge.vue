<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';

const props = defineProps({
  // Unix timestamp of the next SLA target, or null when nothing is running.
  nextBreachAt: {
    type: Number,
    default: null,
  },
  breached: {
    type: Boolean,
    default: false,
  },
});

// Zendesk shows the badge in warning colours when a target is 15 minutes or less away.
const WARNING_SECONDS = 15 * 60;
const REFRESH_MS = 30 * 1000;

const { t } = useI18n();
const now = ref(Date.now() / 1000);
let timer;

onMounted(() => {
  timer = setInterval(() => {
    now.value = Date.now() / 1000;
  }, REFRESH_MS);
});
onBeforeUnmount(() => clearInterval(timer));

const remaining = computed(() =>
  props.nextBreachAt ? props.nextBreachAt - now.value : null
);

const isOverdue = computed(
  () => props.breached || (remaining.value !== null && remaining.value <= 0)
);

const formatDuration = seconds => {
  const minutes = Math.max(1, Math.round(seconds / 60));
  if (minutes < 60)
    return t('CONVERSATION.SLA_BADGE.MINUTES', { count: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t('CONVERSATION.SLA_BADGE.HOURS', { count: hours });
  return t('CONVERSATION.SLA_BADGE.DAYS', { count: Math.floor(hours / 24) });
};

const label = computed(() => {
  if (isOverdue.value) return t('CONVERSATION.SLA_BADGE.BREACHED');
  return formatDuration(remaining.value);
});

const colorClass = computed(() => {
  if (isOverdue.value) return 'bg-n-ruby-9 text-white';
  if (remaining.value <= WARNING_SECONDS) return 'bg-n-amber-9 text-n-slate-12';
  return 'bg-n-teal-9 text-white';
});
</script>

<template>
  <span
    v-if="breached || nextBreachAt"
    v-tooltip.top="$t('CONVERSATION.SLA_BADGE.TOOLTIP')"
    data-testid="ticket-sla-badge"
    class="inline-flex items-center gap-1 px-1.5 h-5 rounded text-xs font-medium shrink-0"
    :class="colorClass"
  >
    <span class="i-lucide-timer size-3" />
    {{ label }}
  </span>
</template>
