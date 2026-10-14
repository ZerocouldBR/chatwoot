<script setup>
import Select from 'dashboard/components-next/select/Select.vue';
import { computed, onMounted, ref, toRaw, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useAlert } from 'dashboard/composables';
import { useStore } from 'dashboard/composables/store';
import TicketRulesAPI from 'dashboard/api/ticketRules';
import SettingsLayout from '../SettingsLayout.vue';
import BaseSettingsHeader from '../components/BaseSettingsHeader.vue';
import Button from 'dashboard/components-next/button/Button.vue';
import RuleValueInput from './RuleValueInput.vue';
import {
  ACTIONS,
  OPERATORS_WITHOUT_VALUE,
  PLACEHOLDERS,
  RULE_KINDS,
  conditionCatalog,
} from 'dashboard/constants/ticketRules';

const props = defineProps({
  kind: {
    type: String,
    required: true,
  },
});

// Values that read naturally as "(none)" in a condition, e.g. "assignee is (none)".
const NONE_INPUTS = ['priority', 'ticket_type', 'team', 'agent'];
const DEFAULT_HOURS = '24';

const { t } = useI18n();
const store = useStore();

const rules = ref([]);
const editing = ref(null);
const isSaving = ref(false);

const kindKey = computed(() => props.kind.toUpperCase());
const conditions = computed(() => conditionCatalog(props.kind));
const conditionFields = computed(() => Object.keys(conditions.value));
const actionFields = Object.keys(ACTIONS);
// Triggers may not close tickets (Zendesk), so they get their own status list.
const actionInput = field =>
  field === 'status' && props.kind === RULE_KINDS.TRIGGER
    ? 'settable_status'
    : ACTIONS[field].input;

const blankCondition = () => {
  const field = conditionFields.value[0];
  return {
    field,
    operator: conditions.value[field].operators[0],
    value: '',
  };
};

const load = async () => {
  const { data } = await TicketRulesAPI.list(props.kind);
  rules.value = data.payload;
};

const edit = rule => {
  editing.value = {
    ...structuredClone(toRaw(rule)),
    conditions: { all: [], any: [], ...rule.conditions },
  };
};

const startNew = () =>
  edit({
    title: '',
    description: '',
    active: true,
    conditions: { all: [blankCondition()], any: [] },
    actions: [{ field: 'add_tags', value: '' }],
  });

const onConditionFieldChange = condition => {
  const config = conditions.value[condition.field];
  condition.operator = config.operators[0];
  condition.value = config.input === 'hours' ? DEFAULT_HOURS : '';
  if (config.input === 'hours') condition.business_hours = false;
  else delete condition.business_hours;
};

const onActionFieldChange = action => {
  action.value =
    ACTIONS[action.field].input === 'email'
      ? { subject: '', body: '', team_id: '', user_id: '' }
      : '';
};

const addCondition = group =>
  editing.value.conditions[group].push(blankCondition());
const removeCondition = (group, condition) => {
  editing.value.conditions[group] = editing.value.conditions[group].filter(
    item => item !== condition
  );
};
const addAction = () =>
  editing.value.actions.push({ field: 'add_tags', value: '' });
const removeAction = action => {
  editing.value.actions = editing.value.actions.filter(item => item !== action);
};

const payload = () => ({
  title: editing.value.title,
  description: editing.value.description,
  active: editing.value.active,
  conditions: editing.value.conditions,
  actions: editing.value.actions,
  ...(props.kind === RULE_KINDS.TRIGGER && {
    delay_minutes: editing.value.delay_minutes || null,
  }),
});

const save = async () => {
  isSaving.value = true;
  try {
    const { data } = editing.value.id
      ? await TicketRulesAPI.updateRule(editing.value.id, payload())
      : await TicketRulesAPI.createRule(props.kind, payload());
    edit(data);
    await load();
    useAlert(t('TICKET_RULES.SAVED'));
  } catch (error) {
    useAlert(error?.response?.data?.message || t('TICKET_RULES.ERROR'));
  } finally {
    isSaving.value = false;
  }
};

const remove = async () => {
  await TicketRulesAPI.delete(editing.value.id);
  editing.value = null;
  await load();
  useAlert(t('TICKET_RULES.DELETED'));
};

const move = async (rule, offset) => {
  const ids = rules.value.map(item => item.id);
  const index = ids.indexOf(rule.id);
  const target = index + offset;
  if (target < 0 || target >= ids.length) return;
  [ids[index], ids[target]] = [ids[target], ids[index]];
  const { data } = await TicketRulesAPI.reorder(props.kind, ids);
  rules.value = data.payload;
};

watch(
  () => props.kind,
  () => {
    editing.value = null;
    load();
  }
);

onMounted(() => {
  load();
  store.dispatch('teams/get');
  store.dispatch('agents/get');
  store.dispatch('inboxes/get');
});
</script>

<template>
  <SettingsLayout :no-records-found="false">
    <template #header>
      <BaseSettingsHeader
        :title="$t(`TICKET_RULES.${kindKey}.TITLE`)"
        :description="$t(`TICKET_RULES.${kindKey}.DESCRIPTION`)"
        :feature-name="kind"
      >
        <template #actions>
          <Button
            :label="$t(`TICKET_RULES.${kindKey}.NEW`)"
            icon="i-lucide-plus"
            @click="startNew"
          />
        </template>
      </BaseSettingsHeader>
    </template>
    <template #body>
      <div class="flex flex-col gap-6 mt-4 xl:flex-row">
        <ol class="flex flex-col gap-1 xl:w-72 shrink-0">
          <li v-if="!rules.length" class="text-sm text-n-slate-11">
            {{ $t(`TICKET_RULES.${kindKey}.EMPTY`) }}
          </li>
          <li
            v-for="(rule, index) in rules"
            :key="rule.id"
            class="flex items-center gap-1"
          >
            <button
              type="button"
              class="flex items-center flex-1 min-w-0 gap-2 px-3 py-2 text-sm rounded-lg text-start text-n-slate-12"
              :class="
                editing?.id === rule.id
                  ? 'bg-n-alpha-2 font-medium'
                  : 'hover:bg-n-alpha-1'
              "
              @click="edit(rule)"
            >
              <span class="truncate">{{ index + 1 }}. {{ rule.title }}</span>
              <span v-if="!rule.active" class="text-xs text-n-slate-10">
                {{ $t('TICKET_RULES.INACTIVE') }}
              </span>
            </button>
            <Button
              icon="i-lucide-arrow-up"
              ghost
              slate
              xs
              :aria-label="$t('TICKET_RULES.MOVE_UP')"
              @click="move(rule, -1)"
            />
            <Button
              icon="i-lucide-arrow-down"
              ghost
              slate
              xs
              :aria-label="$t('TICKET_RULES.MOVE_DOWN')"
              @click="move(rule, 1)"
            />
          </li>
        </ol>

        <form
          v-if="editing"
          data-testid="ticket-rule-form"
          class="flex flex-col flex-1 min-w-0 gap-5"
          @submit.prevent="save"
        >
          <div class="grid gap-4 md:grid-cols-2">
            <label class="flex flex-col gap-1 text-sm text-n-slate-12">
              {{ $t('TICKET_RULES.NAME') }}
              <input
                v-model="editing.title"
                data-testid="rule-title"
                type="text"
                required
              />
            </label>
            <label class="flex flex-col gap-1 text-sm text-n-slate-12">
              {{ $t('TICKET_RULES.DESCRIPTION_FIELD') }}
              <input v-model="editing.description" type="text" />
            </label>
          </div>
          <label
            v-if="kind === RULE_KINDS.TRIGGER"
            class="flex flex-wrap items-center gap-2 text-sm text-n-slate-12"
          >
            {{ $t('TICKET_RULES.DELAY') }}
            <input
              v-model.number="editing.delay_minutes"
              data-testid="rule-delay"
              type="number"
              min="1"
              class="w-24 !mb-0"
            />
            <span class="text-xs text-n-slate-11">
              {{ $t('TICKET_RULES.DELAY_HINT') }}
            </span>
          </label>
          <label class="flex items-center gap-2 text-sm text-n-slate-12">
            <input v-model="editing.active" type="checkbox" />
            {{ $t('TICKET_RULES.ACTIVE') }}
          </label>

          <section
            v-for="group in ['all', 'any']"
            :key="group"
            class="flex flex-col gap-2"
            :data-testid="`rule-conditions-${group}`"
          >
            <h3 class="text-sm font-medium text-n-slate-12">
              {{ $t(`TICKET_RULES.${group.toUpperCase()}`) }}
            </h3>
            <div
              v-for="(condition, index) in editing.conditions[group]"
              :key="index"
              class="flex flex-wrap items-center gap-2"
              data-testid="rule-condition"
            >
              <Select
                v-model="condition.field"
                data-testid="rule-condition-field"
                :aria-label="$t('TICKET_RULES.FIELDS.status')"
                :options="
                  conditionFields.map(field => ({
                    value: field,
                    label: $t(`TICKET_RULES.FIELDS.${field}`),
                  }))
                "
                @update:model-value="onConditionFieldChange(condition)"
              />
              <Select
                v-model="condition.operator"
                data-testid="rule-condition-operator"
                :options="
                  conditions[condition.field].operators.map(operator => ({
                    value: operator,
                    label: $t(`TICKET_RULES.OPERATORS.${operator}`),
                  }))
                "
              />
              <RuleValueInput
                v-if="!OPERATORS_WITHOUT_VALUE.includes(condition.operator)"
                v-model="condition.value"
                :input="conditions[condition.field].input"
                :allow-none="
                  NONE_INPUTS.includes(conditions[condition.field].input)
                "
              />
              <label
                v-if="conditions[condition.field].input === 'hours'"
                class="flex items-center gap-1 text-sm text-n-slate-11"
              >
                <input v-model="condition.business_hours" type="checkbox" />
                {{ $t('TICKET_RULES.BUSINESS_HOURS') }}
              </label>
              <Button
                type="button"
                icon="i-lucide-x"
                ghost
                slate
                xs
                :aria-label="$t('TICKET_RULES.REMOVE')"
                @click="removeCondition(group, condition)"
              />
            </div>
            <div>
              <Button
                type="button"
                :label="$t('TICKET_RULES.ADD_CONDITION')"
                link
                sm
                @click="addCondition(group)"
              />
            </div>
          </section>

          <section class="flex flex-col gap-3" data-testid="rule-actions">
            <h3 class="text-sm font-medium text-n-slate-12">
              {{ $t('TICKET_RULES.ACTIONS') }}
            </h3>
            <div
              v-for="(action, index) in editing.actions"
              :key="index"
              class="flex flex-col gap-2"
              data-testid="rule-action"
            >
              <div class="flex flex-wrap items-center gap-2">
                <Select
                  v-model="action.field"
                  data-testid="rule-action-field"
                  :aria-label="$t('TICKET_RULES.ACTIONS')"
                  :options="
                    actionFields.map(field => ({
                      value: field,
                      label: $t(`TICKET_RULES.ACTION_FIELDS.${field}`),
                    }))
                  "
                  @update:model-value="onActionFieldChange(action)"
                />
                <RuleValueInput
                  v-if="ACTIONS[action.field].input !== 'email'"
                  v-model="action.value"
                  :input="actionInput(action.field)"
                  :allow-none="
                    ['team', 'agent'].includes(ACTIONS[action.field].input)
                  "
                />
                <RuleValueInput
                  v-else-if="ACTIONS[action.field].target === 'team'"
                  v-model="action.value.team_id"
                  input="team"
                  allow-none
                  :none-label="$t('TICKET_RULES.VALUES.TICKET_GROUP')"
                />
                <RuleValueInput
                  v-else-if="ACTIONS[action.field].target === 'agent'"
                  v-model="action.value.user_id"
                  input="agent"
                />
                <Button
                  type="button"
                  icon="i-lucide-x"
                  ghost
                  slate
                  xs
                  :aria-label="$t('TICKET_RULES.REMOVE')"
                  @click="removeAction(action)"
                />
              </div>
              <div
                v-if="ACTIONS[action.field].input === 'email'"
                class="flex flex-col gap-2 ps-4 border-s-2 border-n-weak"
              >
                <input
                  v-model="action.value.subject"
                  data-testid="rule-email-subject"
                  type="text"
                  required
                  :placeholder="$t('TICKET_RULES.SUBJECT')"
                  :aria-label="$t('TICKET_RULES.SUBJECT')"
                />
                <textarea
                  v-model="action.value.body"
                  data-testid="rule-email-body"
                  rows="4"
                  required
                  :placeholder="$t('TICKET_RULES.BODY')"
                  :aria-label="$t('TICKET_RULES.BODY')"
                />
                <p class="text-xs text-n-slate-11">
                  {{ $t('TICKET_RULES.PLACEHOLDERS') }}:
                  {{ PLACEHOLDERS.join(' ') }}
                </p>
              </div>
            </div>
            <div>
              <Button
                type="button"
                :label="$t('TICKET_RULES.ADD_ACTION')"
                link
                sm
                @click="addAction"
              />
            </div>
          </section>

          <div class="flex gap-2">
            <Button
              type="submit"
              :label="$t('TICKET_RULES.SAVE')"
              :is-loading="isSaving"
            />
            <Button
              v-if="editing.id"
              type="button"
              :label="$t('TICKET_RULES.DELETE')"
              ruby
              faded
              @click="remove"
            />
          </div>
        </form>
      </div>
    </template>
  </SettingsLayout>
</template>
