<script setup>
// ServiceDesk: horário comercial do tenant (ops.business_hours) e prazos de SLA por prioridade (ops.sla_policies),
// usados pelo SLA próprio do sd-ops e pelas tarefas de retorno. Um intervalo por dia (0 = segunda).
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import Input from 'dashboard/components-next/input/Input.vue';
import Switch from 'dashboard/components-next/switch/Switch.vue';
import { listToText, textToList } from '../settingsForm';

const hours = defineModel('hours', { type: Object, default: null });
const sla = defineModel('sla', { type: Array, default: () => [] });
const { t } = useI18n();

const DAYS = ['0', '1', '2', '3', '4', '5', '6'];
const schedule = computed(() => hours.value?.schedule || {});

const setHours = patch => {
  hours.value = { ...hours.value, ...patch };
};
const setDay = (day, win) => {
  const s = { ...schedule.value };
  if (win) s[day] = [win];
  else delete s[day];
  setHours({ schedule: s });
};
const toggleDay = (day, open) => setDay(day, open ? ['09:00', '18:00'] : null);
const setTime = (day, idx, v) => {
  const win = [...(schedule.value[day]?.[0] || ['09:00', '18:00'])];
  win[idx] = v;
  setDay(day, win);
};

const setPolicy = (i, patch) => {
  const rows = sla.value.map(r => ({ ...r }));
  rows[i] = { ...rows[i], ...patch };
  sla.value = rows;
};
const minutes = v => (v === '' || v === null ? null : Number(v));
</script>

<template>
  <div class="flex flex-col gap-6" data-test="hours-sla">
    <div v-if="hours" class="flex flex-col gap-3">
      <label
        class="flex flex-col gap-1 max-w-xs text-label-small text-n-slate-11"
      >
        {{ t('SD_TELEPHONY.HOURS.TIMEZONE') }}
        <Input
          :model-value="hours.timezone"
          size="sm"
          @update:model-value="v => setHours({ timezone: v })"
        />
      </label>
      <div class="grid gap-2">
        <div
          v-for="day in DAYS"
          :key="day"
          class="grid grid-cols-[8rem_auto_1fr] items-center gap-3"
          :data-test="`day-${day}`"
        >
          <span class="text-body-main text-n-slate-12">
            {{ t(`SD_TELEPHONY.HOURS.DAYS.D${day}`) }}
          </span>
          <Switch
            :model-value="!!schedule[day]"
            @update:model-value="v => toggleDay(day, v)"
          />
          <div v-if="schedule[day]" class="flex items-center gap-2">
            <Input
              type="time"
              size="sm"
              :model-value="schedule[day][0][0]"
              @update:model-value="v => setTime(day, 0, v)"
            />
            <span class="text-n-slate-11">{{
              t('SD_TELEPHONY.HOURS.TO')
            }}</span>
            <Input
              type="time"
              size="sm"
              :model-value="schedule[day][0][1]"
              @update:model-value="v => setTime(day, 1, v)"
            />
          </div>
          <span v-else class="text-body-main text-n-slate-11">
            {{ t('SD_TELEPHONY.HOURS.CLOSED') }}
          </span>
        </div>
      </div>
      <label class="flex flex-col gap-1 text-label-small text-n-slate-11">
        {{ t('SD_TELEPHONY.HOURS.HOLIDAYS') }}
        <Input
          :model-value="listToText(hours.holidays)"
          size="sm"
          :placeholder="t('SD_TELEPHONY.HOURS.HOLIDAYS_PLACEHOLDER')"
          @update:model-value="v => setHours({ holidays: textToList(v) })"
        />
      </label>
    </div>
    <div class="flex flex-col gap-2">
      <h5 class="text-heading-3 text-n-slate-12">
        {{ t('SD_TELEPHONY.HOURS.SLA_TITLE') }}
      </h5>
      <div
        class="grid grid-cols-[1fr_8rem_8rem_auto] gap-2 text-label-small text-n-slate-11"
      >
        <span>{{ t('SD_TELEPHONY.HOURS.POLICY') }}</span>
        <span>{{ t('SD_TELEPHONY.HOURS.FIRST_RESPONSE') }}</span>
        <span>{{ t('SD_TELEPHONY.HOURS.RESOLUTION') }}</span>
        <span>{{ t('SD_TELEPHONY.RULES.ACTIVE') }}</span>
      </div>
      <div
        v-for="(p, i) in sla"
        :key="p.id || i"
        class="grid grid-cols-[1fr_8rem_8rem_auto] gap-2 items-center"
      >
        <span class="text-body-main text-n-slate-12">
          {{ p.name }}
          <span v-if="p.priority" class="text-n-slate-11">
            ({{
              t(`SD_TELEPHONY.RULES.PRIORITIES.${p.priority.toUpperCase()}`)
            }})
          </span>
        </span>
        <Input
          type="number"
          size="sm"
          :model-value="p.first_response_min ?? ''"
          @update:model-value="
            v => setPolicy(i, { first_response_min: minutes(v) })
          "
        />
        <Input
          type="number"
          size="sm"
          :model-value="p.resolution_min ?? ''"
          @update:model-value="
            v => setPolicy(i, { resolution_min: minutes(v) })
          "
        />
        <Switch
          :model-value="p.active"
          @update:model-value="v => setPolicy(i, { active: v })"
        />
      </div>
      <p class="text-label-small text-n-slate-11">
        {{ t('SD_TELEPHONY.HOURS.SLA_HELP') }}
      </p>
    </div>
  </div>
</template>
