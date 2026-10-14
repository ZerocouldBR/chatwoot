<script>
import NextSelect from 'dashboard/components-next/select/Select.vue';
import PageHeader from '../../SettingsSubPageHeader.vue';
import BandwidthSms from './BandwidthSms.vue';
import Twilio from './Twilio.vue';

export default {
  components: {
    NextSelect,
    PageHeader,
    Twilio,
    BandwidthSms,
  },
  data() {
    return {
      provider: 'twilio',
    };
  },
};
</script>

<template>
  <div class="h-full w-full p-6 col-span-6">
    <PageHeader
      :header-title="$t('INBOX_MGMT.ADD.SMS.TITLE')"
      :header-content="$t('INBOX_MGMT.ADD.SMS.DESC')"
    />
    <div class="flex-shrink-0 flex-grow-0">
      <label>
        {{ $t('INBOX_MGMT.ADD.SMS.PROVIDERS.LABEL') }}
        <NextSelect
          v-model="provider"
          class="!w-full"
          :options="[
            {
              value: 'twilio',
              label: $t('INBOX_MGMT.ADD.SMS.PROVIDERS.TWILIO'),
            },
            {
              value: '360dialog',
              label: $t('INBOX_MGMT.ADD.SMS.PROVIDERS.BANDWIDTH'),
            },
          ]"
        />
      </label>
    </div>
    <Twilio v-if="provider === 'twilio'" type="sms" />
    <BandwidthSms v-else />
  </div>
</template>
