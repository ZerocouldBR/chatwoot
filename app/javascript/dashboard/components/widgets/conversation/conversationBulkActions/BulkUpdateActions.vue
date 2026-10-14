<script setup>
import { useTemplateRef, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useToggle } from '@vueuse/core';
import { vOnClickOutside } from '@vueuse/components';

import Button from 'dashboard/components-next/button/Button.vue';
import DropdownMenu from 'dashboard/components-next/dropdown-menu/DropdownMenu.vue';
import {
  AGENT_SETTABLE_STATUSES,
  STATUS_ICONS,
} from 'dashboard/constants/ticketStatuses';

const emit = defineEmits(['update']);

const { t } = useI18n();

const containerRef = useTemplateRef('containerRef');
const [showDropdown, toggleDropdown] = useToggle(false);

const updateMenuItems = computed(() =>
  AGENT_SETTABLE_STATUSES.map(status => ({
    action: 'update',
    value: status,
    label: t(`CONVERSATION.TICKET_STATUS.${status}`),
    icon: STATUS_ICONS[status],
  }))
);

const handleUpdate = item => {
  emit('update', item.value);
  toggleDropdown(false);
};
</script>

<template>
  <div ref="containerRef" class="relative">
    <Button
      v-tooltip="$t('BULK_ACTION.UPDATE.CHANGE_STATUS')"
      icon="i-lucide-circle-fading-arrow-up"
      slate
      xs
      ghost
      :class="{ 'bg-n-alpha-2': showDropdown }"
      @click="toggleDropdown()"
    />
    <Transition
      enter-active-class="transition-all duration-150 ease-out origin-bottom"
      enter-from-class="opacity-0 scale-95"
      enter-to-class="opacity-100 scale-100"
      leave-active-class="transition-all duration-100 ease-in origin-bottom"
      leave-from-class="opacity-100 scale-100"
      leave-to-class="opacity-0 scale-95"
    >
      <DropdownMenu
        v-if="showDropdown"
        v-on-click-outside="[
          () => toggleDropdown(false),
          { ignore: [containerRef] },
        ]"
        :menu-items="updateMenuItems"
        class="ltr:-right-[4.5rem] rtl:-left-[4.5rem] ltr:2xl:right-0 rtl:2xl:left-0 bottom-8 w-36"
        @action="handleUpdate"
      />
    </Transition>
  </div>
</template>
