<script setup lang="ts">
import { reactive, ref } from 'vue';
import type { SceneBody } from '../types.ts';
import { errorMessage } from '../lib/api.ts';
import AppDialog from './AppDialog.vue';
import { useLightSync } from '../composables/useLightSync.ts';
import { useLightScenes } from '../composables/useLightScenes.ts';
import { useLightUI } from '../composables/useLightUI.ts';
const { light, values } = useLightSync();
const { editingScene, saveScene, deleteScene } = useLightScenes();
const { dialog, closeDialog } = useLightUI();
const form = reactive<SceneBody>({
  name: '',
  color_temperature_kelvin: 4000,
  brightness_percent: 70,
  icon: 'spark',
});
const error = ref(''),
  busy = ref(false);
function initializeForm() {
  const scene = editingScene.value;
  Object.assign(form, {
    name: scene?.name || '',
    icon: scene?.icon || 'spark',
    color_temperature_kelvin:
      scene?.color_temperature_kelvin ?? values.value.color_temperature_kelvin ?? 4000,
    brightness_percent: scene?.brightness_percent ?? values.value.brightness_percent ?? 70,
  });
  error.value = '';
}
async function submit() {
  busy.value = true;
  error.value = '';
  try {
    await saveScene({ ...form, name: form.name.trim() });
  } catch (failure) {
    error.value = errorMessage(failure);
  } finally {
    busy.value = false;
  }
}
async function remove() {
  busy.value = true;
  error.value = '';
  try {
    await deleteScene();
  } catch (failure) {
    error.value = errorMessage(failure);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <AppDialog
    id="scene-dialog"
    :open="dialog === 'scene'"
    :title="editingScene ? '编辑灯光场景' : '保存灯光场景'"
    @open="initializeForm"
    @close="closeDialog('scene')"
  >
    <form id="scene-form" class="dialog-body px-6 pt-3 pb-7" @submit.prevent="submit">
      <label for="scene-name" class="mb-2 block text-xs font-medium text-[#6e767c]">场景名称</label>
      <input
        id="scene-name"
        v-model="form.name"
        maxlength="20"
        required
        pattern=".*\S.*"
        placeholder="例如：睡前阅读"
        class="min-h-12 w-full min-w-0 rounded-xl border border-[#e6e9e3] bg-[#f6f7f4] px-3.5 py-3 text-base focus:border-[#c8a670] focus:bg-white"
      />
      <div class="my-4 grid grid-cols-2 gap-3">
        <div>
          <label for="scene-kelvin" class="mb-2 block text-xs font-medium text-[#6e767c]">
            色温（K）
          </label>
          <input
            id="scene-kelvin"
            v-model.number="form.color_temperature_kelvin"
            type="number"
            :min="light?.capabilities.min_kelvin || 3000"
            :max="light?.capabilities.max_kelvin || 5700"
            step="1"
            required
            class="min-h-12 w-full min-w-0 rounded-xl border border-[#e6e9e3] bg-[#f6f7f4] px-3.5 py-3 text-base focus:border-[#c8a670] focus:bg-white"
          />
        </div>
        <div>
          <label for="scene-brightness" class="mb-2 block text-xs font-medium text-[#6e767c]">
            亮度（%）
          </label>
          <input
            id="scene-brightness"
            v-model.number="form.brightness_percent"
            type="number"
            min="1"
            max="100"
            required
            class="min-h-12 w-full min-w-0 rounded-xl border border-[#e6e9e3] bg-[#f6f7f4] px-3.5 py-3 text-base focus:border-[#c8a670] focus:bg-white"
          />
        </div>
      </div>
      <label for="scene-icon" class="mb-2 block text-xs font-medium text-[#6e767c]">场景图标</label>
      <select
        id="scene-icon"
        v-model="form.icon"
        class="min-h-12 w-full min-w-0 rounded-xl border border-[#e6e9e3] bg-[#f6f7f4] px-3.5 py-3 text-base focus:border-[#c8a670] focus:bg-white"
      >
        <option value="spark">星光</option>
        <option value="sun">日光</option>
        <option value="book">阅读</option>
        <option value="moon">夜间</option>
      </select>
      <p id="scene-error" class="mt-3 text-xs leading-relaxed text-[#aa6058]" role="alert">
        {{ error }}
      </p>
      <div class="mt-5 flex justify-end gap-3">
        <button
          v-if="editingScene"
          id="delete-scene"
          v-press
          type="button"
          class="min-h-12 rounded-xl px-3 text-sm text-[#aa6058] hover:bg-red-50"
          :disabled="busy"
          @click="remove"
        >
          删除场景
        </button>
        <button
          v-press
          type="submit"
          class="inline-flex min-h-12 items-center justify-center rounded-xl bg-[#b58c51] px-4 py-3 text-center text-sm font-medium text-white hover:bg-[#a67b3f]"
          :disabled="busy"
        >
          {{ busy ? '正在保存…' : '保存场景' }}
        </button>
      </div>
    </form>
  </AppDialog>
</template>
