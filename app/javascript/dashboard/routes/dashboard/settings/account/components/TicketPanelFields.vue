<script setup>
import { ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useAccount } from 'dashboard/composables/useAccount';
import { useAlert } from 'dashboard/composables';
import NextButton from 'dashboard/components-next/button/Button.vue';
import { TICKET_PANEL_FIELDS } from 'dashboard/constants/ticketPanelFields';

// Which fields agents see in a ticket's left column, and in which order (like a Zendesk ticket form).
const { t } = useI18n();
const { currentAccount, updateAccount } = useAccount();
// Every field with its visibility, in display order: chosen fields first, the rest after.
const rows = ref([]);
const isSubmitting = ref(false);

watch(
  currentAccount,
  account => {
    const chosen =
      account?.settings?.ticket_panel_fields || TICKET_PANEL_FIELDS;
    rows.value = [
      ...chosen.map(field => ({ field, visible: true })),
      ...TICKET_PANEL_FIELDS.filter(field => !chosen.includes(field)).map(
        field => ({ field, visible: false })
      ),
    ];
  },
  { immediate: true, deep: true }
);

const move = (index, offset) => {
  const target = index + offset;
  if (target < 0 || target >= rows.value.length) return;
  const list = [...rows.value];
  [list[index], list[target]] = [list[target], list[index]];
  rows.value = list;
};

const save = async () => {
  isSubmitting.value = true;
  try {
    await updateAccount(
      {
        ticket_panel_fields: rows.value
          .filter(row => row.visible)
          .map(row => row.field),
      },
      { silent: true }
    );
    useAlert(t('GENERAL_SETTINGS.FORM.TICKET_FIELDS.SUCCESS'));
  } catch (error) {
    useAlert(t('GENERAL_SETTINGS.FORM.TICKET_FIELDS.API_ERROR'));
  } finally {
    isSubmitting.value = false;
  }
};
</script>

<template>
  <div
    data-testid="ticket-panel-fields"
    class="flex flex-col w-full outline-1 outline outline-n-container rounded-xl bg-n-solid-2 divide-y divide-n-weak"
  >
    <div class="flex flex-col items-start gap-2 px-5 py-4">
      <h3 class="text-heading-2 text-n-slate-12">
        {{ t('GENERAL_SETTINGS.FORM.TICKET_FIELDS.TITLE') }}
      </h3>
      <p class="mb-0 text-body-para text-n-slate-11">
        {{ t('GENERAL_SETTINGS.FORM.TICKET_FIELDS.NOTE') }}
      </p>
    </div>
    <form class="flex flex-col gap-1 px-5 py-4" @submit.prevent="save">
      <div
        v-for="(row, index) in rows"
        :key="row.field"
        class="flex items-center gap-2 py-1"
      >
        <label class="flex items-center flex-1 gap-2 text-sm text-n-slate-12">
          <input
            v-model="row.visible"
            type="checkbox"
            :data-testid="`ticket-field-${row.field}`"
          />
          {{ t(`GENERAL_SETTINGS.FORM.TICKET_FIELDS.FIELDS.${row.field}`) }}
        </label>
        <NextButton
          type="button"
          icon="i-lucide-arrow-up"
          ghost
          slate
          xs
          :aria-label="t('GENERAL_SETTINGS.FORM.TICKET_FIELDS.MOVE_UP')"
          @click="move(index, -1)"
        />
        <NextButton
          type="button"
          icon="i-lucide-arrow-down"
          ghost
          slate
          xs
          :aria-label="t('GENERAL_SETTINGS.FORM.TICKET_FIELDS.MOVE_DOWN')"
          @click="move(index, 1)"
        />
      </div>
      <div class="pt-3">
        <NextButton
          type="submit"
          :is-loading="isSubmitting"
          :label="t('GENERAL_SETTINGS.FORM.TICKET_FIELDS.SUBMIT')"
        />
      </div>
    </form>
  </div>
</template>
