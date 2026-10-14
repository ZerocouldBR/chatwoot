<script setup>
// ServiceDesk: política de abertura de ticket por ligação (ops.ticket_open_rules). Vale a primeira regra ativa, na
// ordem, que casa direção e fila. Regra removida aqui é desativada no sd-ops (não apagada).
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import Input from 'dashboard/components-next/input/Input.vue';
import Select from 'dashboard/components-next/select/Select.vue';
import Switch from 'dashboard/components-next/switch/Switch.vue';
import Button from 'dashboard/components-next/button/Button.vue';

const model = defineModel({ type: Array, default: () => [] });
const { t } = useI18n();

const opts = (prefix, values) =>
  values.map(v => ({
    value: v,
    label: t(`SD_TELEPHONY.RULES.${prefix}.${(v || 'ANY').toUpperCase()}`),
  }));
const directions = computed(() =>
  opts('DIRECTIONS', ['', 'receptivo', 'ativo', 'interno'])
);
const modes = computed(() =>
  opts('MODES', ['all', 'answered', 'missed', 'none'])
);
const reuses = computed(() => opts('REUSES', ['reuse_open', 'new', 'ask']));
const priorities = computed(() =>
  opts('PRIORITIES', ['urgente', 'alta', 'normal', 'baixa'])
);

const setRow = (i, patch) => {
  const rows = model.value.map(r => ({ ...r }));
  rows[i] = { ...rows[i], ...patch };
  model.value = rows;
};
const add = () => {
  const sort = Math.max(0, ...model.value.map(r => r.sort || 0)) + 10;
  model.value = [
    ...model.value,
    {
      name: '',
      sort,
      direction: null,
      queue_pattern: null,
      mode: 'all',
      reuse: 'reuse_open',
      reuse_window_hours: 24,
      default_priority: 'normal',
      active: true,
    },
  ];
};
const remove = i => {
  model.value = model.value.filter((_, j) => j !== i);
};
</script>

<template>
  <div class="flex flex-col gap-3" data-test="open-rules">
    <div
      v-for="(rule, i) in model"
      :key="rule.id || `n${i}`"
      class="grid grid-cols-2 lg:grid-cols-4 gap-2 p-3 rounded-lg border border-n-weak"
      :class="{ 'opacity-60': !rule.active }"
    >
      <label
        class="flex flex-col gap-1 col-span-2 text-label-small text-n-slate-11"
      >
        {{ t('SD_TELEPHONY.RULES.NAME') }}
        <Input
          :model-value="rule.name"
          size="sm"
          @update:model-value="v => setRow(i, { name: v })"
        />
      </label>
      <label class="flex flex-col gap-1 text-label-small text-n-slate-11">
        {{ t('SD_TELEPHONY.RULES.SORT') }}
        <Input
          type="number"
          size="sm"
          :model-value="rule.sort"
          @update:model-value="v => setRow(i, { sort: Number(v) || 0 })"
        />
      </label>
      <label class="flex items-center gap-2 text-label-small text-n-slate-11">
        <Switch
          :model-value="rule.active"
          @update:model-value="v => setRow(i, { active: v })"
        />
        {{ t('SD_TELEPHONY.RULES.ACTIVE') }}
      </label>
      <label class="flex flex-col gap-1 text-label-small text-n-slate-11">
        {{ t('SD_TELEPHONY.RULES.DIRECTION') }}
        <Select
          :model-value="rule.direction || ''"
          :options="directions"
          @update:model-value="v => setRow(i, { direction: v || null })"
        />
      </label>
      <label class="flex flex-col gap-1 text-label-small text-n-slate-11">
        {{ t('SD_TELEPHONY.RULES.QUEUE_PATTERN') }}
        <Input
          :model-value="rule.queue_pattern || ''"
          size="sm"
          :placeholder="t('SD_TELEPHONY.RULES.QUEUE_PATTERN_PLACEHOLDER')"
          @update:model-value="v => setRow(i, { queue_pattern: v || null })"
        />
      </label>
      <label class="flex flex-col gap-1 text-label-small text-n-slate-11">
        {{ t('SD_TELEPHONY.RULES.MODE') }}
        <Select
          :model-value="rule.mode"
          :options="modes"
          @update:model-value="v => setRow(i, { mode: v })"
        />
      </label>
      <label class="flex flex-col gap-1 text-label-small text-n-slate-11">
        {{ t('SD_TELEPHONY.RULES.REUSE') }}
        <Select
          :model-value="rule.reuse"
          :options="reuses"
          @update:model-value="v => setRow(i, { reuse: v })"
        />
      </label>
      <label class="flex flex-col gap-1 text-label-small text-n-slate-11">
        {{ t('SD_TELEPHONY.RULES.WINDOW') }}
        <Input
          type="number"
          size="sm"
          :model-value="rule.reuse_window_hours"
          @update:model-value="
            v => setRow(i, { reuse_window_hours: Number(v) || 0 })
          "
        />
      </label>
      <label class="flex flex-col gap-1 text-label-small text-n-slate-11">
        {{ t('SD_TELEPHONY.RULES.PRIORITY') }}
        <Select
          :model-value="rule.default_priority"
          :options="priorities"
          @update:model-value="v => setRow(i, { default_priority: v })"
        />
      </label>
      <div class="flex items-end justify-end col-span-2 lg:col-span-2">
        <Button
          size="xs"
          variant="ghost"
          color="ruby"
          icon="i-lucide-trash-2"
          :label="t('SD_TELEPHONY.ACTIONS.REMOVE_ROW')"
          @click="remove(i)"
        />
      </div>
    </div>
    <Button
      class="w-fit"
      size="sm"
      variant="faded"
      color="slate"
      icon="i-lucide-plus"
      :label="t('SD_TELEPHONY.RULES.ADD')"
      @click="add"
    />
  </div>
</template>
