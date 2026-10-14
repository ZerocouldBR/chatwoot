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
    viewBox="0 0 64 64"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    <rect width="64" height="64" rx="15" fill="#13324A" />
    <g transform="translate(6 5) scale(0.8125)">
      <path
        d="M18 10h28a10 10 0 0 1 10 10v16a10 10 0 0 1-10 10H38l-6 9-6-9h-8A10 10 0 0 1 8 36V20a10 10 0 0 1 10-10Z"
        fill="#5EEAD4"
      />
      <path
        d="M21 28.5l7.5 7.5L43 21.5"
        stroke="#0B1622"
        stroke-width="6"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </g>
  </svg>
</template>
