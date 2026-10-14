<script setup>
import { ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useAccount } from 'dashboard/composables/useAccount';
import { useAlert } from 'dashboard/composables';
import WithLabel from 'v3/components/Form/WithLabel.vue';
import NextButton from 'dashboard/components-next/button/Button.vue';

// Zendesk closes solved tickets after 4 days by default and never later than 28 days.
const DEFAULT_HOURS = 96;
const MIN_HOURS = 1;
const MAX_HOURS = 672;

const { t } = useI18n();
const { currentAccount, updateAccount } = useAccount();
const hours = ref(DEFAULT_HOURS);
const isSubmitting = ref(false);

watch(
  currentAccount,
  account => {
    hours.value = account?.settings?.close_solved_after_hours || DEFAULT_HOURS;
  },
  { immediate: true, deep: true }
);

const handleSubmit = async () => {
  const value = Number(hours.value);
  if (!Number.isInteger(value) || value < MIN_HOURS || value > MAX_HOURS) {
    useAlert(t('GENERAL_SETTINGS.FORM.CLOSE_SOLVED.ERROR'));
    return;
  }
  isSubmitting.value = true;
  try {
    await updateAccount({ close_solved_after_hours: value }, { silent: true });
    useAlert(t('GENERAL_SETTINGS.FORM.CLOSE_SOLVED.SUCCESS'));
  } catch (error) {
    useAlert(t('GENERAL_SETTINGS.FORM.CLOSE_SOLVED.API_ERROR'));
  } finally {
    isSubmitting.value = false;
  }
};
</script>

<template>
  <div
    class="flex flex-col w-full outline-1 outline outline-n-container rounded-xl bg-n-solid-2 divide-y divide-n-weak"
  >
    <div class="flex flex-col gap-2 items-start px-5 py-4">
      <h3 class="text-heading-2 text-n-slate-12">
        {{ t('GENERAL_SETTINGS.FORM.CLOSE_SOLVED.TITLE') }}
      </h3>
      <p class="mb-0 text-body-para text-n-slate-11">
        {{ t('GENERAL_SETTINGS.FORM.CLOSE_SOLVED.NOTE') }}
      </p>
    </div>
    <form class="grid gap-5 px-5 py-4" @submit.prevent="handleSubmit">
      <WithLabel
        :label="t('GENERAL_SETTINGS.FORM.CLOSE_SOLVED.LABEL')"
        :help-message="t('GENERAL_SETTINGS.FORM.CLOSE_SOLVED.HELP')"
      >
        <input
          v-model="hours"
          data-testid="close-solved-hours"
          type="number"
          :min="MIN_HOURS"
          :max="MAX_HOURS"
          class="w-40"
        />
      </WithLabel>
      <div>
        <NextButton
          type="submit"
          :is-loading="isSubmitting"
          :label="t('GENERAL_SETTINGS.FORM.CLOSE_SOLVED.SUBMIT')"
        />
      </div>
    </form>
  </div>
</template>
