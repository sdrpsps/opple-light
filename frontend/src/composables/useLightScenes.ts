import { computed, onScopeDispose, readonly, ref } from 'vue';
import { createSharedComposable } from '@vueuse/core';
import type { Scene, SceneBody } from '../types.ts';
import { errorMessage } from '../lib/api.ts';
import { useLightSession } from './useLightSession.ts';
import { useLightSync } from './useLightSync.ts';
import { useLightCommands } from './useLightCommands.ts';
import { useLightUI } from './useLightUI.ts';

export const useLightScenes = createSharedComposable(() => {
  const { api, authenticated, onAuthenticated } = useLightSession();
  const { selectedId } = useLightSync();
  const { applyScene } = useLightCommands();
  const { openDialog, closeDialog, notify } = useLightUI();
  const allScenes = ref<Scene[]>([]);
  const editingScene = ref<Scene | null>(null);
  const sceneError = ref('');
  const scenes = computed(() =>
    allScenes.value.filter((scene) => scene.light_id === selectedId.value),
  );
  let disposed = false;
  let retryTimeout: ReturnType<typeof setTimeout> | undefined;
  async function loadScenes() {
    const next = await api<Scene[]>('/scenes');
    if (!disposed && authenticated.value) {
      allScenes.value = next;
      sceneError.value = '';
    }
  }
  async function initialize() {
    if (!authenticated.value || disposed) return;
    try {
      await loadScenes();
    } catch (error) {
      if (disposed) return;
      sceneError.value = errorMessage(error);
      if (authenticated.value) retryTimeout = setTimeout(initialize, 5000);
    }
  }
  function openScene(scene: Scene | null = null) {
    editingScene.value = scene;
    openDialog('scene');
  }
  async function saveScene(body: SceneBody) {
    const scene = editingScene.value;
    await api(scene ? `/scenes/${scene.id}` : `/lights/${selectedId.value}/scenes`, {
      method: scene ? 'PUT' : 'POST',
      json: body,
    });
    await loadScenes();
    closeDialog('scene');
    notify('场景已保存');
  }
  async function deleteScene() {
    const scene = editingScene.value;
    if (!scene || !confirm(`删除“${scene.name}”场景？`)) return;
    await api(`/scenes/${scene.id}`, { method: 'DELETE' });
    await loadScenes();
    closeDialog('scene');
    notify('场景已删除');
  }
  onAuthenticated(initialize);
  if (authenticated.value) void initialize();
  onScopeDispose(() => {
    disposed = true;
    clearTimeout(retryTimeout);
  });
  return {
    scenes,
    editingScene: readonly(editingScene),
    sceneError: readonly(sceneError),
    openScene,
    saveScene,
    deleteScene,
    applyScene,
  };
});
