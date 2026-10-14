<script setup>
import { ref } from 'vue';
import Select from 'dashboard/components-next/select/Select.vue';

const props = defineProps({
  label: {
    type: String,
    default: '',
  },
  options: {
    type: Array,
    default: () => [],
  },
  selected: {
    type: String,
    default: '',
  },
  action: {
    type: Function,
    default: () => {},
  },
});

const value = ref(props.selected);
</script>

<template>
  <div class="flex flex-col gap-1">
    <span class="text-sm font-medium text-n-slate-12">{{ label }}</span>
    <Select
      v-model="value"
      class="!w-full"
      :aria-label="label"
      :options="
        options.map(option => ({ value: option.value, label: option.value }))
      "
      @update:model-value="action"
    />
  </div>
</template>
