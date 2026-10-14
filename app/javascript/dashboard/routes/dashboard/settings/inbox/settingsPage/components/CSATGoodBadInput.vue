<script setup>
import { computed } from 'vue';
import { CSAT_DISPLAY_TYPES } from 'shared/constants/messages';

const props = defineProps({
  selected: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['update']);

const selectionClass = computed(() =>
  props.selected
    ? 'outline-n-brand bg-n-brand/5'
    : 'outline-n-weak bg-n-alpha-black2'
);
</script>

<template>
  <button
    type="button"
    class="flex items-center gap-4 px-4 py-2 rounded-lg cursor-pointer outline outline-1 min-w-56 text-sm text-n-slate-12"
    :class="selectionClass"
    @click="emit('update', CSAT_DISPLAY_TYPES.GOOD_BAD)"
  >
    <span class="flex items-center gap-1">
      <span class="i-lucide-thumbs-up size-5 text-n-teal-10" />
      {{ $t('CONVERSATION.SATISFACTION.good') }}
    </span>
    <span class="flex items-center gap-1">
      <span class="i-lucide-thumbs-down size-5 text-n-ruby-10" />
      {{ $t('CONVERSATION.SATISFACTION.bad') }}
    </span>
  </button>
</template>
