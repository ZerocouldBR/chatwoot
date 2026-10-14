<script setup>
// ServiceDesk: mapa editável em linhas (fila -> time, ramal -> time, time -> área interna). Os times vêm da conta.
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import Input from 'dashboard/components-next/input/Input.vue';
import Select from 'dashboard/components-next/select/Select.vue';
import Button from 'dashboard/components-next/button/Button.vue';
import { mapToRows, rowsToMap } from '../settingsForm';

const props = defineProps({
  fieldKey: { type: String, required: true },
  teamOptions: { type: Array, default: () => [] },
});
const model = defineModel({ type: Object, default: () => ({}) });
const { t } = useI18n();

const rows = ref(mapToRows(model.value));
watch(
  () => model.value,
  v => {
    if (JSON.stringify(rowsToMap(rows.value)) !== JSON.stringify(v || {}))
      rows.value = mapToRows(v);
  }
);
const sync = () => {
  model.value = rowsToMap(rows.value);
};

const keyIsTeam = computed(() => props.fieldKey === 'team_area_map');
const valueIsTeam = computed(() =>
  ['queue_team_map', 'branch_team_map'].includes(props.fieldKey)
);
const teamOpts = current => {
  const opts = props.teamOptions.map(n => ({ value: n, label: n }));
  if (current && !props.teamOptions.includes(current))
    opts.unshift({ value: current, label: current });
  return opts;
};
const header = computed(() => {
  const b = `SD_TELEPHONY.MAPS.${props.fieldKey.toUpperCase()}`;
  return { key: t(`${b}.KEY`), value: t(`${b}.VALUE`) };
});

const add = () => {
  rows.value.push({ key: '', value: '' });
};
const remove = i => {
  rows.value.splice(i, 1);
  sync();
};
</script>

<template>
  <div class="flex flex-col gap-2" :data-test="`map-${fieldKey}`">
    <div
      v-if="rows.length"
      class="grid grid-cols-[1fr_1fr_auto] gap-2 text-label-small text-n-slate-11"
    >
      <span>{{ header.key }}</span>
      <span>{{ header.value }}</span>
      <span class="w-8" />
    </div>
    <div
      v-for="(row, i) in rows"
      :key="i"
      class="grid grid-cols-[1fr_1fr_auto] gap-2 items-center"
    >
      <Select
        v-if="keyIsTeam"
        v-model="row.key"
        :options="teamOpts(row.key)"
        :placeholder="header.key"
        :aria-label="header.key"
        @update:model-value="sync"
      />
      <Input
        v-else
        v-model="row.key"
        size="sm"
        :placeholder="header.key"
        @blur="sync"
        @input="sync"
      />
      <Select
        v-if="valueIsTeam"
        v-model="row.value"
        :options="teamOpts(row.value)"
        :placeholder="header.value"
        :aria-label="header.value"
        @update:model-value="sync"
      />
      <Input
        v-else
        v-model="row.value"
        size="sm"
        :placeholder="header.value"
        @input="sync"
      />
      <Button
        icon="i-lucide-trash-2"
        size="sm"
        variant="ghost"
        color="ruby"
        :aria-label="t('SD_TELEPHONY.ACTIONS.REMOVE_ROW')"
        @click="remove(i)"
      />
    </div>
    <Button
      class="w-fit"
      size="sm"
      variant="faded"
      color="slate"
      icon="i-lucide-plus"
      :label="t('SD_TELEPHONY.ACTIONS.ADD_ROW')"
      @click="add"
    />
  </div>
</template>
