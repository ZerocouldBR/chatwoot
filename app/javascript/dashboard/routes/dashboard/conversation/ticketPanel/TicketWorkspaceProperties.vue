<script setup>
// Coluna de PROPRIEDADES à esquerda da conversa (layout Agent Workspace).
// Largura fixa de 300px com scroll próprio; pode ser recolhida para um trilho
// estreito (preferência por usuário em useTicketWorkspace).
import { useTicketWorkspace } from 'dashboard/servicedesk/workspace/useTicketWorkspace';
import NextButton from 'dashboard/components-next/button/Button.vue';
import TicketPropertiesPanel from './TicketPropertiesPanel.vue';

defineProps({
  conversationId: { type: [Number, String], required: true },
});

const { isPropertiesOpen, toggleProperties } = useTicketWorkspace();
</script>

<template>
  <aside
    v-if="isPropertiesOpen"
    class="flex flex-col h-full w-[300px] min-w-[300px] shrink-0 bg-n-solid-1 ltr:border-r rtl:border-l border-n-weak"
    :aria-label="$t('SERVICEDESK_TICKET_PANEL.WORKSPACE.PROPERTIES')"
    data-testid="ticket-workspace-properties"
  >
    <header
      class="flex items-center justify-between h-12 px-4 border-b border-n-weak shrink-0"
    >
      <span class="text-sm font-medium text-n-slate-12">
        {{ $t('SERVICEDESK_TICKET_PANEL.WORKSPACE.PROPERTIES') }}
      </span>
      <NextButton
        v-tooltip.bottom="$t('SERVICEDESK_TICKET_PANEL.WORKSPACE.COLLAPSE')"
        :aria-label="$t('SERVICEDESK_TICKET_PANEL.WORKSPACE.COLLAPSE')"
        icon="i-lucide-panel-left-close"
        ghost
        slate
        sm
        data-testid="ticket-workspace-collapse"
        @click="toggleProperties"
      />
    </header>
    <div class="flex-1 min-h-0 overflow-y-auto overscroll-contain">
      <TicketPropertiesPanel
        :conversation-id="conversationId"
        variant="column"
      />
    </div>
  </aside>
  <div
    v-else
    class="flex flex-col items-center h-full w-11 shrink-0 py-2 bg-n-solid-1 ltr:border-r rtl:border-l border-n-weak"
    data-testid="ticket-workspace-rail"
  >
    <NextButton
      v-tooltip.right="$t('SERVICEDESK_TICKET_PANEL.WORKSPACE.EXPAND')"
      :aria-label="$t('SERVICEDESK_TICKET_PANEL.WORKSPACE.EXPAND')"
      icon="i-lucide-panel-left-open"
      ghost
      slate
      sm
      data-testid="ticket-workspace-expand"
      @click="toggleProperties"
    />
  </div>
</template>
