<script setup>
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useUISettings } from 'dashboard/composables/useUISettings';
import wootConstants from 'dashboard/constants/globals';
import NextButton from 'dashboard/components-next/button/Button.vue';
import { useTicketListMode, TICKET_LIST_MODES } from './useTicketListMode';

const props = defineProps({
  isOnExpandedLayout: { type: Boolean, default: false },
});

const { t } = useI18n();
const { updateUISettings } = useUISettings();
const { isTableMode, setMode } = useTicketListMode();

// A tabela so aparece no layout expandido (lista em largura total).
const isShowingTable = computed(
  () => isTableMode.value && props.isOnExpandedLayout
);

const tooltip = computed(() =>
  isShowingTable.value
    ? t('SD_TICKET_TABLE.TOGGLE.TO_LIST')
    : t('SD_TICKET_TABLE.TOGGLE.TO_TABLE')
);

const toggle = () => {
  if (isShowingTable.value) {
    setMode(TICKET_LIST_MODES.LIST);
    return;
  }
  setMode(TICKET_LIST_MODES.TABLE);
  if (!props.isOnExpandedLayout) {
    const { EXPANDED } = wootConstants.LAYOUT_TYPES;
    updateUISettings({
      conversation_display_type: EXPANDED,
      previously_used_conversation_display_type: EXPANDED,
    });
  }
};
</script>

<template>
  <NextButton
    v-tooltip.left="tooltip"
    :aria-label="tooltip"
    :aria-pressed="isShowingTable"
    :icon="isShowingTable ? 'i-lucide-list' : 'i-lucide-table-2'"
    slate
    xs
    faded
    class="flex-shrink-0 md:inline-flex hidden"
    data-testid="ticket-list-mode-toggle"
    @click="toggle"
  />
</template>
