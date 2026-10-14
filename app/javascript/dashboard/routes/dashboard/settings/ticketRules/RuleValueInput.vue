<script setup>
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useMapGetter } from 'dashboard/composables/store';
import {
  CHANNELS,
  PRIORITIES,
  RULE_SETTABLE_STATUSES,
  SATISFACTIONS,
  STATUSES,
  TICKET_TYPES,
  VIAS,
} from 'dashboard/constants/ticketRules';

const props = defineProps({
  // Kind of value editor, from the conditions/actions catalogue.
  input: {
    type: String,
    required: true,
  },
  // Lets "(none)" (empty) be chosen, e.g. "priority is (none)".
  allowNone: {
    type: Boolean,
    default: false,
  },
  noneLabel: {
    type: String,
    default: '',
  },
});

const value = defineModel({ type: [String, Number], default: '' });

const { t } = useI18n();
const teams = useMapGetter('teams/getTeams');
const agents = useMapGetter('agents/getAgents');
const inboxes = useMapGetter('inboxes/getInboxes');

const valueLabel = key => t(`TICKET_RULES.VALUES.${key}`);
const fromKeys = (keys, label) => keys.map(id => ({ id, name: label(id) }));

const options = computed(() => {
  switch (props.input) {
    case 'status':
      return fromKeys(STATUSES, id => t(`CONVERSATION.TICKET_STATUS.${id}`));
    case 'settable_status':
      return fromKeys(RULE_SETTABLE_STATUSES, id =>
        t(`CONVERSATION.TICKET_STATUS.${id}`)
      );
    case 'priority':
      return fromKeys(PRIORITIES, id => t(`TICKET_SLA.PRIORITIES.${id}`));
    case 'ticket_type':
      return fromKeys(TICKET_TYPES, id =>
        t(`CONVERSATION.TICKET_FIELDS.TYPES.${id}`)
      );
    case 'team':
      return teams.value.map(team => ({
        id: String(team.id),
        name: team.name,
      }));
    case 'agent':
      return agents.value.map(agent => ({
        id: String(agent.id),
        name: agent.name,
      }));
    case 'inbox':
      return inboxes.value.map(inbox => ({
        id: String(inbox.id),
        name: inbox.name,
      }));
    case 'channel':
      return fromKeys(CHANNELS, id => t(`TICKET_RULES.VALUES.CHANNELS.${id}`));
    case 'ticket_event':
      return fromKeys(['created', 'updated'], valueLabel);
    case 'comment_kind':
      return fromKeys(['public', 'private', 'present'], valueLabel);
    case 'via':
      return fromKeys(VIAS, valueLabel);
    case 'satisfaction':
      return fromKeys(SATISFACTIONS, id =>
        t(`CONVERSATION.SATISFACTION.${id}`)
      );
    case 'boolean':
      return fromKeys(['true', 'false'], valueLabel);
    default:
      return null;
  }
});
</script>

<template>
  <span v-if="input === 'none'" />
  <select
    v-else-if="options"
    v-model="value"
    data-testid="rule-value"
    :aria-label="$t('TICKET_RULES.VALUE')"
  >
    <option v-if="allowNone" value="">
      {{ noneLabel || $t('TICKET_RULES.VALUES.NONE') }}
    </option>
    <option v-for="option in options" :key="option.id" :value="option.id">
      {{ option.name }}
    </option>
  </select>
  <input
    v-else
    v-model="value"
    data-testid="rule-value"
    :type="input === 'hours' ? 'number' : 'text'"
    :min="input === 'hours' ? 0 : undefined"
    :class="input === 'hours' ? 'w-24' : ''"
    :aria-label="$t('TICKET_RULES.VALUE')"
  />
</template>
