<script setup>
import { computed } from 'vue';
import { OnClickOutside } from '@vueuse/components';
import { useToggle } from '@vueuse/core';

import Button from 'dashboard/components-next/button/Button.vue';
import Avatar from 'next/avatar/Avatar.vue';
import Icon from 'dashboard/components-next/icon/Icon.vue';
import EmojiIcon from 'dashboard/components-next/emoji-icon-picker/EmojiIcon.vue';
import MultiselectDropdownItems from 'shared/components/ui/MultiselectDropdownItems.vue';

const props = defineProps({
  options: {
    type: Array,
    default: () => [],
  },
  selectedItem: {
    type: Object,
    default: () => ({}),
  },
  hasThumbnail: {
    type: Boolean,
    default: true,
  },
  multiselectorPlaceholder: {
    type: String,
    default: 'None',
  },
  noSearchResult: {
    type: String,
    default: 'No results found',
  },
  inputPlaceholder: {
    type: String,
    default: 'Search',
  },
  showEmojiIcon: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['select']);
const [showSearchDropdown, toggleDropdown] = useToggle(false);

const onCloseDropdown = () => toggleDropdown(false);
const onClickSelectItem = value => {
  emit('select', value);
  onCloseDropdown();
};

const hasValue = computed(() => {
  if (props.selectedItem && props.selectedItem.id) {
    return true;
  }
  return false;
});

const hasIcon = computed(() => {
  return props.selectedItem?.icon || false;
});

const isAgentBot = computed(
  () => props.selectedItem?.assignee_type === 'AgentBot'
);

const selectedItemName = computed(() =>
  !props.selectedItem?.name && isAgentBot.value ? '-' : props.selectedItem?.name
);

const selectedThumbnail = computed(
  () => props.selectedItem?.thumbnail || props.selectedItem?.avatar_url
);
</script>

<template>
  <OnClickOutside @trigger="onCloseDropdown">
    <div class="relative w-full mb-2" @keyup.esc="onCloseDropdown">
      <Button
        slate
        outline
        trailing-icon
        icon="i-lucide-chevrons-up-down"
        class="w-full !px-2"
        @click="
          () => toggleDropdown() // ensure that the event is not passed to the button
        "
      >
        <div class="flex items-center justify-between w-full min-w-0">
          <h4 v-if="!hasValue" class="text-sm text-ellipsis text-n-slate-12">
            {{ multiselectorPlaceholder }}
          </h4>
          <h4
            v-else
            class="items-center overflow-hidden text-sm leading-tight whitespace-nowrap text-ellipsis text-n-slate-12"
            :title="selectedItemName"
          >
            {{ selectedItemName }}
          </h4>
        </div>
        <Avatar
          v-if="hasValue && hasThumbnail && (isAgentBot || !hasIcon)"
          :src="selectedThumbnail"
          :status="selectedItem.availability_status"
          :name="selectedItemName"
          :icon-name="isAgentBot ? 'i-lucide-bot' : undefined"
          :size="24"
          hide-offline-status
          rounded-full
        >
          <template v-if="isAgentBot && selectedThumbnail" #badge>
            <div
              class="absolute z-20 flex items-center justify-center rounded-full outline outline-1 outline-n-weak bg-n-solid-1 -bottom-0.5 ltr:-right-0.5 rtl:-left-0.5 size-3.5"
            >
              <Icon icon="i-lucide-bot" class="text-n-slate-11 size-2.5" />
            </div>
          </template>
        </Avatar>
        <div
          v-else-if="hasValue && hasIcon && showEmojiIcon"
          class="flex items-center justify-center flex-shrink-0 text-sm rounded-full size-6 outline outline-1 -outline-offset-1 outline-n-weak"
        >
          <EmojiIcon
            :value="selectedItem.icon"
            :color="selectedItem.icon_color"
            class="size-3.5 !text-sm"
          />
        </div>
        <Icon
          v-else-if="hasValue && hasIcon"
          :icon="selectedItem.icon"
          class="size-5 text-n-slate-11"
        />
      </Button>
      <div
        :class="{
          'block visible': showSearchDropdown,
          'hidden invisible': !showSearchDropdown,
        }"
        class="box-border top-[2.75rem] w-full rounded-xl bg-n-alpha-3 backdrop-blur-[100px] absolute shadow-lg outline outline-1 outline-n-container p-1 z-[9999] animate-menu-in origin-top"
      >
        <MultiselectDropdownItems
          v-if="showSearchDropdown"
          :options="options"
          :selected-items="[selectedItem]"
          :has-thumbnail="hasThumbnail"
          :input-placeholder="inputPlaceholder"
          :no-search-result="noSearchResult"
          :show-emoji-icon="showEmojiIcon"
          @select="onClickSelectItem"
        />
      </div>
    </div>
  </OnClickOutside>
</template>
