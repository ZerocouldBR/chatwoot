<script setup>
import { useAttrs } from 'vue';
import { useMapGetter } from 'dashboard/composables/store';

const attrs = useAttrs();
const globalConfig = useMapGetter('globalConfig/get');
</script>

<template>
  <img
    v-if="globalConfig.logoThumbnail"
    v-bind="attrs"
    :src="globalConfig.logoThumbnail"
  />
  <svg
    v-else
    v-once
    v-bind="attrs"
    width="16"
    height="16"
    viewBox="12.8 14 38 38"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    <rect
      x="15.6"
      y="14.5"
      width="32.4"
      height="26.1"
      rx="7.3"
      fill="#5EEAD4"
    />
    <path d="M28.6 39.5h6.2l-3.1 11.8z" fill="#5EEAD4" />
    <path
      d="M24.8 28.1l4.9 4.5 9.6-9.4"
      stroke="#0B1622"
      stroke-width="4"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
  </svg>
</template>
