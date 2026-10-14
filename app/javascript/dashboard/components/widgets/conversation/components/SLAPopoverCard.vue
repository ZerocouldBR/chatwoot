<script setup>
import { computed } from 'vue';
import SLAEventItem from './SLAEventItem.vue';

const props = defineProps({
  slaMissedEvents: {
    type: Array,
    required: true,
  },
});

// Breaches grouped by SLA metric, in the order they happened.
const breachesByMetric = computed(() =>
  props.slaMissedEvents.reduce((groups, event) => {
    (groups[event.metric] ||= []).push(event);
    return groups;
  }, {})
);
</script>

<template>
  <div
    class="absolute flex flex-col items-start border-n-strong bg-n-solid-3 w-96 backdrop-blur-[100px] px-6 py-5 z-50 shadow rounded-xl gap-4 max-h-96 overflow-auto"
  >
    <span class="text-sm font-medium text-n-slate-12">
      {{ $t('SLA.EVENTS.TITLE') }}
    </span>
    <SLAEventItem
      v-for="(events, metric) in breachesByMetric"
      :key="metric"
      :label="$t(`TICKET_SLA.METRICS.${metric}`)"
      :items="events"
    />
  </div>
</template>
