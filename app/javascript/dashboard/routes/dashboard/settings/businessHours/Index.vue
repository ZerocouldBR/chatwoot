<script setup>
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useAlert } from 'dashboard/composables';
import BusinessSchedulesAPI from 'dashboard/api/businessSchedules';
import { timeZoneOptions } from '../inbox/helpers/businessHour';
import SettingsLayout from '../SettingsLayout.vue';
import BaseSettingsHeader from '../components/BaseSettingsHeader.vue';
import Button from 'dashboard/components-next/button/Button.vue';

const { t, tm } = useI18n();

const MINUTES_PER_HOUR = 60;
const DEFAULT_OPEN = 9 * MINUTES_PER_HOUR;
const DEFAULT_CLOSE = 18 * MINUTES_PER_HOUR;
const WEEKDAYS = [1, 2, 3, 4, 5];

const schedules = ref([]);
const editing = ref(null);
const isSaving = ref(false);
const timeZones = timeZoneOptions();
const dayNames = computed(() => tm('BUSINESS_HOURS.DAYS'));

const blankSchedule = () => ({
  name: '',
  time_zone: 'America/Sao_Paulo',
  is_default: !schedules.value.length,
  intervals: WEEKDAYS.map(day => ({
    day,
    start: DEFAULT_OPEN,
    end: DEFAULT_CLOSE,
  })),
  holidays: [],
});

const load = async () => {
  const { data } = await BusinessSchedulesAPI.get();
  schedules.value = data.payload;
  if (!editing.value) {
    editing.value = schedules.value[0]
      ? structuredClone(schedules.value[0])
      : blankSchedule();
  }
};

const edit = schedule => {
  editing.value = structuredClone(schedule);
};

const startNew = () => {
  editing.value = blankSchedule();
};

const intervalsFor = day =>
  editing.value.intervals.filter(interval => interval.day === day);

// <input type="time"> works with HH:MM; the API stores minutes from midnight.
const toTime = minutes =>
  `${String(Math.floor(minutes / MINUTES_PER_HOUR)).padStart(2, '0')}:${String(minutes % MINUTES_PER_HOUR).padStart(2, '0')}`;
const toMinutes = value => {
  const [hours, minutes] = value.split(':').map(Number);
  return hours * MINUTES_PER_HOUR + minutes;
};

const addInterval = day => {
  editing.value.intervals.push({
    day,
    start: DEFAULT_OPEN,
    end: DEFAULT_CLOSE,
  });
};

const removeInterval = interval => {
  editing.value.intervals = editing.value.intervals.filter(
    item => item !== interval
  );
};

const addHoliday = () => {
  editing.value.holidays.push({ name: '', start_date: '', end_date: '' });
};

const removeHoliday = holiday => {
  editing.value.holidays = editing.value.holidays.filter(
    item => item !== holiday
  );
};

const save = async () => {
  isSaving.value = true;
  const payload = { business_schedule: editing.value };
  try {
    const { data } = editing.value.id
      ? await BusinessSchedulesAPI.update(editing.value.id, payload)
      : await BusinessSchedulesAPI.create(payload);
    editing.value = data;
    await load();
    useAlert(t('BUSINESS_HOURS.SAVED'));
  } catch (error) {
    useAlert(t('BUSINESS_HOURS.ERROR'));
  } finally {
    isSaving.value = false;
  }
};

const remove = async () => {
  await BusinessSchedulesAPI.delete(editing.value.id);
  editing.value = null;
  await load();
  useAlert(t('BUSINESS_HOURS.DELETED'));
};

onMounted(load);
</script>

<template>
  <SettingsLayout :no-records-found="false">
    <template #header>
      <BaseSettingsHeader
        :title="$t('BUSINESS_HOURS.TITLE')"
        :description="$t('BUSINESS_HOURS.DESCRIPTION')"
        feature-name="business-hours"
      >
        <template #actions>
          <Button
            :label="$t('BUSINESS_HOURS.NEW')"
            icon="i-lucide-plus"
            @click="startNew"
          />
        </template>
      </BaseSettingsHeader>
    </template>
    <template #body>
      <div class="flex flex-col gap-6 mt-4 lg:flex-row">
        <ul class="flex flex-col gap-1 lg:w-56 shrink-0">
          <li v-if="!schedules.length" class="text-sm text-n-slate-11">
            {{ $t('BUSINESS_HOURS.EMPTY') }}
          </li>
          <li v-for="schedule in schedules" :key="schedule.id">
            <button
              type="button"
              class="flex items-center justify-between w-full gap-2 px-3 py-2 text-sm rounded-lg text-n-slate-12"
              :class="
                editing?.id === schedule.id
                  ? 'bg-n-alpha-2 font-medium'
                  : 'hover:bg-n-alpha-1'
              "
              @click="edit(schedule)"
            >
              <span class="truncate">{{ schedule.name }}</span>
              <span v-if="schedule.is_default" class="text-xs text-n-blue-11">
                {{ $t('BUSINESS_HOURS.DEFAULT_BADGE') }}
              </span>
            </button>
          </li>
        </ul>

        <form
          v-if="editing"
          data-testid="business-schedule-form"
          class="flex flex-col flex-1 gap-5"
          @submit.prevent="save"
        >
          <div class="grid gap-4 md:grid-cols-2">
            <label class="flex flex-col gap-1 text-sm text-n-slate-12">
              {{ $t('BUSINESS_HOURS.NAME') }}
              <input
                v-model="editing.name"
                data-testid="schedule-name"
                type="text"
                required
              />
            </label>
            <label class="flex flex-col gap-1 text-sm text-n-slate-12">
              {{ $t('BUSINESS_HOURS.TIME_ZONE') }}
              <select v-model="editing.time_zone" data-testid="schedule-tz">
                <option
                  v-for="zone in timeZones"
                  :key="zone.label"
                  :value="zone.value"
                >
                  {{ zone.label }}
                </option>
              </select>
            </label>
          </div>
          <label class="flex items-center gap-2 text-sm text-n-slate-12">
            <input v-model="editing.is_default" type="checkbox" />
            {{ $t('BUSINESS_HOURS.DEFAULT') }}
          </label>

          <section class="flex flex-col gap-2">
            <h3 class="text-sm font-medium text-n-slate-12">
              {{ $t('BUSINESS_HOURS.HOURS') }}
            </h3>
            <div
              v-for="(dayName, day) in dayNames"
              :key="day"
              class="flex flex-wrap items-center gap-3 py-2 border-b border-n-weak"
              :data-testid="`schedule-day-${day}`"
            >
              <span class="w-24 text-sm text-n-slate-12">{{ dayName }}</span>
              <span
                v-if="!intervalsFor(day).length"
                class="text-sm text-n-slate-11"
              >
                {{ $t('BUSINESS_HOURS.CLOSED') }}
              </span>
              <span
                v-for="(interval, index) in intervalsFor(day)"
                :key="index"
                class="flex items-center gap-1"
              >
                <input
                  type="time"
                  step="900"
                  :value="toTime(interval.start)"
                  @change="interval.start = toMinutes($event.target.value)"
                />
                <input
                  type="time"
                  step="900"
                  :value="toTime(interval.end)"
                  @change="interval.end = toMinutes($event.target.value)"
                />
                <Button
                  type="button"
                  icon="i-lucide-x"
                  ghost
                  slate
                  xs
                  :aria-label="$t('BUSINESS_HOURS.REMOVE')"
                  @click="removeInterval(interval)"
                />
              </span>
              <Button
                type="button"
                :label="$t('BUSINESS_HOURS.ADD_INTERVAL')"
                link
                sm
                @click="addInterval(day)"
              />
            </div>
          </section>

          <section class="flex flex-col gap-2">
            <h3 class="text-sm font-medium text-n-slate-12">
              {{ $t('BUSINESS_HOURS.HOLIDAYS') }}
            </h3>
            <div
              v-for="(holiday, index) in editing.holidays"
              :key="index"
              class="flex flex-wrap items-center gap-2"
            >
              <input
                v-model="holiday.name"
                type="text"
                required
                :placeholder="$t('BUSINESS_HOURS.HOLIDAY_NAME')"
                :aria-label="$t('BUSINESS_HOURS.HOLIDAY_NAME')"
              />
              <input
                v-model="holiday.start_date"
                type="date"
                required
                :aria-label="$t('BUSINESS_HOURS.START_DATE')"
              />
              <input
                v-model="holiday.end_date"
                type="date"
                required
                :aria-label="$t('BUSINESS_HOURS.END_DATE')"
              />
              <Button
                type="button"
                icon="i-lucide-x"
                ghost
                slate
                xs
                :aria-label="$t('BUSINESS_HOURS.REMOVE')"
                @click="removeHoliday(holiday)"
              />
            </div>
            <div>
              <Button
                type="button"
                :label="$t('BUSINESS_HOURS.ADD_HOLIDAY')"
                link
                sm
                @click="addHoliday"
              />
            </div>
          </section>

          <div class="flex gap-2">
            <Button
              type="submit"
              :label="$t('BUSINESS_HOURS.SAVE')"
              :is-loading="isSaving"
            />
            <Button
              v-if="editing.id"
              type="button"
              :label="$t('BUSINESS_HOURS.DELETE')"
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
