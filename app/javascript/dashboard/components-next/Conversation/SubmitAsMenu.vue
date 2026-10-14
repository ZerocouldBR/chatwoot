<script setup>
import { computed, useTemplateRef } from 'vue';
import { useI18n } from 'vue-i18n';
import { useToggle } from '@vueuse/core';
import { vOnClickOutside } from '@vueuse/components';

import Button from 'dashboard/components-next/button/Button.vue';
import DropdownMenu from 'dashboard/components-next/dropdown-menu/DropdownMenu.vue';
import {
  AGENT_SETTABLE_STATUSES,
  STATUS_ICONS,
} from 'dashboard/constants/ticketStatuses';

defineProps({
  disabled: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['submit']);

const { t } = useI18n();
const containerRef = useTemplateRef('containerRef');
const [showDropdown, toggleDropdown] = useToggle(false);

const menuItems = computed(() =>
  AGENT_SETTABLE_STATUSES.map(status => ({
    action: 'submit',
    value: status,
    label: t('CONVERSATION.REPLYBOX.SUBMIT_AS', {
      status: t(`CONVERSATION.TICKET_STATUS.${status}`),
    }),
    icon: STATUS_ICONS[status],
  }))
);

const onSelect = item => {
  toggleDropdown(false);
  emit('submit', item.value);
};
</script>

<template>
  <div ref="containerRef" class="relative">
    <Button
      v-tooltip.top="$t('CONVERSATION.REPLYBOX.SUBMIT_AS_TOOLTIP')"
      icon="i-lucide-chevron-up"
      data-testid="submit-as-menu"
      sm
      blue
      :disabled="disabled"
      class="ltr:rounded-l-none rtl:rounded-r-none"
      @click="toggleDropdown()"
    />
    <DropdownMenu
      v-if="showDropdown"
      v-on-click-outside="[
        () => toggleDropdown(false),
        { ignore: [containerRef] },
      ]"
      :menu-items="menuItems"
      class="bottom-9 ltr:right-0 rtl:left-0 w-56"
      @action="onSelect"
    />
  </div>
</template>
