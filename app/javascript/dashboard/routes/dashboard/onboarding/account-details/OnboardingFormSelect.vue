<script setup>
import Select from 'dashboard/components-next/select/Select.vue';

defineProps({
  options: { type: Array, default: () => [] },
  placeholder: { type: String, default: '' },
  hasError: { type: Boolean, default: false },
});

const modelValue = defineModel({ type: String, default: '' });
</script>

<template>
  <Select
    v-model="modelValue"
    ghost
    :options="options"
    :placeholder="placeholder"
    :class="{ 'animate-shake': hasError }"
  />
</template>
