<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useAlert } from 'dashboard/composables';
import { dynamicTime } from 'shared/helpers/timeHelper';
import {
  DeletedTicketsAPI,
  SuspendedTicketsAPI,
} from 'dashboard/api/ticketQueues';
import Button from 'dashboard/components-next/button/Button.vue';

// Deleted tickets (restorable for 30 days) and suspended tickets (held e-mails, kept 14 days).
const props = defineProps({
  kind: {
    type: String,
    required: true,
    validator: value => ['deleted', 'suspended'].includes(value),
  },
});

const { t } = useI18n();
const api = computed(() =>
  props.kind === 'deleted' ? DeletedTicketsAPI : SuspendedTicketsAPI
);
const prefix = computed(() => `TICKET_QUEUES.${props.kind.toUpperCase()}`);
const items = ref([]);
const isLoading = ref(false);

const load = async () => {
  isLoading.value = true;
  try {
    const { data } = await api.value.get();
    items.value = data.payload;
  } finally {
    isLoading.value = false;
  }
};

const restore = async item => {
  await api.value.restore(item.id);
  useAlert(t(`${prefix.value}.RESTORED`));
  load();
};

const remove = async item => {
  await api.value.delete(item.id);
  useAlert(t(`${prefix.value}.DELETED`));
  load();
};

watch(() => props.kind, load);
onMounted(load);
</script>

<template>
  <section
    class="flex flex-col w-full h-full gap-4 px-6 py-6 overflow-y-auto bg-n-background"
    :data-testid="`ticket-queue-${kind}`"
  >
    <header class="flex flex-col gap-1">
      <h1 class="text-heading-1 text-n-slate-12">
        {{ $t(`${prefix}.TITLE`) }}
      </h1>
      <p class="text-sm text-n-slate-11">{{ $t(`${prefix}.DESCRIPTION`) }}</p>
    </header>
    <p v-if="!isLoading && !items.length" class="text-sm text-n-slate-11">
      {{ $t(`${prefix}.EMPTY`) }}
    </p>
    <ul class="flex flex-col divide-y divide-n-weak">
      <li
        v-for="item in items"
        :key="item.id"
        data-testid="ticket-queue-item"
        class="flex flex-wrap items-center gap-3 py-3"
      >
        <div class="flex flex-col flex-1 min-w-0">
          <span class="text-sm font-medium truncate text-n-slate-12">
            <template v-if="kind === 'deleted'">#{{ item.id }} · </template>
            {{ item.subject || $t('TICKET_QUEUES.NO_SUBJECT') }}
          </span>
          <span class="text-xs text-n-slate-11">
            <template v-if="kind === 'deleted'">
              {{ item.requester }} ·
              {{
                $t('TICKET_QUEUES.DELETED_AT', {
                  time: dynamicTime(item.deleted_at),
                })
              }}
            </template>
            <template v-else>
              {{ item.from_name || item.from_email }} · {{ item.inbox }} ·
              {{ $t(`TICKET_QUEUES.SUSPENDED.REASONS.${item.reason}`) }}
            </template>
          </span>
        </div>
        <Button
          :label="$t(`${prefix}.RESTORE`)"
          sm
          slate
          faded
          @click="restore(item)"
        />
        <Button
          :label="$t(`${prefix}.DELETE`)"
          sm
          ruby
          faded
          @click="remove(item)"
        />
      </li>
    </ul>
  </section>
</template>
