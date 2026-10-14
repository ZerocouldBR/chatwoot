<script setup>
// ServiceDesk: ramal 55PBX -> agente da conta (ops.agent_phone_mappings). Define o responsável da ligação e o ramal
// usado no click-to-call. O e-mail do ramal na 55PBX só é preciso se for diferente do e-mail do agente.
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import Input from 'dashboard/components-next/input/Input.vue';
import Select from 'dashboard/components-next/select/Select.vue';
import Button from 'dashboard/components-next/button/Button.vue';

const props = defineProps({
  agents: { type: Array, default: () => [] },
});
const model = defineModel({ type: Array, default: () => [] });
const { t } = useI18n();

const agentOptions = computed(() =>
  props.agents.map(a => ({
    value: a.id,
    label: a.email ? `${a.name} (${a.email})` : a.name,
  }))
);

const optionsFor = row => {
  const opts = [...agentOptions.value];
  if (row.agent_email && !props.agents.some(a => a.id === row.chatwoot_user_id))
    opts.unshift({ value: row.chatwoot_user_id ?? '', label: row.agent_email });
  return opts;
};

const setRow = (i, patch) => {
  const rows = model.value.map(r => ({ ...r }));
  rows[i] = { ...rows[i], ...patch };
  model.value = rows;
};
const pickAgent = (i, id) => {
  const a = props.agents.find(x => x.id === Number(id));
  if (a) setRow(i, { chatwoot_user_id: a.id, agent_email: a.email });
};
const add = () => {
  model.value = [
    ...model.value,
    { branch: '', agent_email: '', chatwoot_user_id: null, pbx_email: null },
  ];
};
const remove = i => {
  model.value = model.value.filter((_, j) => j !== i);
};
</script>

<template>
  <div class="flex flex-col gap-2" data-test="agent-mappings">
    <div
      v-if="model.length"
      class="grid grid-cols-[7rem_1fr_1fr_auto] gap-2 text-label-small text-n-slate-11"
    >
      <span>{{ t('SD_TELEPHONY.MAPS.BRANCH') }}</span>
      <span>{{ t('SD_TELEPHONY.MAPS.AGENT') }}</span>
      <span>{{ t('SD_TELEPHONY.MAPS.PBX_EMAIL') }}</span>
      <span class="w-8" />
    </div>
    <div
      v-for="(row, i) in model"
      :key="i"
      class="grid grid-cols-[7rem_1fr_1fr_auto] gap-2 items-center"
      data-test="agent-mapping-row"
    >
      <Input
        :model-value="row.branch"
        size="sm"
        :placeholder="t('SD_TELEPHONY.MAPS.BRANCH')"
        @update:model-value="v => setRow(i, { branch: String(v).trim() })"
      />
      <Select
        :model-value="row.chatwoot_user_id ?? ''"
        :options="optionsFor(row)"
        :placeholder="t('SD_TELEPHONY.MAPS.PICK_AGENT')"
        :aria-label="t('SD_TELEPHONY.MAPS.AGENT')"
        @update:model-value="v => pickAgent(i, v)"
      />
      <Input
        :model-value="row.pbx_email || ''"
        size="sm"
        type="email"
        :placeholder="t('SD_TELEPHONY.MAPS.PBX_EMAIL_PLACEHOLDER')"
        @update:model-value="v => setRow(i, { pbx_email: v || null })"
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
      :label="t('SD_TELEPHONY.MAPS.ADD_BRANCH')"
      @click="add"
    />
  </div>
</template>
