<script setup lang="ts">
defineProps({ name: { type: String, required: true } });
const paths: Record<string, string[]> = {
  sun: ['M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5'],
  moon: ['M20.5 14.2A8.8 8.8 0 0 1 9.8 3.5 8.8 8.8 0 1 0 20.5 14.2Z'],
  book: ['M12 5c-3-2-6-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-3-1-6-1-9 1Zm0 0v15'],
  spark: ['m12 3 2.6 6.4L21 12l-6.4 2.6L12 21l-2.6-6.4L3 12l6.4-2.6L12 3Z'],
  power: ['M12 2v9M6.3 5.8a9 9 0 1 0 11.4 0'],
  settings: ['M4 7h16M4 17h16'],
  clock: ['M12 7v5l3 2'],
  plus: ['M12 5v14M5 12h14'],
  close: ['m6 6 12 12M6 18 18 6'],
  refresh: ['M20 5v5h-5M4 19v-5h5M5 8a8 8 0 0 1 13-3l2 3M4 16l2 3a8 8 0 0 0 13-3'],
  chevron: ['m9 5 7 7-7 7'],
  check: ['m5 12 4 4L19 6'],
  download: ['M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5'],
};
</script>

<template>
  <svg
    viewBox="0 0 24 24"
    class="size-5.5 shrink-0 fill-none stroke-current"
    aria-hidden="true"
    stroke-width="1.6"
    stroke-linecap="round"
    stroke-linejoin="round"
  >
    <circle v-if="name === 'sun'" cx="12" cy="12" r="4" />
    <circle v-if="name === 'clock'" cx="12" cy="12" r="9" />
    <template v-if="name === 'settings'">
      <circle cx="9" cy="7" r="2.5" />
      <circle cx="16" cy="17" r="2.5" />
    </template>
    <path v-for="path in paths[name] || paths.spark" :key="path" :d="path" />
  </svg>
</template>
