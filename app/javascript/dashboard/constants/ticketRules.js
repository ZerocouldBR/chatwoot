// Catalogue of Zendesk-style trigger and automation conditions and actions.
// Mirrors Tickets::Rules::Conditions and TicketRule on the backend.

export const RULE_KINDS = { TRIGGER: 'trigger', AUTOMATION: 'automation' };

const IDENTITY = ['is', 'is_not'];
const ORDERED = [...IDENTITY, 'less_than', 'greater_than'];
const CHANGES = ['changed', 'changed_to', 'changed_from', 'not_changed'];
const TEXT = ['contains', 'not_contains'];
const HOURS = ['is', 'less_than', 'greater_than'];

export const OPERATORS_WITHOUT_VALUE = ['changed', 'not_changed'];

// input: the kind of value editor (select options come from VALUE_SOURCES).
const COMMON_CONDITIONS = {
  status: { operators: ORDERED, changes: true, input: 'status' },
  priority: { operators: ORDERED, changes: true, input: 'priority' },
  ticket_type: { operators: IDENTITY, changes: true, input: 'ticket_type' },
  team_id: { operators: IDENTITY, changes: true, input: 'team' },
  assignee_id: { operators: IDENTITY, changes: true, input: 'agent' },
  inbox_id: { operators: IDENTITY, input: 'inbox' },
  channel: { operators: IDENTITY, input: 'channel' },
  labels: { operators: ['includes', 'not_includes'], input: 'text' },
  subject: { operators: TEXT, input: 'text' },
  satisfaction: { operators: IDENTITY, changes: true, input: 'satisfaction' },
};

const TRIGGER_CONDITIONS = {
  ticket: { operators: ['is'], input: 'ticket_event' },
  comment: { operators: ['is'], input: 'comment_kind' },
  comment_text: { operators: TEXT, input: 'text' },
  update_via: { operators: IDENTITY, input: 'via' },
  within_business_hours: { operators: ['is'], input: 'boolean' },
};

const HOURS_FIELDS = [
  'hours_since_created',
  'hours_since_updated',
  'hours_since_open',
  'hours_since_waiting_on_customer',
  'hours_since_on_hold',
  'hours_since_resolved',
  'hours_since_assigned',
  'hours_since_requester_update',
  'hours_since_assignee_update',
  'hours_until_due_date',
];

const AUTOMATION_CONDITIONS = Object.fromEntries(
  HOURS_FIELDS.map(field => [field, { operators: HOURS, input: 'hours' }])
);

export const conditionCatalog = kind => {
  if (kind === RULE_KINDS.TRIGGER) {
    const common = Object.fromEntries(
      Object.entries(COMMON_CONDITIONS).map(([field, config]) => [
        field,
        {
          ...config,
          operators: config.changes
            ? [...config.operators, ...CHANGES]
            : config.operators,
        },
      ])
    );
    return { ...TRIGGER_CONDITIONS, ...common };
  }
  return { ...COMMON_CONDITIONS, ...AUTOMATION_CONDITIONS };
};

// input: value editor; email actions take a subject and a body with placeholders.
export const ACTIONS = {
  status: { input: 'settable_status' },
  priority: { input: 'priority' },
  ticket_type: { input: 'ticket_type' },
  team_id: { input: 'team' },
  assignee_id: { input: 'agent' },
  add_tags: { input: 'text' },
  remove_tags: { input: 'text' },
  set_tags: { input: 'text' },
  add_cc: { input: 'text' },
  add_follower: { input: 'agent' },
  email_requester: { input: 'email' },
  email_requester_and_ccs: { input: 'email' },
  email_assignee: { input: 'email' },
  email_group: { input: 'email', target: 'team' },
  email_user: { input: 'email', target: 'agent' },
  notify_webhook: { input: 'text' },
  request_satisfaction: { input: 'none' },
  send_message: { input: 'textarea' },
};

export const STATUSES = [
  'new_ticket',
  'open',
  'waiting_on_customer',
  'on_hold',
  'resolved',
  'closed',
  'pending',
];
export const RULE_SETTABLE_STATUSES = [
  'open',
  'waiting_on_customer',
  'on_hold',
  'resolved',
  'closed',
];
export const PRIORITIES = ['low', 'medium', 'high', 'urgent'];
export const TICKET_TYPES = ['question', 'incident', 'problem', 'task'];
export const CHANNELS = [
  'email',
  'api',
  'web_widget',
  'whatsapp',
  'telegram',
  'sms',
  'facebook_page',
  'instagram',
  'twilio_sms',
  'line',
  'tiktok',
];
export const VIAS = ['agent', 'customer', 'rule', 'bot', 'system'];
export const SATISFACTIONS = ['unoffered', 'offered', 'good', 'bad'];
export const PLACEHOLDERS = [
  '{{ticket.id}}',
  '{{ticket.title}}',
  '{{ticket.status}}',
  '{{ticket.priority}}',
  '{{ticket.url}}',
  '{{ticket.group}}',
  '{{ticket.requester.name}}',
  '{{ticket.assignee.name}}',
  '{{ticket.latest_comment}}',
];
