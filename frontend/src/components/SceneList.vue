<script setup lang="ts">
import type { Scene } from '../types.ts';
import { useLightSync } from '../composables/useLightSync.ts';
import { useLightCommands } from '../composables/useLightCommands.ts';
import { useLightSession } from '../composables/useLightSession.ts';
import { useLightScenes } from '../composables/useLightScenes.ts';
const { light, available } = useLightSync();
const { sending } = useLightCommands();
const { authenticated } = useLightSession();
const { scenes, sceneError, openScene, applyScene } = useLightScenes();
function isActive(scene: Scene) {
  const actual = light.value?.state;
  return Boolean(
    actual?.power &&
    Math.abs(actual.color_temperature_kelvin - scene.color_temperature_kelvin) <= 50 &&
    Math.abs(actual.brightness_percent - scene.brightness_percent) <= 1,
  );
}
</script>

<template>
  <section class="mt-6.5 sm:mt-8" aria-labelledby="scenes-title">
    <div class="mb-4 flex items-center justify-between gap-3">
      <div>
        <h2 id="scenes-title" class="text-base font-semibold tracking-tight sm:text-lg">
          灯光场景
        </h2>
        <p class="mt-1 text-[.6875rem] text-muted sm:text-xs">喜欢的光，一触即达。</p>
      </div>
      <button
        id="add-scene"
        v-press
        class="inline-flex min-h-11 items-center justify-center gap-1 rounded-[.625rem] bg-transparent px-2 py-1.5 text-[.625rem] text-[#866636] hover:bg-[#e9e3d6]/40 sm:text-xs [&_svg]:size-3.75"
        :disabled="!light?.state || !authenticated"
        @click="openScene()"
      >
        <AppIcon name="plus" />
        保存当前灯光
      </button>
    </div>
    <div id="scene-list" class="grid grid-cols-3 gap-2 sm:gap-3.5">
      <p v-if="!scenes.length" class="col-span-3 py-4 text-sm text-muted">
        {{ sceneError || '保存一组喜欢的灯光，下一次一触即达。' }}
      </p>
      <div
        v-for="scene in scenes"
        :key="scene.id"
        class="scene relative flex min-w-0 rounded-[1.125rem] border transition-[background-color,border-color,box-shadow] duration-150 hover:shadow-md shadow-[0_3px_14px_#252b3404] sm:rounded-[1.25rem]"
        :class="isActive(scene) ? 'active border-[#d4b37c] bg-[#faf5e9]' : 'border-white bg-white'"
        :data-icon="scene.icon"
      >
        <button
          v-press
          class="scene-apply flex min-h-33.5 w-full flex-col items-start gap-3 rounded-[inherit] bg-transparent px-2.5 py-4 text-left sm:min-h-25 sm:flex-row sm:items-center sm:gap-4 sm:p-5 sm:pr-11.5"
          :aria-label="`应用${scene.name}场景`"
          :aria-pressed="isActive(scene)"
          :disabled="!available || sending"
          @click="applyScene(scene)"
        >
          <span
            class="scene-icon grid size-8.5 shrink-0 place-items-center rounded-xl sm:size-11"
            :class="{
              'bg-[#faf0dc] text-[#b98b46]': scene.icon === 'sun',
              'bg-[#e9eff3] text-[#6e8ca2]': scene.icon === 'book',
              'bg-[#eeecf5] text-[#8a80a2]': scene.icon === 'moon',
              'bg-[#ece7f3] text-[#817098]': !['sun', 'book', 'moon'].includes(scene.icon),
            }"
          >
            <AppIcon :name="scene.icon" />
          </span>
          <span class="min-w-0">
            <strong class="block truncate text-[.8125rem] font-medium sm:text-[.9375rem]">
              {{ scene.name }}
            </strong>
            <small
              class="mt-1 block text-[.5625rem] whitespace-nowrap text-muted sm:text-[.6875rem]"
            >
              {{ scene.color_temperature_kelvin }} K / {{ scene.brightness_percent }}%
            </small>
          </span>
        </button>
        <button
          v-press
          class="scene-edit absolute top-0 right-0 size-11 rounded-full bg-transparent text-xl text-muted"
          :aria-label="`编辑${scene.name}场景`"
          :disabled="!authenticated"
          @click="openScene(scene)"
        >
          ⋯
        </button>
        <AppIcon
          v-if="isActive(scene)"
          name="check"
          class="pointer-events-none absolute right-3 bottom-3 size-3.5 text-accent"
        />
      </div>
    </div>
  </section>
</template>

<style scoped>
@media (prefers-contrast: more) {
  .scene {
    border: 1px solid #707770;
  }
}
</style>
