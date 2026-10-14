<script setup>
// ServiceDesk M13: Configurações > Papéis. Lista os papéis da conta (os 5 do Zendesk já vêm semeados) e
// abre o editor de permissões. Só administrador chega aqui (rota e API).
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useAlert } from 'dashboard/composables';
import SettingsLayout from '../SettingsLayout.vue';
import BaseSettingsHeader from '../components/BaseSettingsHeader.vue';
import Button from 'dashboard/components-next/button/Button.vue';
import SdRolesAPI from 'dashboard/api/sdRoles';
import SdRoleEditor from './SdRoleEditor.vue';

const { t } = useI18n();

const roles = ref([]);
const catalog = ref({ keys: [], pending_keys: [] });
const isLoading = ref(true);
const editorRole = ref(null);
const showEditor = ref(false);

const fetchRoles = async () => {
  isLoading.value = true;
  try {
    const { data } = await SdRolesAPI.get();
    roles.value = data.payload;
    catalog.value = data.catalog;
  } catch (error) {
    useAlert(t('SD_ROLES.API.LOAD_ERROR'));
  } finally {
    isLoading.value = false;
  }
};

onMounted(fetchRoles);

const sortedRoles = computed(() =>
  [...roles.value].sort((a, b) => a.position - b.position || a.id - b.id)
);

const openEditor = (role = null) => {
  editorRole.value = role;
  showEditor.value = true;
};

const closeEditor = () => {
  showEditor.value = false;
  editorRole.value = null;
};

const onSaved = () => {
  closeEditor();
  fetchRoles();
};

const deleteRole = async role => {
  // eslint-disable-next-line no-alert
  if (!window.confirm(t('SD_ROLES.DELETE.CONFIRM', { name: role.name }))) {
    return;
  }
  try {
    await SdRolesAPI.delete(role.id);
    useAlert(t('SD_ROLES.DELETE.SUCCESS'));
    fetchRoles();
  } catch (error) {
    useAlert(error?.response?.data?.error || t('SD_ROLES.DELETE.ERROR'));
  }
};

const baseLabel = role =>
  role.base_role === 'administrator'
    ? t('SD_ROLES.BASE.ADMINISTRATOR')
    : t('SD_ROLES.BASE.AGENT');
</script>

<template>
  <SettingsLayout
    :is-loading="isLoading"
    :loading-message="$t('SD_ROLES.LOADING')"
    :no-records-found="!isLoading && !roles.length"
    :no-records-message="$t('SD_ROLES.EMPTY')"
  >
    <template #header>
      <BaseSettingsHeader
        :title="$t('SD_ROLES.HEADER')"
        :description="$t('SD_ROLES.DESCRIPTION')"
        feature-name="sd_roles"
      >
        <template #actions>
          <Button
            :label="$t('SD_ROLES.NEW')"
            size="sm"
            data-test-id="sd-role-new"
            @click="openEditor()"
          />
        </template>
      </BaseSettingsHeader>
    </template>

    <template #body>
      <table class="min-w-full divide-y divide-n-weak text-sm">
        <thead>
          <tr class="text-left text-n-slate-11">
            <th class="py-2 pr-4 font-medium">
              {{ $t('SD_ROLES.TABLE.NAME') }}
            </th>
            <th class="py-2 pr-4 font-medium">
              {{ $t('SD_ROLES.TABLE.BASE') }}
            </th>
            <th class="py-2 pr-4 font-medium">
              {{ $t('SD_ROLES.TABLE.MEMBERS') }}
            </th>
            <th class="py-2 font-medium text-right">
              {{ $t('SD_ROLES.TABLE.ACTIONS') }}
            </th>
          </tr>
        </thead>
        <tbody class="divide-y divide-n-weak">
          <tr
            v-for="role in sortedRoles"
            :key="role.id"
            :data-test-id="`sd-role-${role.key}`"
          >
            <td class="py-3 pr-4">
              <div class="font-medium text-n-slate-12">
                {{ role.name }}
                <span
                  v-if="role.system"
                  class="ml-1 px-1.5 py-0.5 text-xs rounded bg-n-alpha-2 text-n-slate-11"
                >
                  {{ $t('SD_ROLES.SYSTEM_BADGE') }}
                </span>
              </div>
              <div class="text-n-slate-11">{{ role.description }}</div>
            </td>
            <td class="py-3 pr-4 text-n-slate-12">{{ baseLabel(role) }}</td>
            <td class="py-3 pr-4 text-n-slate-12">{{ role.members_count }}</td>
            <td class="py-3 text-right whitespace-nowrap">
              <Button
                :label="$t('SD_ROLES.EDIT')"
                size="sm"
                slate
                faded
                @click="openEditor(role)"
              />
              <Button
                v-if="!role.system"
                :label="$t('SD_ROLES.DELETE.BUTTON')"
                size="sm"
                ruby
                faded
                class="ml-2"
                @click="deleteRole(role)"
              />
            </td>
          </tr>
        </tbody>
      </table>
    </template>

    <woot-modal v-model:show="showEditor" :on-close="closeEditor" size="medium">
      <SdRoleEditor
        v-if="showEditor"
        :role="editorRole"
        :catalog="catalog"
        @saved="onSaved"
        @close="closeEditor"
      />
    </woot-modal>
  </SettingsLayout>
</template>
