import { onScopeDispose, readonly, ref } from 'vue';
import { createEventHook, createSharedComposable } from '@vueuse/core';
import type { Session } from '../types.ts';
import { createApi, errorMessage } from '../lib/api.ts';
import { useLightUI } from './useLightUI.ts';

export const useLightSession = createSharedComposable(() => {
  const { requireLogin, attempt } = useLightUI();
  const authenticated = ref(false);
  const loginEnabled = ref(true);
  const loginRequired = ref(false);
  const sessionError = ref('');
  const authenticatedEvent = createEventHook<void>();
  const invalidatedEvent = createEventHook<void>();
  let retryTimeout: ReturnType<typeof setTimeout> | undefined;
  let disposed = false;
  function showLogin() {
    if (disposed) return;
    authenticated.value = false;
    loginRequired.value = true;
    requireLogin();
    void invalidatedEvent.trigger();
  }
  const api = createApi(showLogin);
  async function boot() {
    try {
      const session = await api<Session>('/session');
      if (disposed) return;
      loginEnabled.value = session.login_enabled !== false;
      if (!session.authenticated) return showLogin();
      authenticated.value = true;
      loginRequired.value = false;
      sessionError.value = '';
      await authenticatedEvent.trigger();
    } catch (error) {
      if (disposed) return;
      sessionError.value = errorMessage(error);
      if (!loginRequired.value) retryTimeout = setTimeout(boot, 5000);
    }
  }
  const logout = () =>
    attempt(async () => {
      await api('/session', { method: 'DELETE' });
      if (!disposed) showLogin();
    });
  void boot();
  onScopeDispose(() => {
    disposed = true;
    clearTimeout(retryTimeout);
  });
  return {
    api,
    authenticated: readonly(authenticated),
    loginEnabled: readonly(loginEnabled),
    loginRequired: readonly(loginRequired),
    sessionError: readonly(sessionError),
    logout,
    onAuthenticated: authenticatedEvent.on,
    onInvalidated: invalidatedEvent.on,
  };
});
