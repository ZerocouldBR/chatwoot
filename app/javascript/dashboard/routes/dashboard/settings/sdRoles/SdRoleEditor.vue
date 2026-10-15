<script setup>
// ServiceDesk M13: editor de um papel (nome, descrição, papel base e permissões granulares, no padrão do
// Admin Center do Zendesk). Papel de administrador tem tudo liberado e não tem permissões editáveis.
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useAlert } from 'dashboard/composables';
import Button from 'dashboard/components-next/button/Button.vue';
import Switch from 'dashboard/components-next/switch/Switch.vue';
import Select from 'dashboard/components-next/select/Select.vue';
import SdRolesAPI from 'dashboard/api/sdRoles';
import {
  PERMISSION_GROUPS,
  permissionI18nKey,
} from 'dashboard/servicedesk/roles/permissions';

const props = defineProps({
  role: { type: Object, default: null },
  catalog: { type: Object, default: () => ({ keys: [], pending_keys: [] }) },
});
const emit = defineEmits(['saved', 'close']);

const { t } = useI18n();

const isNew = computed(() => !props.role);
const name = ref(props.role?.name || '');
const description = ref(props.role?.description || '');
const baseRole = ref(props.role?.base_role || 'agent');
const isSaving = ref(false);

const catalogByKey = computed(() =>
  Object.fromEntries((props.catalog.keys || []).map(item => [item.key, item]))
);

const defaultPermissions = () => {
  const agente = Object.fromEntries(
    (props.catalog.keys || []).map(item => [
      item.key,
      item.type === 'bool' ? true : item.levels[0],
    ])
  );
  return { ...agente, 'ticket.access': 'all' };
};

const permissions = ref({
  ...(props.role?.permissions || defaultPermissions()),
});

const isAdministratorRole = computed(() => baseRole.value === 'administrator');
const isPending = key => (props.catalog.pending_keys || []).includes(key);

const groups = computed(() =>
  PERMISSION_GROUPS.map(group => ({
    ...group,
    permissions: group.permissions.filter(key => catalogByKey.value[key]),
  }))
);

const levelLabel = (key, level) =>
  t(`SD_ROLES.LEVELS.${permissionI18nKey(key)}.${level.toUpperCase()}`);

const save = async () => {
  if (!name.value.trim()) {
    useAlert(t('SD_ROLES.FORM.NAME_REQUIRED'));
    return;
  }
  isSaving.value = true;
  const payload = {
    sd_role: {
      name: name.value.trim(),
      description: description.value,
      base_role: baseRole.value,
      permissions: permissions.value,
    },
  };
  try {
    if (isNew.value) {
      await SdRolesAPI.create(payload);
    } else {
      await SdRolesAPI.update(props.role.id, payload);
    }
    useAlert(t('SD_ROLES.FORM.SAVED'));
    emit('saved');
  } catch (error) {
    useAlert(
      error?.response?.data?.message ||
        error?.response?.data?.error ||
        t('SD_ROLES.FORM.ERROR')
    );
  } finally {
    isSaving.value = false;
  }
};
</script>

<template>
  <div class="flex flex-col h-auto overflow-auto p-6 gap-4 text-sm">
    <h2 class="text-lg font-medium text-n-slate-12">
      {{
        isNew ? $t('SD_ROLES.FORM.NEW_TITLE') : $t('SD_ROLES.FORM.EDIT_TITLE')
      }}
    </h2>

    <label class="flex flex-col gap-1">
      <span class="text-n-slate-11">{{ $t('SD_ROLES.FORM.NAME') }}</span>
      <input
        v-model="name"
        data-test-id="sd-role-name"
        class="px-3 py-2 rounded-lg border border-n-weak bg-n-alpha-black2 text-n-slate-12"
        type="text"
      />
    </label>
    <label class="flex flex-col gap-1">
      <span class="text-n-slate-11">{{ $t('SD_ROLES.FORM.DESCRIPTION') }}</span>
      <textarea
        v-model="description"
        rows="2"
        class="px-3 py-2 rounded-lg border border-n-weak bg-n-alpha-black2 text-n-slate-12"
      />
    </label>
    <label class="flex flex-col gap-1">
      <span class="text-n-slate-11">{{ $t('SD_ROLES.FORM.BASE') }}</span>
      <Select
        v-model="baseRole"
        class="!w-full"
        :disabled="role?.system"
        :options="[
          { value: 'agent', label: $t('SD_ROLES.BASE.AGENT') },
          { value: 'administrator', label: $t('SD_ROLES.BASE.ADMINISTRATOR') },
        ]"
      />
    </label>

    <p
      v-if="isAdministratorRole"
      class="px-3 py-2 rounded-lg bg-n-alpha-2 text-n-slate-11"
    >
      {{ $t('SD_ROLES.FORM.ADMIN_ALL') }}
    </p>

    <template v-else>
      <section
        v-for="group in groups"
        :key="group.key"
        class="flex flex-col gap-2"
      >
        <h3 class="font-medium text-n-slate-12">
          {{ $t(`SD_ROLES.GROUPS.${group.key}`) }}
        </h3>
        <div
          v-for="key in group.permissions"
          :key="key"
          class="flex items-center justify-between gap-4 py-1"
          :data-test-id="`sd-perm-${key}`"
        >
          <span class="text-n-slate-12">
            {{ $t(`SD_ROLES.PERMISSIONS.${permissionI18nKey(key)}`) }}
            <span v-if="isPending(key)" class="text-xs text-n-slate-10">
              {{ $t('SD_ROLES.FORM.PENDING') }}
            </span>
          </span>
          <Switch
            v-if="catalogByKey[key].type === 'bool'"
            v-model="permissions[key]"
          />
          <Select
            v-else
            v-model="permissions[key]"
            :aria-label="$t(`SD_ROLES.PERMISSIONS.${permissionI18nKey(key)}`)"
            :options="
              catalogByKey[key].levels.map(level => ({
                value: level,
                label: levelLabel(key, level),
              }))
            "
          />
        </div>
      </section>
    </template>

    <div class="flex justify-end gap-2 pt-2">
      <Button
        :label="$t('SD_ROLES.FORM.CANCEL')"
        slate
        faded
        size="sm"
        @click="emit('close')"
      />
      <Button
        :label="$t('SD_ROLES.FORM.SAVE')"
        size="sm"
        :is-loading="isSaving"
        data-test-id="sd-role-save"
        @click="save"
      />
    </div>
  </div>
</template>
