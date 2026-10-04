import { onScopeDispose, readonly, ref } from 'vue';
import { createSharedComposable } from '@vueuse/core';
import type { LightEvent } from '../types.ts';
import { errorMessage } from '../lib/api.ts';
import { useLightSession } from './useLightSession.ts';
import { useLightUI } from './useLightUI.ts';

export const useLightSettings = createSharedComposable(() => {
  const { api } = useLightSession();
  const { openDialog, notify, attempt } = useLightUI();
  const events = ref<LightEvent[]>([]);
  const eventError = ref('');
  const eventsLoading = ref(false);
  let disposed = false;
  let request = 0;
  async function openSettings() {
    openDialog('settings');
    const current = ++request;
    events.value = [];
    eventError.value = '';
    eventsLoading.value = true;
    try {
      const next = await api<LightEvent[]>('/events');
      if (!disposed && current === request) events.value = next;
    } catch (error) {
      if (!disposed && current === request) eventError.value = errorMessage(error);
    } finally {
      if (!disposed && current === request) eventsLoading.value = false;
    }
  }
  const backup = () =>
    attempt(async () => {
      const blob = await api('/backup', { blob: true });
      if (disposed) return;
      const url = URL.createObjectURL(blob),
        link = document.createElement('a');
      link.href = url;
      link.download = 'opple-backup.json';
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      notify('配置备份已导出');
    });
  onScopeDispose(() => {
    disposed = true;
  });
  return {
    events: readonly(events),
    eventError: readonly(eventError),
    eventsLoading: readonly(eventsLoading),
    openSettings,
    backup,
  };
});
