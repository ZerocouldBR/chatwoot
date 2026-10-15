<script setup>
import { computed, nextTick, ref, watch } from 'vue';
import { useEventListener } from '@vueuse/core';
import { useI18n } from 'vue-i18n';
import Icon from 'dashboard/components-next/icon/Icon.vue';
import TeleportWithDirection from 'dashboard/components-next/TeleportWithDirection.vue';

// The system's own select: a button that opens a floating list (with search when the list is long), keyboard
// navigation and a check on the chosen option. The list is teleported so panels and dialogs never clip it.
const props = defineProps({
  options: {
    type: Array,
    default: () => [],
    validator: options =>
      options.every(
        opt => typeof opt === 'object' && 'value' in opt && 'label' in opt
      ),
  },
  groups: {
    type: Array,
    default: () => [],
    validator: groups =>
      groups.every(
        group =>
          'label' in group &&
          Array.isArray(group.options) &&
          group.options.every(opt => 'value' in opt && 'label' in opt)
      ),
  },
  placeholder: {
    type: String,
    default: '',
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: '',
  },
  ariaLabel: {
    type: String,
    default: '',
  },
  // Borderless trigger that reads like text, for pickers inside sentences or end-aligned rows.
  ghost: {
    type: Boolean,
    default: false,
  },
});

const modelValue = defineModel({
  type: [String, Number, Boolean],
  default: '',
});

// Long lists get a search box.
const SEARCH_THRESHOLD = 8;
const PANEL_GAP = 6;
const PANEL_MAX_HEIGHT = 288;

const { t } = useI18n();
const trigger = ref(null);
const panel = ref(null);
const searchInput = ref(null);
const isOpen = ref(false);
const query = ref('');
const activeIndex = ref(-1);
const position = ref({ top: 0, left: 0, width: 0, openUp: false });

const sections = computed(() =>
  props.groups.length ? props.groups : [{ label: '', options: props.options }]
);
const allOptions = computed(() =>
  sections.value.flatMap(section => section.options)
);
const isSearchable = computed(() => allOptions.value.length > SEARCH_THRESHOLD);
const filteredSections = computed(() => {
  const term = query.value.trim().toLowerCase();
  if (!term) return sections.value;
  return sections.value
    .map(section => ({
      ...section,
      options: section.options.filter(option =>
        String(option.label).toLowerCase().includes(term)
      ),
    }))
    .filter(section => section.options.length);
});
const visibleOptions = computed(() =>
  filteredSections.value.flatMap(section => section.options)
);
const selected = computed(() =>
  allOptions.value.find(option => option.value === modelValue.value)
);

const place = () => {
  const rect = trigger.value?.getBoundingClientRect();
  if (!rect) return;
  const spaceBelow = window.innerHeight - rect.bottom;
  const openUp = spaceBelow < PANEL_MAX_HEIGHT && rect.top > spaceBelow;
  position.value = {
    top: openUp ? rect.top - PANEL_GAP : rect.bottom + PANEL_GAP,
    left: rect.left,
    width: rect.width,
    openUp,
  };
};

const panelStyle = computed(() => ({
  top: `${position.value.top}px`,
  left: `${position.value.left}px`,
  minWidth: `${position.value.width}px`,
  transform: position.value.openUp ? 'translateY(-100%)' : undefined,
}));

const open = async () => {
  if (props.disabled || isOpen.value) return;
  place();
  query.value = '';
  activeIndex.value = Math.max(
    visibleOptions.value.findIndex(option => option.value === modelValue.value),
    0
  );
  isOpen.value = true;
  await nextTick();
  if (isSearchable.value) searchInput.value?.focus();
  panel.value
    ?.querySelector('[data-active="true"]')
    ?.scrollIntoView({ block: 'nearest' });
};

const close = () => {
  isOpen.value = false;
};

const choose = option => {
  if (!option || option.disabled) return;
  modelValue.value = option.value;
  close();
  trigger.value?.focus();
};

const move = step => {
  const count = visibleOptions.value.length;
  if (!count) return;
  let index = activeIndex.value;
  for (let tries = 0; tries < count; tries += 1) {
    index = (index + step + count) % count;
    if (!visibleOptions.value[index].disabled) break;
  }
  activeIndex.value = index;
  nextTick(() =>
    panel.value
      ?.querySelector('[data-active="true"]')
      ?.scrollIntoView({ block: 'nearest' })
  );
};

// Typing on the closed button jumps to the first option starting with that letter.
const typeAhead = key => {
  const index = allOptions.value.findIndex(option =>
    String(option.label).toLowerCase().startsWith(key.toLowerCase())
  );
  if (index >= 0) modelValue.value = allOptions.value[index].value;
};

const onKeydown = event => {
  const { key } = event;
  if (!isOpen.value) {
    if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(key)) {
      event.preventDefault();
      open();
    } else if (key.length === 1 && !isSearchable.value) {
      typeAhead(key);
    }
    return;
  }
  if (key === 'ArrowDown' || key === 'ArrowUp') {
    event.preventDefault();
    move(key === 'ArrowDown' ? 1 : -1);
  } else if (key === 'Enter') {
    event.preventDefault();
    choose(visibleOptions.value[activeIndex.value]);
  } else if (key === 'Escape' || key === 'Tab') {
    close();
  }
};

watch(query, () => {
  activeIndex.value = visibleOptions.value.findIndex(
    option => !option.disabled
  );
});

useEventListener(document, 'pointerdown', event => {
  if (!isOpen.value) return;
  if (
    trigger.value?.contains(event.target) ||
    panel.value?.contains(event.target)
  )
    return;
  close();
});
useEventListener(window, 'resize', () => isOpen.value && place());
useEventListener(
  window,
  'scroll',
  event => {
    if (isOpen.value && !panel.value?.contains(event.target)) place();
  },
  true
);

const optionIndex = option => visibleOptions.value.indexOf(option);
</script>

<template>
  <div class="relative w-fit" data-testid="select">
    <button
      ref="trigger"
      type="button"
      role="combobox"
      :aria-expanded="isOpen"
      aria-haspopup="listbox"
      :aria-label="ariaLabel || undefined"
      class="flex items-center w-full gap-2 text-sm text-start disabled:opacity-60 disabled:cursor-not-allowed"
      :class="
        ghost
          ? 'justify-end'
          : [
              'h-9 px-3 rounded-lg outline outline-1 -outline-offset-1 bg-n-surface-1 dark:bg-n-solid-2',
              {
                'outline-n-weak hover:outline-n-slate-6 focus-visible:outline-n-brand':
                  !error && !disabled,
                'outline-n-brand': isOpen && !error,
                'outline-n-ruby-9': error && !disabled,
                'outline-n-weak': disabled,
              },
            ]
      "
      :disabled="disabled"
      @click="isOpen ? close() : open()"
      @keydown="onKeydown"
    >
      <Icon
        v-if="selected?.icon"
        :icon="selected.icon"
        class="size-4 shrink-0 text-n-slate-11"
      />
      <span
        class="min-w-0 truncate"
        :class="[
          selected ? 'text-n-slate-12' : 'text-n-slate-10',
          { 'flex-1': !ghost },
        ]"
      >
        {{ selected ? selected.label : placeholder }}
      </span>
      <Icon
        icon="i-lucide-chevrons-up-down"
        class="size-3.5 shrink-0 text-n-slate-10"
      />
    </button>

    <TeleportWithDirection v-if="isOpen" to="body">
      <div
        ref="panel"
        role="listbox"
        :aria-label="ariaLabel || placeholder || undefined"
        class="fixed z-[10000] flex flex-col p-1 overflow-hidden shadow-lg animate-menu-in rounded-xl bg-n-alpha-3 backdrop-blur-[100px] outline outline-1 outline-n-container"
        :class="position.openUp ? 'origin-bottom' : 'origin-top'"
        :style="panelStyle"
        @keydown="onKeydown"
      >
        <div v-if="isSearchable" class="relative p-1 pb-1.5">
          <Icon
            icon="i-lucide-search"
            class="absolute size-3.5 text-n-slate-10 top-1/2 -translate-y-1/2 ltr:left-3.5 rtl:right-3.5 -mt-px"
          />
          <input
            ref="searchInput"
            v-model="query"
            type="text"
            :placeholder="t('DROPDOWN_MENU.SEARCH_PLACEHOLDER')"
            class="!mb-0 !h-8 !py-0 ltr:!pl-8 rtl:!pr-8 !text-sm !rounded-lg !outline-n-weak !bg-n-alpha-1"
          />
        </div>
        <ul class="overflow-y-auto max-h-64 m-0 list-none">
          <template v-for="section in filteredSections" :key="section.label">
            <li
              v-if="section.label"
              class="px-2.5 pt-2 pb-1 text-xs font-medium text-n-slate-10"
            >
              {{ section.label }}
            </li>
            <li
              v-for="option in section.options"
              :key="String(option.value)"
              role="option"
              :aria-selected="option.value === modelValue"
              :aria-disabled="option.disabled || undefined"
              :data-active="optionIndex(option) === activeIndex"
              :data-value="String(option.value)"
              class="flex items-center gap-2 px-2.5 py-1.5 text-sm rounded-lg cursor-pointer select-none"
              :class="[
                option.disabled
                  ? 'opacity-40 cursor-not-allowed'
                  : 'text-n-slate-12',
                optionIndex(option) === activeIndex && !option.disabled
                  ? 'bg-n-alpha-2'
                  : '',
              ]"
              @mousemove="activeIndex = optionIndex(option)"
              @click="choose(option)"
            >
              <Icon
                v-if="option.icon"
                :icon="option.icon"
                class="size-4 shrink-0 text-n-slate-11"
              />
              <span class="flex-1 min-w-0 truncate">{{ option.label }}</span>
              <Icon
                v-if="option.value === modelValue"
                icon="i-lucide-check"
                class="size-4 shrink-0 text-n-brand"
              />
            </li>
          </template>
          <li
            v-if="!visibleOptions.length"
            class="px-2.5 py-2 text-sm text-n-slate-10"
          >
            {{ t('DROPDOWN_MENU.EMPTY_STATE') }}
          </li>
        </ul>
      </div>
    </TeleportWithDirection>
  </div>
</template>
