import wootConstants from 'dashboard/constants/globals';

const { STATUS_TYPE } = wootConstants;

// Statuses that count as "not solved yet", mirroring Conversation::UNSOLVED_STATUSES.
export const UNSOLVED_STATUSES = [
  STATUS_TYPE.NEW,
  STATUS_TYPE.OPEN,
  STATUS_TYPE.WAITING_ON_CUSTOMER,
  STATUS_TYPE.ON_HOLD,
];

// Options shown in the ticket list status filter, in Zendesk order.
export const STATUS_FILTER_OPTIONS = [
  STATUS_TYPE.UNSOLVED,
  ...UNSOLVED_STATUSES,
  STATUS_TYPE.RESOLVED,
  STATUS_TYPE.CLOSED,
  STATUS_TYPE.PENDING,
  STATUS_TYPE.ALL,
];

// Statuses an agent can pick for a ticket (New and Closed are set by the system).
export const AGENT_SETTABLE_STATUSES = [
  STATUS_TYPE.OPEN,
  STATUS_TYPE.WAITING_ON_CUSTOMER,
  STATUS_TYPE.ON_HOLD,
  STATUS_TYPE.RESOLVED,
];

// Badge colours follow the Zendesk convention for each status.
export const STATUS_BADGE_CLASSES = {
  [STATUS_TYPE.NEW]: 'bg-n-amber-9',
  [STATUS_TYPE.OPEN]: 'bg-n-ruby-9',
  [STATUS_TYPE.WAITING_ON_CUSTOMER]: 'bg-n-blue-9',
  [STATUS_TYPE.ON_HOLD]: 'bg-n-slate-12',
  [STATUS_TYPE.RESOLVED]: 'bg-n-slate-9',
  [STATUS_TYPE.CLOSED]: 'bg-n-slate-6',
  [STATUS_TYPE.PENDING]: 'bg-n-iris-9',
};

export const STATUS_ICONS = {
  [STATUS_TYPE.OPEN]: 'i-lucide-redo',
  [STATUS_TYPE.WAITING_ON_CUSTOMER]: 'i-lucide-hourglass',
  [STATUS_TYPE.ON_HOLD]: 'i-lucide-pause',
  [STATUS_TYPE.RESOLVED]: 'i-lucide-check',
};
