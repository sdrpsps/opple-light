import { computed, onScopeDispose, readonly, ref, watch } from 'vue';
import {
  createEventHook,
  createSharedComposable,
  useEventListener,
  useIntervalFn,
  useStorage,
} from '@vueuse/core';
import type { Light, Snapshot } from '../types.ts';
import { errorMessage } from '../lib/api.ts';
import { useLightSession } from './useLightSession.ts';
import { useLightUI } from './useLightUI.ts';

export const effectiveSettings = (light: Light | undefined) => ({
  ...light?.state,
  ...(!light?.state?.power ? light?.pending_settings : {}),
});

export const useLightSync = createSharedComposable(() => {
  const { api, authenticated, onAuthenticated } = useLightSession();
  const { notify, attempt } = useLightUI();
  const snapshot = ref<Snapshot | null>(null);
  const selectedId = useStorage('opple-light', 'bedroom');
  const connectionLost = ref(false);
  const warning = ref('');
  const serverOffset = ref(0);
  const light = computed(() => snapshot.value?.lights.find((item) => item.id === selectedId.value));
  const available = computed(() =>
    Boolean(light.value?.online && !connectionLost.value && authenticated.value),
  );
  const values = computed(() => effectiveSettings(light.value));
  const updated = createEventHook<{ previous: Light | undefined; current: Light | undefined }>();
  let updatePromise: Promise<void> | null = null;
  let refreshTimeout: ReturnType<typeof setTimeout> | undefined;
  let disposed = false;
  async function update(): Promise<void> {
    if (!authenticated.value || disposed) return;
    if (updatePromise) return updatePromise;
    updatePromise = (async () => {
      try {
        const next = await api<Snapshot>('/status');
        if (!authenticated.value || disposed) return;
        const previous = light.value;
        snapshot.value = next;
        serverOffset.value = next.server_time - Date.now() / 1000;
        if (!next.lights.some((item) => item.id === selectedId.value))
          selectedId.value = next.lights[0]?.id || '';
        connectionLost.value = false;
        warning.value = next.lights.length ? '' : '尚未配置灯具，请检查服务配置。';
        await updated.trigger({ previous, current: light.value });
      } catch (error) {
        if (disposed) return;
        connectionLost.value = true;
        warning.value = errorMessage(error);
      } finally {
        updatePromise = null;
      }
    })();
    return updatePromise;
  }
  const refresh = () =>
    attempt(async () => {
      await api(`/lights/${selectedId.value}/refresh`, { method: 'POST' });
      if (disposed) return;
      notify('已请求刷新灯具状态');
      clearTimeout(refreshTimeout);
      refreshTimeout = setTimeout(update, 1000);
    });
  watch(
    () => light.value?.name,
    (name) => {
      if (name) document.title = `一室光 · ${name}`;
    },
  );
  useEventListener(document, 'visibilitychange', () => {
    if (document.visibilityState === 'visible') void update();
  });
  onAuthenticated(update);
  if (authenticated.value) void update();
  useIntervalFn(update, 3000);
  onScopeDispose(() => {
    disposed = true;
    clearTimeout(refreshTimeout);
  });
  return {
    snapshot: readonly(snapshot),
    selectedId,
    light,
    available,
    values,
    warning: readonly(warning),
    serverOffset: readonly(serverOffset),
    update,
    refresh,
    onUpdated: updated.on,
  };
});
