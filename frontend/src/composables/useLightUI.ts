import { onScopeDispose, reactive, readonly, ref } from 'vue';
import { createSharedComposable } from '@vueuse/core';
import { errorMessage } from '../lib/api.ts';

type Dialog = 'scene' | 'timer' | 'settings';

export const useLightUI = createSharedComposable(() => {
  const dialog = ref<Dialog | null>(null);
  const loadedDialogs = reactive({ login: false, scene: false, timer: false, settings: false });
  const toast = ref<{ message: string; error: boolean } | null>(null);
  let disposed = false;
  let toastTimeout: ReturnType<typeof setTimeout> | undefined;
  function openDialog(name: Dialog) {
    loadedDialogs[name] = true;
    dialog.value = name;
  }
  function closeDialog(name?: Dialog) {
    if (!name || dialog.value === name) dialog.value = null;
  }
  function requireLogin() {
    closeDialog();
    loadedDialogs.login = true;
  }
  function notify(message: string, error = false) {
    if (disposed) return;
    clearTimeout(toastTimeout);
    toast.value = { message, error };
    toastTimeout = setTimeout(
      () => {
        toast.value = null;
      },
      error ? 6500 : 3200,
    );
  }
  async function attempt(action: () => Promise<unknown>) {
    try {
      await action();
    } catch (error) {
      notify(errorMessage(error), true);
    }
  }
  onScopeDispose(() => {
    disposed = true;
    clearTimeout(toastTimeout);
  });
  return {
    dialog: readonly(dialog),
    loadedDialogs: readonly(loadedDialogs),
    toast: readonly(toast),
    openDialog,
    closeDialog,
    requireLogin,
    notify,
    attempt,
  };
});
