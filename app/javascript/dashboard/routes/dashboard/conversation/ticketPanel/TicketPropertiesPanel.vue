<script setup>
// Painel de propriedades do ticket no estilo do Agent Workspace:
// solicitante, organização, CC/seguidores, formulário, tipo, prioridade,
// status, grupo, responsável, tags e os campos do formulário selecionado.
// Reaproveita as mesmas actions do ConversationAction/CustomAttributes.
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute } from 'vue-router';
import { useAlert } from 'dashboard/composables';
import { useMapGetter, useStore } from 'dashboard/composables/store';
import { useAgentsList } from 'dashboard/composables/useAgentsList';
import { useUISettings } from 'dashboard/composables/useUISettings';
import { copyTextToClipboard } from 'shared/helpers/clipboard';
import { frontendURL } from 'dashboard/helper/URLHelper';
import { CONVERSATION_PRIORITY } from 'shared/constants/messages';
import wootConstants from 'dashboard/constants/globals';
import CompanyAPI from 'dashboard/api/companies';
import { resolveTicketStatus } from 'dashboard/servicedesk/statusTokens';
import {
  FORM_ATTRIBUTE_KEY,
  STATUS_ATTRIBUTE_KEY,
  TYPE_ATTRIBUTE_KEY,
  CC_ATTRIBUTE_KEY,
  FOLLOWERS_ATTRIBUTE_KEY,
  buildFormFieldGroups,
  defaultCustomStatusFor,
  getFormNames,
  hasValue,
  nativeStatusFor,
  resolveFormName,
  ticketFormsMeta,
} from 'dashboard/servicedesk/ticketFormHelper';

import Avatar from 'next/avatar/Avatar.vue';
import NextButton from 'dashboard/components-next/button/Button.vue';
import Icon from 'dashboard/components-next/icon/Icon.vue';
import MultiselectDropdown from 'shared/components/ui/MultiselectDropdown.vue';
import CustomAttribute from 'dashboard/components/CustomAttribute.vue';
import ConversationLabels from '../labels/LabelBox.vue';
import TicketPropertyField from './TicketPropertyField.vue';

const props = defineProps({
  conversationId: { type: [Number, String], required: true },
});

const store = useStore();
const route = useRoute();
const { t } = useI18n();
const { uiSettings, updateUISettings } = useUISettings();

const currentChat = useMapGetter('getSelectedChat');
const currentUser = useMapGetter('getCurrentUser');
const teams = useMapGetter('teams/getTeams');
const contactGetter = useMapGetter('contacts/getContact');
const attributesByModel = useMapGetter('attributes/getAttributesByModel');
const { agentsList } = useAgentsList(true, { includeAIAssignees: true });

const UI_KEY = 'servicedesk_ticket_panel';
const panelState = computed(() => uiSettings.value[UI_KEY] || {});
const isSectionOpen = (key, fallback = true) =>
  panelState.value[key] === undefined ? fallback : !!panelState.value[key];
const toggleSection = key => {
  updateUISettings({
    [UI_KEY]: {
      ...panelState.value,
      [key]: !isSectionOpen(key, key === 'fields'),
    },
  });
};

const showHiddenFields = ref(false);
watch(
  () => props.conversationId,
  () => {
    showHiddenFields.value = false;
  }
);

// ---------------------------------------------------------------- dados
const conversationAttributes = computed(() =>
  attributesByModel.value('conversation_attribute')
);
const attributeByKey = computed(() => {
  const map = {};
  conversationAttributes.value.forEach(attribute => {
    map[attribute.attribute_key] = attribute;
  });
  return map;
});
const customAttributes = computed(
  () => currentChat.value?.custom_attributes || {}
);

const contactId = computed(() => currentChat.value?.meta?.sender?.id);
const contact = computed(() => contactGetter.value(contactId.value) || {});
const requester = computed(() => ({
  ...(currentChat.value?.meta?.sender || {}),
  ...contact.value,
}));
const contactLink = computed(() =>
  contactId.value
    ? frontendURL(
        `accounts/${route.params.accountId}/contacts/${contactId.value}`
      )
    : ''
);

// Organização (decisão 7): o nome vem de contact.additional_attributes.
// company_name; a empresa (company_id) só complementa com o link e, se o nome
// não estiver no contato, com o nome da empresa.
const companyName = ref('');
const companyLink = ref('');
const loadCompany = async () => {
  const companyId = contact.value?.company_id;
  const savedName = (
    contact.value?.additional_attributes?.company_name ||
    requester.value?.additional_attributes?.company_name ||
    ''
  ).trim();
  companyName.value = savedName;
  companyLink.value = '';
  if (!companyId) return;
  try {
    const { data } = await CompanyAPI.show(companyId);
    const company = data?.payload || data || {};
    if (contact.value?.company_id !== companyId) return;
    companyName.value = savedName || company.name || '';
    companyLink.value = frontendURL(
      `accounts/${route.params.accountId}/companies/${companyId}`
    );
  } catch {
    // recurso de empresas desativado ou sem permissão: fica o nome salvo
  }
};
watch(
  () => [contact.value?.company_id, contact.value?.additional_attributes],
  loadCompany,
  { immediate: true }
);

const ticketNumber = computed(
  () => customAttributes.value.zd_ticket_id || currentChat.value?.id
);

// ---------------------------------------------- atributos personalizados
const saveCustomAttributes = async (changes, successMessage) => {
  try {
    await store.dispatch('updateCustomAttributes', {
      conversationId: currentChat.value.id,
      customAttributes: { ...customAttributes.value, ...changes },
    });
    useAlert(successMessage || t('CUSTOM_ATTRIBUTES.FORM.UPDATE.SUCCESS'));
    return true;
  } catch (error) {
    useAlert(
      error?.response?.message || t('CUSTOM_ATTRIBUTES.FORM.UPDATE.ERROR')
    );
    return false;
  }
};

const onUpdateAttribute = (key, value) =>
  saveCustomAttributes({ [key]: value });

const onDeleteAttribute = async key => {
  const { [key]: removed, ...rest } = customAttributes.value;
  try {
    await store.dispatch('updateCustomAttributes', {
      conversationId: currentChat.value.id,
      customAttributes: rest,
    });
    useAlert(t('CUSTOM_ATTRIBUTES.FORM.DELETE.SUCCESS'));
  } catch (error) {
    useAlert(
      error?.response?.message || t('CUSTOM_ATTRIBUTES.FORM.DELETE.ERROR')
    );
  }
};

const onCopyAttribute = async value => {
  await copyTextToClipboard(value);
  useAlert(t('CUSTOM_ATTRIBUTES.COPY_SUCCESSFUL'));
};

// Opções {id, name} de um atributo do tipo lista (+ valor atual se não
// estiver mais na lista, para não perder dado legado).
const listOptionsFor = (key, { allowEmpty = true } = {}) => {
  const values = [...(attributeByKey.value[key]?.attribute_values || [])];
  const current = customAttributes.value[key];
  if (hasValue(current) && !values.includes(current)) values.push(current);
  const options = values.map((name, index) => ({ id: index + 1, name }));
  if (allowEmpty && hasValue(current)) {
    return [{ id: -1, name: t('SERVICEDESK_TICKET_PANEL.NONE') }, ...options];
  }
  return options;
};
const selectedOptionFor = key => {
  const current = customAttributes.value[key];
  if (!hasValue(current)) return null;
  return { id: 1, name: String(current) };
};
const onSelectListValue = (key, option) => {
  if (!option) return;
  if (option.id === -1) {
    onDeleteAttribute(key);
    return;
  }
  if (customAttributes.value[key] === option.name) return;
  onUpdateAttribute(key, option.name);
};

const hasAttribute = key => !!attributeByKey.value[key];
const attrValue = key =>
  hasValue(customAttributes.value[key]) ? customAttributes.value[key] : '';

// ------------------------------------------------------------ formulário
const formValue = computed(() => customAttributes.value[FORM_ATTRIBUTE_KEY]);
const effectiveFormName = computed(() => resolveFormName(formValue.value));
const isDefaultFormApplied = computed(
  () => !hasValue(formValue.value) && !!effectiveFormName.value
);
const formOptions = computed(() => {
  const fromAttribute = attributeByKey.value[FORM_ATTRIBUTE_KEY]
    ?.attribute_values || [
    ...getFormNames().filter(name => ticketFormsMeta.forms?.[name]?.active),
  ];
  const names = [...fromAttribute];
  if (hasValue(formValue.value) && !names.includes(formValue.value)) {
    names.push(formValue.value);
  }
  return names.map((name, index) => ({ id: index + 1, name }));
});
const selectedForm = computed(() =>
  effectiveFormName.value ? { id: 1, name: effectiveFormName.value } : null
);
const onSelectForm = option => {
  if (!option || option.name === formValue.value) return;
  saveCustomAttributes(
    { [FORM_ATTRIBUTE_KEY]: option.name },
    t('SERVICEDESK_TICKET_PANEL.FORM.CHANGED', { form: option.name })
  );
};

const fieldGroups = computed(() =>
  buildFormFieldGroups({
    formName: effectiveFormName.value,
    attributes: conversationAttributes.value,
    values: customAttributes.value,
    showAllConditional: showHiddenFields.value,
  })
);

// ------------------------------------------------------------- prioridade
const priorityOptions = computed(() => [
  {
    id: null,
    name: t('CONVERSATION.PRIORITY.OPTIONS.NONE'),
    icon: 'i-woot-priority-empty',
  },
  {
    id: CONVERSATION_PRIORITY.URGENT,
    name: t('CONVERSATION.PRIORITY.OPTIONS.URGENT'),
    icon: 'i-woot-priority-urgent',
  },
  {
    id: CONVERSATION_PRIORITY.HIGH,
    name: t('CONVERSATION.PRIORITY.OPTIONS.HIGH'),
    icon: 'i-woot-priority-high',
  },
  {
    id: CONVERSATION_PRIORITY.MEDIUM,
    name: t('CONVERSATION.PRIORITY.OPTIONS.MEDIUM'),
    icon: 'i-woot-priority-medium',
  },
  {
    id: CONVERSATION_PRIORITY.LOW,
    name: t('CONVERSATION.PRIORITY.OPTIONS.LOW'),
    icon: 'i-woot-priority-low',
  },
]);
const selectedPriority = computed(
  () =>
    priorityOptions.value.find(
      option => option.id === currentChat.value?.priority
    ) || priorityOptions.value[0]
);
const onSelectPriority = option => {
  const conversationId = currentChat.value.id;
  const priority = option.id === selectedPriority.value.id ? null : option.id;
  store.dispatch('setCurrentChatPriority', { priority, conversationId });
  store.dispatch('assignPriority', { conversationId, priority }).then(() => {
    useAlert(
      t('CONVERSATION.PRIORITY.CHANGE_PRIORITY.SUCCESSFUL', {
        priority: option.name,
        conversationId,
      })
    );
  });
};

// ----------------------------------------------------------------- status
const STATUS = wootConstants.STATUS_TYPE;
const nativeStatusLabels = computed(() => ({
  [STATUS.OPEN]: t('SERVICEDESK_TICKET_PANEL.NATIVE_STATUS.OPEN'),
  [STATUS.PENDING]: t('SERVICEDESK_TICKET_PANEL.NATIVE_STATUS.PENDING'),
  [STATUS.RESOLVED]: t('SERVICEDESK_TICKET_PANEL.NATIVE_STATUS.RESOLVED'),
  [STATUS.SNOOZED]: t('SERVICEDESK_TICKET_PANEL.NATIVE_STATUS.SNOOZED'),
}));
// Status canônico: Aberto (open) · Pendente/Em espera (snoozed) · Resolvido.
// O status nativo "pending" é reservado a bot/IA e só aparece se o ticket
// já estiver nele.
const nativeStatusOptions = computed(() => {
  const options = [STATUS.OPEN, STATUS.SNOOZED, STATUS.RESOLVED];
  if (currentChat.value?.status === STATUS.PENDING)
    options.push(STATUS.PENDING);
  return options.map(id => ({ id, name: nativeStatusLabels.value[id] }));
});
const nativeStatus = computed(() => currentChat.value?.status);
// Status exibido (canônico): rótulo zd_status com a cor da sua categoria.
const ticketStatus = computed(() =>
  resolveTicketStatus({
    status: nativeStatus.value,
    zdStatus: customAttributes.value[STATUS_ATTRIBUTE_KEY],
  })
);
const statusBadgeLabel = computed(
  () => ticketStatus.value.label || t(ticketStatus.value.token.labelKey)
);
const statusBadgeClass = computed(() => ticketStatus.value.token.classes.badge);
// No seletor, snoozed mostra "Pendente" ou "Em espera" conforme a categoria.
const nativeOptionLabel = option =>
  option.id === STATUS.SNOOZED && nativeStatus.value === STATUS.SNOOZED
    ? t(ticketStatus.value.token.labelKey)
    : option.name;

const changeNativeStatus = async status => {
  if (!status || status === nativeStatus.value) return;
  await store.dispatch('toggleStatus', {
    conversationId: currentChat.value.id,
    status,
  });
  useAlert(t('CONVERSATION.CHANGE_STATUS'));
};

// Status personalizado (zd_status): ao escolher, o status nativo acompanha a
// categoria pelo status canônico (novo/aberto -> open, pendente/em espera ->
// snoozed, resolvido -> resolved).
const onSelectCustomStatus = async option => {
  if (!option || option.id === -1) return;
  if (customAttributes.value[STATUS_ATTRIBUTE_KEY] !== option.name) {
    const saved = await saveCustomAttributes({
      [STATUS_ATTRIBUTE_KEY]: option.name,
    });
    if (!saved) return;
  }
  await changeNativeStatus(nativeStatusFor(option.name));
};

const onSelectNativeStatus = async status => {
  if (status === nativeStatus.value) return;
  const currentCustom = customAttributes.value[STATUS_ATTRIBUTE_KEY];
  // mantém o status personalizado coerente com a nova categoria
  if (
    hasAttribute(STATUS_ATTRIBUTE_KEY) &&
    nativeStatusFor(currentCustom) !== status
  ) {
    const fallback = defaultCustomStatusFor(status);
    if (fallback) {
      await saveCustomAttributes({ [STATUS_ATTRIBUTE_KEY]: fallback });
    }
  }
  await changeNativeStatus(status);
};

// ------------------------------------------------------------ grupo/agente
const teamsList = computed(() => {
  if (currentChat.value?.meta?.team) {
    return [{ id: 0, name: t('TEAMS_SETTINGS.LIST.NONE') }, ...teams.value];
  }
  return teams.value;
});
const assignedTeam = computed(() => currentChat.value?.meta?.team);
const onSelectTeam = team => {
  const conversationId = currentChat.value.id;
  const isSame = assignedTeam.value?.id === team?.id;
  const newTeam = isSame || !team?.id ? null : team;
  store.dispatch('setCurrentChatTeam', { team: newTeam, conversationId });
  store
    .dispatch('assignTeam', {
      conversationId,
      teamId: newTeam ? newTeam.id : 0,
    })
    .then(() => useAlert(t('CONVERSATION.CHANGE_TEAM')));
};

const assignedAgent = computed(() => {
  const assignee = currentChat.value?.meta?.assignee;
  return (
    assignee && {
      ...assignee,
      assignee_type: currentChat.value.meta.assignee_type || 'User',
    }
  );
});
const setAgent = agent => {
  const conversationId = currentChat.value.id;
  const assigneeType = agent ? agent.assignee_type || 'User' : null;
  store.dispatch('setCurrentChatAssignee', {
    conversationId,
    assignee: agent,
    assigneeType,
  });
  store
    .dispatch('assignAgent', {
      conversationId,
      agentId: agent ? agent.id : null,
      assigneeType,
    })
    .then(() => useAlert(t('CONVERSATION.CHANGE_AGENT')));
};
const onSelectAgent = agent => {
  const isSame =
    assignedAgent.value?.id === agent.id &&
    (assignedAgent.value?.assignee_type || 'User') ===
      (agent.assignee_type || 'User');
  setAgent(isSame ? null : agent);
};
const showSelfAssign = computed(
  () =>
    !assignedAgent.value ||
    assignedAgent.value.id !== currentUser.value.id ||
    (assignedAgent.value.assignee_type || 'User') !== 'User'
);
const onSelfAssign = () => {
  const {
    account_id,
    availability_status,
    available_name,
    email,
    id,
    name,
    role,
    avatar_url,
  } = currentUser.value;
  setAgent({
    account_id,
    availability_status,
    available_name,
    email,
    id,
    name,
    role,
    thumbnail: avatar_url,
  });
};

const formatMetaValue = field => {
  if (field.attribute_display_type === 'date' && field.value) {
    const date = new Date(field.value);
    return Number.isNaN(date.getTime()) ? field.value : date.toLocaleString();
  }
  if (field.attribute_display_type === 'checkbox') {
    return field.value === true || field.value === 'true'
      ? t('SERVICEDESK_TICKET_PANEL.YES')
      : t('SERVICEDESK_TICKET_PANEL.NO');
  }
  return String(field.value);
};
</script>

<template>
  <section
    class="ticket-properties border-b border-n-weak bg-n-solid-1"
    :aria-label="$t('SERVICEDESK_TICKET_PANEL.TITLE')"
  >
    <header class="flex items-center justify-between gap-2 px-4 pt-3 pb-2">
      <h3 class="m-0 text-sm font-semibold text-n-slate-12">
        {{ $t('SERVICEDESK_TICKET_PANEL.TITLE') }}
        <span class="ms-1 font-normal text-n-slate-11">
          {{
            $t('SERVICEDESK_TICKET_PANEL.TICKET_NUMBER', {
              number: ticketNumber,
            })
          }}
        </span>
      </h3>
      <span
        class="max-w-[50%] truncate px-2 py-0.5 text-xs font-semibold rounded-full ring-1 ring-inset ring-black/5 dark:ring-white/10"
        :class="statusBadgeClass"
        :data-category="ticketStatus.category"
      >
        {{ statusBadgeLabel }}
      </span>
    </header>

    <div class="flex flex-col gap-3 px-4 pb-4">
      <!-- Solicitante -->
      <TicketPropertyField :label="$t('SERVICEDESK_TICKET_PANEL.REQUESTER')">
        <div class="flex items-center min-w-0 gap-2">
          <Avatar
            :src="requester.thumbnail || requester.avatar_url"
            :name="requester.name || requester.email || ''"
            :size="24"
            rounded-full
          />
          <div class="flex flex-col min-w-0">
            <router-link
              v-if="contactLink"
              :to="contactLink"
              class="text-sm font-medium truncate text-n-slate-12 hover:underline"
            >
              {{ requester.name || requester.email || '---' }}
            </router-link>
            <span
              v-if="requester.email && requester.email !== requester.name"
              class="text-xs truncate text-n-slate-11"
            >
              {{ requester.email }}
            </span>
          </div>
        </div>
      </TicketPropertyField>

      <!-- Organização -->
      <TicketPropertyField :label="$t('SERVICEDESK_TICKET_PANEL.ORGANIZATION')">
        <router-link
          v-if="companyLink"
          :to="companyLink"
          class="text-sm truncate text-n-slate-12 hover:underline"
        >
          {{ companyName }}
        </router-link>
        <span v-else class="text-sm truncate text-n-slate-12">
          {{ companyName || '---' }}
        </span>
      </TicketPropertyField>

      <!-- CC e seguidores -->
      <div
        v-if="
          hasAttribute(CC_ATTRIBUTE_KEY) ||
          hasAttribute(FOLLOWERS_ATTRIBUTE_KEY)
        "
        class="-mx-4 ticket-properties__attrs"
      >
        <template
          v-for="key in [CC_ATTRIBUTE_KEY, FOLLOWERS_ATTRIBUTE_KEY]"
          :key="key"
        >
          <CustomAttribute
            v-if="hasAttribute(key)"
            :attribute-key="key"
            attribute-type="text"
            :label="
              key === CC_ATTRIBUTE_KEY
                ? $t('SERVICEDESK_TICKET_PANEL.CC')
                : $t('SERVICEDESK_TICKET_PANEL.FOLLOWERS')
            "
            :value="attrValue(key)"
            show-actions
            @update="onUpdateAttribute"
            @delete="onDeleteAttribute"
            @copy="onCopyAttribute"
          />
        </template>
      </div>

      <!-- Formulário -->
      <TicketPropertyField
        v-if="hasAttribute(FORM_ATTRIBUTE_KEY)"
        :label="$t('SERVICEDESK_TICKET_PANEL.FORM.LABEL')"
        :hint="
          isDefaultFormApplied
            ? $t('SERVICEDESK_TICKET_PANEL.FORM.DEFAULT')
            : ''
        "
      >
        <MultiselectDropdown
          :options="formOptions"
          :selected-item="selectedForm"
          :has-thumbnail="false"
          :multiselector-title="$t('SERVICEDESK_TICKET_PANEL.FORM.LABEL')"
          :multiselector-placeholder="$t('SERVICEDESK_TICKET_PANEL.SELECT')"
          :no-search-result="$t('SERVICEDESK_TICKET_PANEL.NO_RESULTS')"
          :input-placeholder="$t('SERVICEDESK_TICKET_PANEL.SEARCH')"
          @select="onSelectForm"
        />
      </TicketPropertyField>

      <!-- Tipo | Prioridade -->
      <div class="grid grid-cols-2 gap-3">
        <TicketPropertyField
          v-if="hasAttribute(TYPE_ATTRIBUTE_KEY)"
          :label="$t('SERVICEDESK_TICKET_PANEL.TYPE')"
        >
          <MultiselectDropdown
            :options="listOptionsFor(TYPE_ATTRIBUTE_KEY)"
            :selected-item="selectedOptionFor(TYPE_ATTRIBUTE_KEY)"
            :has-thumbnail="false"
            :multiselector-title="$t('SERVICEDESK_TICKET_PANEL.TYPE')"
            :multiselector-placeholder="$t('SERVICEDESK_TICKET_PANEL.EMPTY')"
            :no-search-result="$t('SERVICEDESK_TICKET_PANEL.NO_RESULTS')"
            :input-placeholder="$t('SERVICEDESK_TICKET_PANEL.SEARCH')"
            @select="option => onSelectListValue(TYPE_ATTRIBUTE_KEY, option)"
          />
        </TicketPropertyField>
        <TicketPropertyField
          :label="$t('CONVERSATION.PRIORITY.TITLE')"
          :class="{ 'col-span-2': !hasAttribute(TYPE_ATTRIBUTE_KEY) }"
        >
          <MultiselectDropdown
            :options="priorityOptions"
            :selected-item="selectedPriority"
            :multiselector-title="$t('CONVERSATION.PRIORITY.TITLE')"
            :multiselector-placeholder="
              $t('CONVERSATION.PRIORITY.CHANGE_PRIORITY.SELECT_PLACEHOLDER')
            "
            :no-search-result="
              $t('CONVERSATION.PRIORITY.CHANGE_PRIORITY.NO_RESULTS')
            "
            :input-placeholder="
              $t('CONVERSATION.PRIORITY.CHANGE_PRIORITY.INPUT_PLACEHOLDER')
            "
            @select="onSelectPriority"
          />
        </TicketPropertyField>
      </div>

      <!-- Status -->
      <TicketPropertyField :label="$t('SERVICEDESK_TICKET_PANEL.STATUS')">
        <MultiselectDropdown
          v-if="hasAttribute(STATUS_ATTRIBUTE_KEY)"
          :options="listOptionsFor(STATUS_ATTRIBUTE_KEY, { allowEmpty: false })"
          :selected-item="selectedOptionFor(STATUS_ATTRIBUTE_KEY)"
          :has-thumbnail="false"
          :multiselector-title="$t('SERVICEDESK_TICKET_PANEL.STATUS')"
          :multiselector-placeholder="$t('SERVICEDESK_TICKET_PANEL.EMPTY')"
          :no-search-result="$t('SERVICEDESK_TICKET_PANEL.NO_RESULTS')"
          :input-placeholder="$t('SERVICEDESK_TICKET_PANEL.SEARCH')"
          @select="onSelectCustomStatus"
        />
        <div
          class="flex p-0.5 rounded-lg bg-n-alpha-black2 gap-0.5"
          role="radiogroup"
          :aria-label="$t('SERVICEDESK_TICKET_PANEL.NATIVE_STATUS.LABEL')"
        >
          <button
            v-for="option in nativeStatusOptions"
            :key="option.id"
            type="button"
            role="radio"
            :aria-checked="nativeStatus === option.id"
            class="flex-1 px-1.5 py-1 text-xs font-medium truncate rounded-md transition-colors"
            :class="
              nativeStatus === option.id
                ? 'bg-n-solid-1 text-n-slate-12 shadow-sm outline outline-1 outline-n-weak'
                : 'text-n-slate-11 hover:text-n-slate-12'
            "
            @click="onSelectNativeStatus(option.id)"
          >
            {{ nativeOptionLabel(option) }}
          </button>
        </div>
      </TicketPropertyField>

      <!-- Grupo -->
      <TicketPropertyField :label="$t('SERVICEDESK_TICKET_PANEL.GROUP')">
        <MultiselectDropdown
          :options="teamsList"
          :selected-item="assignedTeam"
          show-emoji-icon
          :multiselector-title="$t('AGENT_MGMT.MULTI_SELECTOR.TITLE.TEAM')"
          :multiselector-placeholder="$t('SERVICEDESK_TICKET_PANEL.EMPTY')"
          :no-search-result="
            $t('AGENT_MGMT.MULTI_SELECTOR.SEARCH.NO_RESULTS.TEAM')
          "
          :input-placeholder="
            $t('AGENT_MGMT.MULTI_SELECTOR.SEARCH.PLACEHOLDER.TEAM')
          "
          @select="onSelectTeam"
        />
      </TicketPropertyField>

      <!-- Responsável -->
      <TicketPropertyField :label="$t('SERVICEDESK_TICKET_PANEL.ASSIGNEE')">
        <template #action>
          <NextButton
            v-if="showSelfAssign"
            link
            xs
            :label="$t('CONVERSATION_SIDEBAR.SELF_ASSIGN')"
            @click="onSelfAssign"
          />
        </template>
        <MultiselectDropdown
          :options="agentsList"
          :selected-item="assignedAgent"
          :multiselector-title="$t('AGENT_MGMT.MULTI_SELECTOR.TITLE.AGENT')"
          :multiselector-placeholder="$t('SERVICEDESK_TICKET_PANEL.EMPTY')"
          :no-search-result="
            $t('AGENT_MGMT.MULTI_SELECTOR.SEARCH.NO_RESULTS.AGENT')
          "
          :input-placeholder="
            $t('AGENT_MGMT.MULTI_SELECTOR.SEARCH.PLACEHOLDER.AGENT')
          "
          @select="onSelectAgent"
        />
      </TicketPropertyField>

      <!-- Tags -->
      <TicketPropertyField :label="$t('SERVICEDESK_TICKET_PANEL.TAGS')">
        <ConversationLabels :conversation-id="conversationId" />
      </TicketPropertyField>
    </div>

    <!-- Campos do formulário -->
    <div class="border-t border-n-weak">
      <button
        type="button"
        class="flex items-center justify-between w-full px-4 py-2.5 text-start"
        :aria-expanded="isSectionOpen('fields')"
        @click="toggleSection('fields')"
      >
        <span class="text-sm font-semibold text-n-slate-12">
          {{
            effectiveFormName
              ? $t('SERVICEDESK_TICKET_PANEL.FIELDS.TITLE_WITH_FORM', {
                  form: effectiveFormName,
                })
              : $t('SERVICEDESK_TICKET_PANEL.FIELDS.TITLE')
          }}
        </span>
        <Icon
          :icon="
            isSectionOpen('fields')
              ? 'i-lucide-chevron-up'
              : 'i-lucide-chevron-down'
          "
          class="size-4 text-n-slate-11"
        />
      </button>
      <div v-if="isSectionOpen('fields')" class="pb-2">
        <div class="ticket-properties__attrs">
          <CustomAttribute
            v-for="field in fieldGroups.formFields"
            :key="`${conversationId}-${field.key}`"
            :attribute-key="field.attribute_key"
            :attribute-type="field.attribute_display_type"
            :values="field.attribute_values"
            :label="
              field.isRequired
                ? `${field.attribute_display_name} *`
                : field.attribute_display_name
            "
            :value="field.value"
            show-actions
            :attribute-regex="field.regex_pattern"
            :regex-cue="field.regex_cue"
            @update="onUpdateAttribute"
            @delete="onDeleteAttribute"
            @copy="onCopyAttribute"
          />
        </div>
        <p
          v-if="!fieldGroups.formFields.length"
          class="px-4 py-2 m-0 text-sm text-n-slate-11"
        >
          {{ $t('SERVICEDESK_TICKET_PANEL.FIELDS.EMPTY') }}
        </p>
        <div
          v-if="fieldGroups.hiddenCount || showHiddenFields"
          class="px-4 pt-1"
        >
          <NextButton
            ghost
            xs
            slate
            :icon="showHiddenFields ? 'i-lucide-eye-off' : 'i-lucide-eye'"
            :label="
              showHiddenFields
                ? $t('SERVICEDESK_TICKET_PANEL.FIELDS.HIDE_CONDITIONAL')
                : $t('SERVICEDESK_TICKET_PANEL.FIELDS.SHOW_CONDITIONAL', {
                    count: fieldGroups.hiddenCount,
                  })
            "
            @click="showHiddenFields = !showHiddenFields"
          />
        </div>
      </div>
    </div>

    <!-- Outros campos preenchidos (fora do formulário atual) -->
    <div v-if="fieldGroups.otherFields.length" class="border-t border-n-weak">
      <button
        type="button"
        class="flex items-center justify-between w-full px-4 py-2.5 text-start"
        :aria-expanded="isSectionOpen('other', false)"
        @click="toggleSection('other')"
      >
        <span class="text-sm font-semibold text-n-slate-12">
          {{
            $t('SERVICEDESK_TICKET_PANEL.OTHER_FIELDS', {
              count: fieldGroups.otherFields.length,
            })
          }}
        </span>
        <Icon
          :icon="
            isSectionOpen('other', false)
              ? 'i-lucide-chevron-up'
              : 'i-lucide-chevron-down'
          "
          class="size-4 text-n-slate-11"
        />
      </button>
      <div
        v-if="isSectionOpen('other', false)"
        class="ticket-properties__attrs pb-2"
      >
        <CustomAttribute
          v-for="field in fieldGroups.otherFields"
          :key="`${conversationId}-${field.key}`"
          :attribute-key="field.attribute_key"
          :attribute-type="field.attribute_display_type"
          :values="field.attribute_values"
          :label="field.attribute_display_name"
          :value="field.value"
          show-actions
          :attribute-regex="field.regex_pattern"
          :regex-cue="field.regex_cue"
          @update="onUpdateAttribute"
          @delete="onDeleteAttribute"
          @copy="onCopyAttribute"
        />
      </div>
    </div>

    <!-- Dados importados do sistema anterior (somente leitura) -->
    <div v-if="fieldGroups.metaFields.length" class="border-t border-n-weak">
      <button
        type="button"
        class="flex items-center justify-between w-full px-4 py-2.5 text-start"
        :aria-expanded="isSectionOpen('meta', false)"
        @click="toggleSection('meta')"
      >
        <span class="text-sm font-semibold text-n-slate-12">
          {{ $t('SERVICEDESK_TICKET_PANEL.META_FIELDS') }}
        </span>
        <Icon
          :icon="
            isSectionOpen('meta', false)
              ? 'i-lucide-chevron-up'
              : 'i-lucide-chevron-down'
          "
          class="size-4 text-n-slate-11"
        />
      </button>
      <dl
        v-if="isSectionOpen('meta', false)"
        class="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-x-3 gap-y-1.5 px-4 pb-3 m-0 text-xs"
      >
        <template v-for="field in fieldGroups.metaFields" :key="field.key">
          <dt
            class="truncate text-n-slate-11"
            :title="field.attribute_display_name"
          >
            {{ field.attribute_display_name }}
          </dt>
          <dd class="m-0 break-words text-n-slate-12">
            {{ formatMetaValue(field) }}
          </dd>
        </template>
      </dl>
    </div>
  </section>
</template>

<style lang="scss" scoped>
// Linhas de atributo mais compactas, alinhadas ao restante do painel.
.ticket-properties__attrs > :deep(div) {
  @apply px-4 py-2;
}
</style>
