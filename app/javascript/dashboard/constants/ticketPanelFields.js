// Fields the left column of a ticket can show (all of them by default), in the account's chosen order
// (Settings > Ticket fields).
// The requester is always shown first. Due date and problem only appear on tasks and incidents.
export const TICKET_PANEL_FIELDS = [
  'assignee',
  'team',
  'followers',
  'ticket_type',
  'priority',
  'labels',
];

// Custom ticket fields (conversation custom attributes) are stored as "attr:<attribute_key>".
export const CUSTOM_FIELD_PREFIX = 'attr:';
export const customFieldId = attributeKey =>
  `${CUSTOM_FIELD_PREFIX}${attributeKey}`;

// Literal class names so Tailwind generates them; fields past the last one keep their relative order at the end.
export const ORDER_CLASSES = [
  'order-1',
  'order-2',
  'order-3',
  'order-4',
  'order-5',
  'order-6',
  'order-7',
  'order-8',
  'order-9',
  'order-10',
  'order-11',
  'order-12',
];
