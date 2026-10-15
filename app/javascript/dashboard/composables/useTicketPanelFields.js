import { computed } from 'vue';
import { useMapGetter } from 'dashboard/composables/store';
import {
  TICKET_PANEL_FIELDS,
  ORDER_CLASSES,
} from 'dashboard/constants/ticketPanelFields';

// Which ticket fields the agent sees in the left column, and in which order.
export function useTicketPanelFields() {
  const accountId = useMapGetter('getCurrentAccountId');
  const getAccount = useMapGetter('accounts/getAccount');

  const fields = computed(
    () =>
      getAccount.value(accountId.value)?.settings?.ticket_panel_fields ||
      TICKET_PANEL_FIELDS
  );

  const fieldClass = field => {
    const index = fields.value.indexOf(field);
    if (index === -1) return 'hidden';
    return ORDER_CLASSES[index] || 'order-last';
  };

  return { fields, fieldClass };
}
