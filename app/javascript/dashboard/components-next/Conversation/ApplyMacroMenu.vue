<script setup>
import { computed, onMounted, ref } from 'vue';
import { useToggle } from '@vueuse/core';
import { useMapGetter, useStore } from 'dashboard/composables/store';
import Button from 'dashboard/components-next/button/Button.vue';
import DropdownMenu from 'dashboard/components-next/dropdown-menu/DropdownMenu.vue';

// Zendesk "Apply macro", at the start of the reply footer.
const emit = defineEmits(['apply']);

const store = useStore();
const macros = useMapGetter('macros/getMacros');
const [isOpen, toggle] = useToggle(false);
const wrapper = ref(null);

const menuItems = computed(() =>
  macros.value.map(macro => ({
    label: macro.name,
    value: macro.id,
    action: 'apply',
    icon: 'i-lucide-wand-sparkles',
  }))
);

const onAction = ({ value }) => {
  toggle(false);
  emit(
    'apply',
    macros.value.find(macro => macro.id === value)
  );
};

onMounted(() => store.dispatch('macros/get'));
</script>

<template>
  <div
    ref="wrapper"
    v-on-clickaway="() => toggle(false)"
    class="relative"
    data-testid="apply-macro"
  >
    <Button
      type="button"
      :label="$t('CONVERSATION.APPLY_MACRO')"
      icon="i-lucide-wand-sparkles"
      slate
      faded
      sm
      @click="toggle()"
    />
    <DropdownMenu
      v-if="isOpen"
      :menu-items="menuItems"
      show-search
      :search-placeholder="$t('CONVERSATION.APPLY_MACRO_SEARCH')"
      class="bottom-full mb-1 ltr:left-0 rtl:right-0 w-64 max-h-80 overflow-y-auto"
      @action="onAction"
    />
  </div>
</template>
