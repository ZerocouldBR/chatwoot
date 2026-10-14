<script setup>
import Select from 'dashboard/components-next/select/Select.vue';
import { computed, onMounted, ref, toRaw } from 'vue';
import { useI18n } from 'vue-i18n';
import { useAlert } from 'dashboard/composables';
import { useMapGetter, useStore } from 'dashboard/composables/store';
import SlaAPI from 'dashboard/api/sla';
import SettingsLayout from '../SettingsLayout.vue';
import BaseSettingsHeader from '../components/BaseSettingsHeader.vue';
import Button from 'dashboard/components-next/button/Button.vue';
import { AGENT_SETTABLE_STATUSES } from 'dashboard/constants/ticketStatuses';

const METRICS = [
  'first_reply_time',
  'next_reply_time',
  'periodic_update',
  'pausable_update',
  'requester_wait_time',
  'agent_work_time',
  'total_resolution_time',
];
const PRIORITIES = ['urgent', 'high', 'medium', 'low'];
const TICKET_TYPES = ['question', 'incident', 'problem', 'task'];
const FIELDS = [
  'priority',
  'status',
  'ticket_type',
  'team_id',
  'inbox_id',
  'labels',
];
const OPERATORS = ['is', 'is_not'];
const LABEL_OPERATORS = ['includes', 'not_includes'];

const { t } = useI18n();
const store = useStore();
const teams = useMapGetter('teams/getTeams');
const inboxes = useMapGetter('inboxes/getInboxes');

const policies = ref([]);
const editing = ref(null);
// targets keyed "metric:priority" -> minutes, plus business hours per metric, for the grid.
const minutes = ref({});
const businessHours = ref({});
const isSaving = ref(false);

const valueOptions = field => {
  switch (field) {
    case 'priority':
      return PRIORITIES.map(id => ({
        id,
        name: t(`TICKET_SLA.PRIORITIES.${id}`),
      }));
    case 'status':
      return AGENT_SETTABLE_STATUSES.map(id => ({
        id,
        name: t(`CONVERSATION.TICKET_STATUS.${id}`),
      }));
    case 'ticket_type':
      return TICKET_TYPES.map(id => ({
        id,
        name: t(`CONVERSATION.TICKET_FIELDS.TYPES.${id}`),
      }));
    case 'team_id':
      return teams.value.map(team => ({
        id: String(team.id),
        name: team.name,
      }));
    case 'inbox_id':
      return inboxes.value.map(inbox => ({
        id: String(inbox.id),
        name: inbox.name,
      }));
    default:
      return null;
  }
};

const loadGrid = policy => {
  minutes.value = {};
  businessHours.value = {};
  (policy.targets || []).forEach(target => {
    minutes.value[`${target.metric}:${target.priority}`] = target.minutes;
    businessHours.value[target.metric] = target.business_hours;
  });
};

const edit = policy => {
  editing.value = {
    ...structuredClone(toRaw(policy)),
    filter: { all: [], any: [], ...policy.filter },
  };
  loadGrid(policy);
};

const startNew = () =>
  edit({ name: '', description: '', filter: {}, targets: [] });

const load = async () => {
  const { data } = await SlaAPI.get();
  policies.value = data.payload;
};

const addCondition = group => {
  editing.value.filter[group].push({
    field: 'priority',
    operator: 'is',
    value: 'urgent',
  });
};

const operatorsFor = field =>
  field === 'labels' ? LABEL_OPERATORS : OPERATORS;

const onFieldChange = condition => {
  condition.operator = operatorsFor(condition.field)[0];
  condition.value = '';
};

const removeCondition = (group, condition) => {
  editing.value.filter[group] = editing.value.filter[group].filter(
    item => item !== condition
  );
};

const targets = computed(() =>
  METRICS.flatMap(metric =>
    PRIORITIES.filter(
      priority => minutes.value[`${metric}:${priority}`] > 0
    ).map(priority => ({
      metric,
      priority,
      minutes: Number(minutes.value[`${metric}:${priority}`]),
      business_hours: !!businessHours.value[metric],
    }))
  )
);

const save = async () => {
  isSaving.value = true;
  const payload = {
    sla_policy: {
      name: editing.value.name,
      description: editing.value.description,
      filter: editing.value.filter,
      targets: targets.value,
    },
  };
  try {
    const { data } = editing.value.id
      ? await SlaAPI.update(editing.value.id, payload)
      : await SlaAPI.create(payload);
    edit(data);
    await load();
    useAlert(t('TICKET_SLA.SAVED'));
  } catch (error) {
    useAlert(error?.response?.data?.message || t('TICKET_SLA.ERROR'));
  } finally {
    isSaving.value = false;
  }
};

const remove = async () => {
  await SlaAPI.delete(editing.value.id);
  editing.value = null;
  await load();
  useAlert(t('TICKET_SLA.DELETED'));
};

const move = async (policy, offset) => {
  const ids = policies.value.map(item => item.id);
  const index = ids.indexOf(policy.id);
  const target = index + offset;
  if (target < 0 || target >= ids.length) return;
  [ids[index], ids[target]] = [ids[target], ids[index]];
  const { data } = await SlaAPI.reorder(ids);
  policies.value = data.payload;
};

onMounted(() => {
  load();
  store.dispatch('teams/get');
  store.dispatch('inboxes/get');
});
</script>

<template>
  <SettingsLayout :no-records-found="false">
    <template #header>
      <BaseSettingsHeader
        :title="$t('TICKET_SLA.TITLE')"
        :description="$t('TICKET_SLA.DESCRIPTION')"
        feature-name="sla"
      >
        <template #actions>
          <Button
            :label="$t('TICKET_SLA.NEW')"
            icon="i-lucide-plus"
            @click="startNew"
          />
        </template>
      </BaseSettingsHeader>
    </template>
    <template #body>
      <div class="flex flex-col gap-6 mt-4 xl:flex-row">
        <ol class="flex flex-col gap-1 xl:w-64 shrink-0">
          <li v-if="!policies.length" class="text-sm text-n-slate-11">
            {{ $t('TICKET_SLA.EMPTY') }}
          </li>
          <li
            v-for="(policy, index) in policies"
            :key="policy.id"
            class="flex items-center gap-1"
          >
            <button
              type="button"
              class="flex-1 min-w-0 px-3 py-2 text-sm truncate rounded-lg text-start text-n-slate-12"
              :class="
                editing?.id === policy.id
                  ? 'bg-n-alpha-2 font-medium'
                  : 'hover:bg-n-alpha-1'
              "
              @click="edit(policy)"
            >
              {{ index + 1 }}. {{ policy.name }}
            </button>
            <Button
              icon="i-lucide-arrow-up"
              ghost
              slate
              xs
              :aria-label="$t('TICKET_SLA.MOVE_UP')"
              @click="move(policy, -1)"
            />
            <Button
              icon="i-lucide-arrow-down"
              ghost
              slate
              xs
              :aria-label="$t('TICKET_SLA.MOVE_DOWN')"
              @click="move(policy, 1)"
            />
          </li>
        </ol>

        <form
          v-if="editing"
          data-testid="sla-policy-form"
          class="flex flex-col flex-1 min-w-0 gap-5"
          @submit.prevent="save"
        >
          <div class="grid gap-4 md:grid-cols-2">
            <label class="flex flex-col gap-1 text-sm text-n-slate-12">
              {{ $t('TICKET_SLA.NAME') }}
              <input
                v-model="editing.name"
                data-testid="sla-name"
                type="text"
                required
              />
            </label>
            <label class="flex flex-col gap-1 text-sm text-n-slate-12">
              {{ $t('TICKET_SLA.DESCRIPTION_FIELD') }}
              <input v-model="editing.description" type="text" />
            </label>
          </div>

          <section class="flex flex-col gap-3">
            <div>
              <h3 class="text-sm font-medium text-n-slate-12">
                {{ $t('TICKET_SLA.CONDITIONS') }}
              </h3>
              <p class="text-xs text-n-slate-11">
                {{ $t('TICKET_SLA.CONDITIONS_HINT') }}
              </p>
            </div>
            <div
              v-for="group in ['all', 'any']"
              :key="group"
              class="flex flex-col gap-2"
            >
              <span class="text-xs font-medium text-n-slate-11">
                {{ $t(`TICKET_SLA.${group.toUpperCase()}`) }}
              </span>
              <div
                v-for="(condition, index) in editing.filter[group]"
                :key="index"
                class="flex flex-wrap items-center gap-2"
              >
                <Select
                  v-model="condition.field"
                  :aria-label="$t('TICKET_SLA.CONDITIONS')"
                  :options="
                    FIELDS.map(field => ({
                      value: field,
                      label: $t(`TICKET_SLA.FIELDS.${field}`),
                    }))
                  "
                  @update:model-value="onFieldChange(condition)"
                />
                <Select
                  v-model="condition.operator"
                  :options="
                    operatorsFor(condition.field).map(operator => ({
                      value: operator,
                      label: $t(`TICKET_SLA.OPERATORS.${operator}`),
                    }))
                  "
                />
                <Select
                  v-if="valueOptions(condition.field)"
                  v-model="condition.value"
                  :aria-label="$t('TICKET_SLA.VALUE')"
                  :options="
                    valueOptions(condition.field).map(option => ({
                      value: option.id,
                      label: option.name,
                    }))
                  "
                />
                <input
                  v-else
                  v-model="condition.value"
                  type="text"
                  :aria-label="$t('TICKET_SLA.VALUE')"
                />
                <Button
                  type="button"
                  icon="i-lucide-x"
                  ghost
                  slate
                  xs
                  :aria-label="$t('TICKET_SLA.REMOVE')"
                  @click="removeCondition(group, condition)"
                />
              </div>
              <div>
                <Button
                  type="button"
                  :label="$t('TICKET_SLA.ADD_CONDITION')"
                  link
                  sm
                  @click="addCondition(group)"
                />
              </div>
            </div>
          </section>

          <section class="flex flex-col gap-2 overflow-x-auto">
            <h3 class="text-sm font-medium text-n-slate-12">
              {{ $t('TICKET_SLA.TARGETS') }}
            </h3>
            <table class="text-sm" data-testid="sla-targets">
              <thead>
                <tr class="text-xs text-n-slate-11">
                  <th class="py-2 font-medium text-start">
                    {{ $t('TICKET_SLA.METRIC') }}
                  </th>
                  <th
                    v-for="priority in PRIORITIES"
                    :key="priority"
                    class="px-2 py-2 font-medium"
                  >
                    {{ $t(`TICKET_SLA.PRIORITIES.${priority}`) }}
                  </th>
                  <th class="px-2 py-2 font-medium">
                    {{ $t('TICKET_SLA.BUSINESS_HOURS') }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="metric in METRICS"
                  :key="metric"
                  class="border-t border-n-weak"
                >
                  <td class="py-2 pe-3 text-n-slate-12">
                    {{ $t(`TICKET_SLA.METRICS.${metric}`) }}
                  </td>
                  <td
                    v-for="priority in PRIORITIES"
                    :key="priority"
                    class="px-2 py-2"
                  >
                    <input
                      v-model.number="minutes[`${metric}:${priority}`]"
                      :data-testid="`sla-target-${metric}-${priority}`"
                      type="number"
                      min="1"
                      class="w-20"
                      :aria-label="`${$t(`TICKET_SLA.METRICS.${metric}`)} ${$t(`TICKET_SLA.PRIORITIES.${priority}`)}`"
                    />
                  </td>
                  <td class="px-2 py-2 text-center">
                    <input
                      v-model="businessHours[metric]"
                      type="checkbox"
                      :aria-label="`${$t('TICKET_SLA.BUSINESS_HOURS')} ${$t(`TICKET_SLA.METRICS.${metric}`)}`"
                    />
                  </td>
                </tr>
              </tbody>
            </table>
          </section>

          <div class="flex gap-2">
            <Button
              type="submit"
              :label="$t('TICKET_SLA.SAVE')"
              :is-loading="isSaving"
            />
            <Button
              v-if="editing.id"
              type="button"
              :label="$t('TICKET_SLA.DELETE')"
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
