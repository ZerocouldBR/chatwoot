<script setup>
// ServiceDesk: Configurações > Telefonia 55PBX (só administrador da conta).
// A configuração vive no sd-ops (ops.tenant_settings, segredos cifrados) e vale na hora, sem .env nem redeploy.
// A tela fala com o sd-ops no mesmo domínio (/sd-ops/...) com uma sessão criada a partir do token do próprio usuário
// (CTI_AUTH.md); o sd-ops confere no Chatwoot que ele é administrator da conta. Ver docs/INTEGRACAO-55PBX.md,
// "Configuração pelo painel (admin)".
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useStore, useMapGetter } from 'dashboard/composables/store';
import { useAlert } from 'dashboard/composables';
import Button from 'dashboard/components-next/button/Button.vue';
import BaseSettingsHeader from '../components/BaseSettingsHeader.vue';
import SettingsLayout from '../SettingsLayout.vue';
import SectionLayout from '../account/components/SectionLayout.vue';
import FieldControl from './components/FieldControl.vue';
import WebhookCard from './components/WebhookCard.vue';
import AgentMappings from './components/AgentMappings.vue';
import OpenRulesEditor from './components/OpenRulesEditor.vue';
import HoursSlaEditor from './components/HoursSlaEditor.vue';
import ReadinessChecklist from './components/ReadinessChecklist.vue';
import TestResults from './components/TestResults.vue';
import { createSdOpsClient } from './sdOpsClient';
import {
  SECTIONS,
  buildPayload,
  formFromSettings,
  isFieldVisible,
  isPayloadEmpty,
} from './settingsForm';

const { t } = useI18n();
const store = useStore();
const currentUser = useMapGetter('getCurrentUser');
const accountId = useMapGetter('getCurrentAccountId');
const agents = useMapGetter('agents/getAgents');
const teams = useMapGetter('teams/getTeams');

const client = createSdOpsClient({
  getAccessToken: () => currentUser.value?.access_token,
  getAccountId: () => accountId.value,
});

const isLoading = ref(true);
const loadError = ref('');
const data = ref(null);
const form = ref(null);
const isSaving = ref(false);
const isTesting = ref(false);
const isRotating = ref(false);
const testResult = ref(null);
const fullWebhookUrl = ref('');
const fieldErrors = ref({});

const errorMessage = e => {
  if (e.status === 0) return t('SD_TELEPHONY.ERRORS.NETWORK');
  if (e.status === 401) return t('SD_TELEPHONY.ERRORS.SESSION');
  if (e.status === 403) return t('SD_TELEPHONY.ERRORS.FORBIDDEN');
  if (e.status === 404 || e.status === 502 || e.status === 503)
    return t('SD_TELEPHONY.ERRORS.UNAVAILABLE');
  if (e.code === 'conflict') return t('SD_TELEPHONY.ERRORS.CONFLICT');
  return e.message || t('SD_TELEPHONY.ERRORS.GENERIC');
};

const applyData = d => {
  data.value = d;
  form.value = formFromSettings(d);
};

const load = async () => {
  loadError.value = '';
  try {
    applyData(await client.getSettings());
  } catch (e) {
    loadError.value = errorMessage(e);
  } finally {
    isLoading.value = false;
  }
};

onMounted(() => {
  store.dispatch('agents/get');
  store.dispatch('teams/get');
  load();
});

const payload = computed(() =>
  form.value && data.value ? buildPayload(data.value, form.value) : null
);
const isDirty = computed(
  () => !!payload.value && !isPayloadEmpty(payload.value)
);
const teamOptions = computed(() => (teams.value || []).map(x => x.name));
const vaultEnabled = computed(() => !!data.value?.vault?.enabled);
const uraEndpoint = computed(
  () => `${window.location.origin}/sd-ops/api/v1/ura/tickets/{protocolo}`
);

const visibleFields = section =>
  section.fields.filter(
    k => data.value.fields[k] && isFieldVisible(k, form.value.values)
  );
const fieldLabel = key =>
  t(`SD_TELEPHONY.FIELDS.${key.toUpperCase()}.LABEL`, key);

const save = async () => {
  isSaving.value = true;
  try {
    applyData(await client.saveSettings(payload.value));
    fieldErrors.value = {};
    useAlert(t('SD_TELEPHONY.SAVED'));
  } catch (e) {
    fieldErrors.value = e.code === 'validation' ? e.extra.fields || {} : {};
    useAlert(errorMessage(e));
  } finally {
    isSaving.value = false;
  }
};

const discard = () => {
  form.value = formFromSettings(data.value);
  fieldErrors.value = {};
};

const runTest = async () => {
  isTesting.value = true;
  try {
    testResult.value = await client.testSettings(
      isDirty.value ? payload.value : undefined
    );
  } catch (e) {
    useAlert(errorMessage(e));
  } finally {
    isTesting.value = false;
  }
};

const rotate = async () => {
  isRotating.value = true;
  try {
    const r = await client.rotateWebhookSecret();
    fullWebhookUrl.value = r.url;
    // recarrega (nova versão e URL mascarada) sem perder o que ainda não foi salvo no formulário
    data.value = await client.getSettings();
  } catch (e) {
    useAlert(errorMessage(e));
  } finally {
    isRotating.value = false;
  }
};
</script>

<template>
  <SettingsLayout
    :is-loading="isLoading"
    :loading-message="t('SD_TELEPHONY.LOADING')"
  >
    <template #header>
      <BaseSettingsHeader
        :title="t('SD_TELEPHONY.TITLE')"
        :description="t('SD_TELEPHONY.DESCRIPTION')"
      >
        <template v-if="data" #actions>
          <Button
            v-if="isDirty"
            variant="ghost"
            color="slate"
            :label="t('SD_TELEPHONY.ACTIONS.DISCARD')"
            data-test="discard"
            @click="discard"
          />
          <Button
            variant="faded"
            color="slate"
            icon="i-lucide-plug-zap"
            :is-loading="isTesting"
            :label="t('SD_TELEPHONY.ACTIONS.TEST')"
            data-test="test"
            @click="runTest"
          />
          <Button
            icon="i-lucide-save"
            :is-loading="isSaving"
            :disabled="!isDirty"
            :label="t('SD_TELEPHONY.ACTIONS.SAVE')"
            data-test="save"
            @click="save"
          />
        </template>
      </BaseSettingsHeader>
    </template>
    <template #body>
      <div
        v-if="loadError"
        class="p-4 rounded-lg bg-n-ruby-2 text-n-ruby-11 text-body-main"
        data-test="load-error"
      >
        {{ loadError }}
        <Button
          class="ltr:ml-2 rtl:mr-2"
          size="xs"
          variant="link"
          :label="t('SD_TELEPHONY.ACTIONS.RETRY')"
          @click="load"
        />
      </div>
      <div v-else-if="data && form" class="flex flex-col pb-16">
        <div class="flex flex-col gap-3">
          <div
            v-if="!vaultEnabled"
            class="p-3 rounded-lg bg-n-amber-2 text-n-amber-11 text-body-main"
            data-test="vault-warning"
          >
            {{ data.vault.error || t('SD_TELEPHONY.INFO.VAULT_MISSING') }}
          </div>
          <div
            v-if="data.force_disabled"
            class="p-3 rounded-lg bg-n-ruby-2 text-n-ruby-11 text-body-main"
          >
            {{ t('SD_TELEPHONY.INFO.FORCE_DISABLED') }}
          </div>
          <div
            v-if="Object.keys(fieldErrors).length"
            class="p-3 rounded-lg bg-n-ruby-2 text-n-ruby-11 text-body-main"
            data-test="field-errors"
          >
            <p>{{ t('SD_TELEPHONY.ERRORS.VALIDATION') }}</p>
            <ul class="ltr:pl-4 rtl:pr-4 list-disc">
              <li v-for="(msg, key) in fieldErrors" :key="key">
                {{ fieldLabel(key) }}: {{ msg }}
              </li>
            </ul>
          </div>
          <p class="text-label-small text-n-slate-11" data-test="tenant-info">
            {{
              t('SD_TELEPHONY.INFO.TENANT', {
                name: data.tenant.name,
                account: data.tenant.chatwoot_account_id,
                inbox: data.tenant.pbx_inbox_id ?? '-',
                version: data.version,
              })
            }}
            <template v-if="data.updated_by?.email">
              ·
              {{
                t('SD_TELEPHONY.INFO.UPDATED_BY', {
                  email: data.updated_by.email,
                  at: data.updated_at,
                })
              }}
            </template>
          </p>
        </div>

        <SectionLayout
          :title="t('SD_TELEPHONY.CHECKLIST.TITLE')"
          :description="t('SD_TELEPHONY.CHECKLIST.DESCRIPTION')"
        >
          <ReadinessChecklist :items="data.checklist" />
          <div v-if="testResult" class="mt-4">
            <h5 class="mb-2 text-heading-3 text-n-slate-12">
              {{ t('SD_TELEPHONY.TEST.TITLE') }}
            </h5>
            <TestResults :result="testResult" />
          </div>
          <p v-else class="mt-3 text-label-small text-n-slate-11">
            {{ t('SD_TELEPHONY.TEST.HINT') }}
          </p>
        </SectionLayout>

        <SectionLayout
          v-for="section in SECTIONS"
          :key="section.id"
          with-border
          :title="t(`SD_TELEPHONY.SECTIONS.${section.id}.TITLE`)"
          :description="t(`SD_TELEPHONY.SECTIONS.${section.id}.DESCRIPTION`)"
          :data-test="`section-${section.id}`"
        >
          <div class="flex flex-col gap-2">
            <WebhookCard
              v-if="section.id === 'WEBHOOK'"
              class="mb-4"
              :webhook="data.webhook"
              :full-url="fullWebhookUrl"
              :is-rotating="isRotating"
              @rotate="rotate"
            />
            <AgentMappings
              v-if="section.id === 'MAPS'"
              v-model="form.agentMappings"
              class="mb-4"
              :agents="agents"
            />
            <OpenRulesEditor
              v-if="section.id === 'TICKETS'"
              v-model="form.ticketOpenRules"
            />
            <HoursSlaEditor
              v-if="section.id === 'HOURS'"
              v-model:hours="form.businessHours"
              v-model:sla="form.slaPolicies"
            />
            <p
              v-if="section.id === 'URA'"
              class="mb-2 text-label-small text-n-slate-11"
            >
              {{ t('SD_TELEPHONY.URA_ENDPOINT', { url: uraEndpoint }) }}
            </p>
            <template v-for="key in visibleFields(section)" :key="key">
              <FieldControl
                v-if="data.fields[key].kind === 'secret'"
                v-model="form.secrets[key]"
                :field-key="key"
                :meta="data.fields[key]"
                :vault-enabled="vaultEnabled"
              />
              <FieldControl
                v-else
                v-model="form.values[key]"
                :field-key="key"
                :meta="data.fields[key]"
                :team-options="teamOptions"
                :reset="!!form.resets[key]"
                @reset="v => (form.resets[key] = v)"
              />
            </template>
          </div>
        </SectionLayout>
      </div>
    </template>
  </SettingsLayout>
</template>
