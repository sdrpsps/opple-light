<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue';
import { useLightSession } from './composables/useLightSession.ts';
import { useLightSync } from './composables/useLightSync.ts';
import { useLightSettings } from './composables/useLightSettings.ts';
import { useLightUI } from './composables/useLightUI.ts';
import AppHeader from './components/AppHeader.vue';
import LightPanel from './components/LightPanel.vue';
import SceneList from './components/SceneList.vue';
import TimerSection from './components/TimerSection.vue';
const LoginDialog = defineAsyncComponent(() => import('./components/LoginDialog.vue'));
const SceneDialog = defineAsyncComponent(() => import('./components/SceneDialog.vue'));
const TimerDialog = defineAsyncComponent(() => import('./components/TimerDialog.vue'));
const SettingsDialog = defineAsyncComponent(() => import('./components/SettingsDialog.vue'));
const { loginRequired, sessionError } = useLightSession();
const { light, available, warning: connectionWarning } = useLightSync();
const { openSettings } = useLightSettings();
const { loadedDialogs, toast } = useLightUI();
const warning = computed(() => {
  if (loginRequired.value) return '';
  if (sessionError.value) return sessionError.value;
  if (connectionWarning.value) return connectionWarning.value;
  if (!light.value || available.value) return '';
  return light.value.error || '正在连接灯具。请确认灯具有电，且服务能够访问灯具所在的局域网。';
});
</script>

<template>
  <div class="mx-auto max-w-298 px-4 pb-6 sm:px-6 lg:px-11">
    <AppHeader />
    <main>
      <div
        v-if="warning"
        id="connection-warning"
        class="mb-5 rounded-xl bg-[#f4e7d2] p-4 text-sm leading-relaxed text-[#806135]"
        role="status"
      >
        {{ warning }}
      </div>
      <LightPanel />
      <SceneList />
      <TimerSection />
      <footer
        class="flex items-center justify-between gap-2 pt-4 text-[.5625rem] text-muted sm:pt-5 sm:text-[.6875rem]"
      >
        <span class="flex items-center gap-1.5">
          <i class="size-1.5 rounded-full bg-[#7c9c87]" />
          本地控制，灯光就在你手中。
        </span>
        <button
          id="history-button"
          v-press
          class="inline-flex min-h-11 items-center justify-center gap-1 rounded-[.625rem] bg-transparent px-2 py-1.5 text-[.625rem] text-muted hover:bg-[#e9e3d6]/40 [&_svg]:size-3.75"
          @click="openSettings"
        >
          最近操作
          <AppIcon name="chevron" />
        </button>
      </footer>
    </main>
  </div>
  <Transition name="toast">
    <div
      v-if="toast"
      id="toast"
      class="toast"
      :class="{ error: toast.error }"
      role="status"
      aria-live="polite"
    >
      {{ toast.message }}
    </div>
  </Transition>
  <LoginDialog v-if="loadedDialogs.login" />
  <SceneDialog v-if="loadedDialogs.scene" />
  <TimerDialog v-if="loadedDialogs.timer" />
  <SettingsDialog v-if="loadedDialogs.settings" />
</template>

<style scoped>
.toast {
  position: fixed;
  z-index: 100;
  left: 50%;
  bottom: calc(1.125rem + env(safe-area-inset-bottom));
  transform: translateX(-50%);
  width: max-content;
  max-width: calc(100% - 2rem);
  padding: 0.875rem 1.25rem;
  border: 1px solid #ffffff16;
  border-radius: 1rem;
  background: #333a35ec;
  backdrop-filter: blur(18px);
  box-shadow: 0 8px 32px #2230281a;
  color: white;
  font-size: 0.8125rem;
}
.toast.error {
  background: #854d46;
}
.toast-enter-active {
  transition:
    opacity 240ms ease-out,
    transform 240ms cubic-bezier(0.22, 1, 0.36, 1);
}
.toast-leave-active {
  transition:
    opacity 180ms ease-in,
    transform 180ms ease-in;
  pointer-events: none;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translate(-50%, 0.625rem);
}
@media (prefers-reduced-transparency: reduce) {
  .toast {
    backdrop-filter: none;
    background: #333a35;
  }
}
</style>
