<script setup lang="ts">
import BrandMark from './BrandMark.vue';
import { useLightSync } from '../composables/useLightSync.ts';
import { useLightCommands } from '../composables/useLightCommands.ts';
import { useLightSettings } from '../composables/useLightSettings.ts';
const { snapshot, selectedId, light, available } = useLightSync();
const { sending } = useLightCommands();
const { openSettings } = useLightSettings();
</script>

<template>
  <header
    class="topbar sticky top-0 z-10 -mx-2 flex h-18 items-center justify-between rounded-b-[1.25rem] px-2 sm:-mx-4 sm:h-22 sm:px-4"
  >
    <a
      class="flex items-center gap-2.5 text-lg font-semibold tracking-tight sm:text-xl"
      href="/"
      aria-label="一室光首页"
    >
      <BrandMark />
      一室光
    </a>
    <div class="flex items-center gap-2 sm:gap-4">
      <span id="connection-label" class="text-[.6875rem] font-medium text-muted sm:text-xs">
        {{ snapshot ? '局域网直连' : '正在连接' }}
      </span>
      <button
        id="settings-button"
        v-press
        class="inline-flex size-11 shrink-0 items-center justify-center rounded-full bg-white/65 text-[#545b62] hover:bg-white"
        aria-label="设置与记录"
        @click="openSettings"
      >
        <AppIcon name="settings" />
      </button>
    </div>
  </header>
  <div class="my-6 flex items-center justify-between gap-3 sm:mb-7 sm:mt-8">
    <div class="min-w-0">
      <p class="mb-2 text-xs text-muted sm:text-[.8125rem]">把灯光调到刚刚好。</p>
      <h1
        id="light-name"
        class="text-[clamp(1.75rem,3.3vw,2.6rem)] leading-tight font-semibold tracking-[-.035em] wrap-break-word"
      >
        {{ light?.name || '房间吸顶灯' }}
      </h1>
    </div>
    <div class="flex shrink-0 flex-col items-end gap-3 sm:flex-row sm:items-center">
      <select
        v-if="(snapshot?.lights.length ?? 0) > 1"
        id="light-select"
        v-model="selectedId"
        aria-label="选择灯具"
        :disabled="sending"
        class="max-w-32 rounded-xl bg-white p-2 text-xs"
      >
        <option v-for="item in snapshot?.lights" :key="item.id" :value="item.id">
          {{ item.name }}
        </option>
      </select>
      <span
        id="device-status"
        class="status-pill flex items-center gap-2 rounded-full px-2.5 py-2 text-[.625rem] font-medium sm:px-3 sm:text-xs"
        :class="available ? 'online bg-[#e8eeea] text-[#47745a]' : 'bg-[#ebe8e5] text-muted'"
      >
        <i class="size-1.5 rounded-full" :class="available ? 'bg-[#71957e]' : 'bg-[#9d97aa]'" />
        <span>{{ light ? (available ? '设备在线' : '设备离线') : '读取中' }}</span>
      </span>
    </div>
  </div>
</template>

<style scoped>
.topbar {
  background: rgba(245, 245, 243, 0.82);
  backdrop-filter: blur(24px) saturate(150%);
}

@media (prefers-reduced-transparency: reduce) {
  .topbar {
    backdrop-filter: none;
    background: var(--color-canvas);
  }
}

@media (prefers-contrast: more) {
  .topbar {
    background: white;
    backdrop-filter: none;
  }
}
</style>
