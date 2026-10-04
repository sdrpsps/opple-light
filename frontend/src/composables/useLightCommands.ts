import { onScopeDispose, readonly, ref } from 'vue';
import { createSharedComposable } from '@vueuse/core';
import type { Operation, Scene, StatePatch } from '../types.ts';
import { errorMessage, waitOperation } from '../lib/api.ts';
import { useLightSession } from './useLightSession.ts';
import { useLightSync } from './useLightSync.ts';
import { useLightUI } from './useLightUI.ts';

export const useLightCommands = createSharedComposable(() => {
  const { api, authenticated, onInvalidated } = useLightSession();
  const { selectedId, available, update } = useLightSync();
  const { notify } = useLightUI();
  const sending = ref(false);
  // Light changes and scene application share one queue and sending state.
  let pendingTarget: StatePatch | null = null;
  let disposed = false;
  function clearPending() {
    pendingTarget = null;
  }
  async function control(target: StatePatch) {
    if (!available.value) return;
    pendingTarget = { ...pendingTarget, ...target };
    if (sending.value) return;
    sending.value = true;
    const id = selectedId.value;
    try {
      while (pendingTarget && authenticated.value && !disposed) {
        const next = pendingTarget;
        pendingTarget = null;
        const operation = await waitOperation(
          api,
          await api<Operation>(`/lights/${id}/state`, {
            method: 'PATCH',
            json: next,
          }),
        );
        notify(operation.message);
        await update();
      }
    } catch (error) {
      pendingTarget = null;
      notify(errorMessage(error), true);
    } finally {
      sending.value = false;
      await update();
    }
  }
  async function applyScene(scene: Scene) {
    if (!available.value || sending.value) return;
    sending.value = true;
    try {
      await waitOperation(
        api,
        await api<Operation>(`/scenes/${scene.id}/apply`, { method: 'POST' }),
      );
      notify(`${scene.name}场景已应用`);
    } catch (error) {
      notify(errorMessage(error), true);
    } finally {
      sending.value = false;
      await update();
      if (pendingTarget) control({});
    }
  }
  onScopeDispose(() => {
    disposed = true;
    clearPending();
  });
  onInvalidated(clearPending);
  return { sending: readonly(sending), control, applyScene };
});
