<script setup>
import { computed } from 'vue';
import { CSAT_GOOD_BAD_RATINGS } from 'shared/constants/messages';

// Zendesk-style satisfaction: Good (stored as 5) or Bad (stored as 1).
const props = defineProps({
  selectedRating: {
    type: Number,
    default: null,
  },
  isDisabled: {
    type: Boolean,
    default: false,
  },
  goodLabel: {
    type: String,
    required: true,
  },
  badLabel: {
    type: String,
    required: true,
  },
});

const emit = defineEmits(['selectRating']);

const options = computed(() => [
  {
    value: CSAT_GOOD_BAD_RATINGS.GOOD,
    icon: 'i-lucide-thumbs-up',
    label: props.goodLabel,
  },
  {
    value: CSAT_GOOD_BAD_RATINGS.BAD,
    icon: 'i-lucide-thumbs-down',
    label: props.badLabel,
  },
]);
</script>

<template>
  <div class="flex gap-3 py-4" data-testid="good-bad-rating">
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      :disabled="isDisabled"
      class="flex items-center justify-center flex-1 gap-2 px-4 py-3 text-sm font-medium border rounded-lg disabled:opacity-60"
      :class="
        selectedRating === option.value
          ? 'border-n-brand bg-n-brand/10 text-n-slate-12'
          : 'border-n-weak text-n-slate-11 hover:bg-n-alpha-1'
      "
      @click="emit('selectRating', option.value)"
    >
      <span :class="option.icon" class="size-5" />
      {{ option.label }}
    </button>
  </div>
</template>
