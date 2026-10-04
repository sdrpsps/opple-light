<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue';
import { useLightSync } from '../composables/useLightSync.ts';
import { useLightCommands } from '../composables/useLightCommands.ts';
import { useLightSession } from '../composables/useLightSession.ts';
import { spring, stopSpring } from '../lib/motion.ts';
import LightVisual from './LightVisual.vue';
const { light, available, values, selectedId, refresh } = useLightSync();
const { sending, control } = useLightCommands();
const { authenticated } = useLightSession();
const kelvin = ref(4000),
  brightness = ref(70),
  adjusting = ref(false),
  indicator = ref<HTMLElement | null>(null);
const min = computed(() => light.value?.capabilities.min_kelvin ?? 3000);
const max = computed(() => light.value?.capabilities.max_kelvin ?? 5700);
const presets = computed(() => [
  min.value,
  Math.min(max.value, Math.max(min.value, 4000)),
  max.value,
]);
const presetIndex = computed(() =>
  presets.value.findIndex((value) => Math.abs(value - kelvin.value) < 50),
);
const on = computed(() => Boolean(light.value?.state?.power));
const seen = computed(() =>
  light.value?.last_seen
    ? new Date(light.value.last_seen).toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    : null,
);
const hint = computed(() =>
  on.value
    ? '操作后会读取灯具状态，确认灯光已更新。'
    : Object.keys(light.value?.pending_settings || {}).length
      ? '已保存下次开灯设置。开灯时会应用这些参数。'
      : '关灯时调节参数，将保存为下次开灯设置。',
);
watch(
  [values, () => sending.value, () => selectedId.value],
  () => {
    if (adjusting.value || sending.value) return;
    kelvin.value = values.value.color_temperature_kelvin ?? 4000;
    brightness.value = values.value.brightness_percent ?? 70;
  },
  { immediate: true },
);
watch(
  [presetIndex, indicator],
  ([index]) => {
    if (index < 0 || !indicator.value) return;
    spring(
      indicator.value,
      index,
      (value) => {
        indicator.value!.style.transform = `translateX(${value * 100}%)`;
      },
      { initial: index, response: 0.3 },
    );
  },
  { flush: 'post', immediate: true },
);
function commit(key: 'color_temperature_kelvin' | 'brightness_percent', value: number) {
  adjusting.value = false;
  control({ [key]: value });
}
function setPreset(value: number) {
  kelvin.value = value;
  control({ color_temperature_kelvin: value });
}
onUnmounted(() => {
  if (indicator.value) stopSpring(indicator.value);
});
</script>

<template>
  <section
    class="light-panel grid overflow-hidden rounded-[1.625rem] border border-white bg-white shadow-[0_24px_60px_#242b3306] sm:grid-cols-[1.05fr_1fr]"
    aria-label="灯光控制"
  >
    <LightVisual :kelvin="kelvin" :brightness="brightness" :adjusting="adjusting || sending" />
    <div class="px-6 pt-6 pb-4.5 sm:px-7 sm:pt-7.5 lg:px-8.5">
      <div class="mb-7 flex items-center justify-between gap-3">
        <div>
          <h2 class="text-base font-semibold tracking-tight sm:text-lg">让光刚刚好</h2>
          <p
            id="power-description"
            class="mt-1.5 text-[.6875rem] leading-relaxed text-muted sm:text-xs"
          >
            {{
              sending
                ? '正在更新灯光…'
                : !available
                  ? '等待设备连接'
                  : on
                    ? '已开启，让光陪着你。'
                    : '已关闭，留一点安静。'
            }}
          </p>
        </div>
        <button
          id="power-button"
          v-press
          class="power-button"
          role="switch"
          :aria-checked="on"
          :aria-label="on ? '关闭灯具' : '开启灯具'"
          :disabled="!available || sending"
          @click="control({ power: !on })"
        >
          <AppIcon name="power" />
        </button>
      </div>
      <div>
        <div class="mb-1.5 flex items-center justify-between">
          <label for="temperature" class="text-[.8125rem] font-medium sm:text-sm">色温</label>
          <output
            id="temperature-value"
            for="temperature"
            class="text-[1.7rem] leading-none font-normal tracking-tighter tabular-nums sm:text-[1.9rem]"
          >
            {{ values.color_temperature_kelvin == null && !adjusting ? '—' : kelvin }}
            <small class="text-[.6875rem] tracking-normal text-muted">K</small>
          </output>
        </div>
        <input
          id="temperature"
          v-model.number="kelvin"
          class="range temperature-range"
          type="range"
          :min="min"
          :max="max"
          step="100"
          :disabled="!available"
          @pointerdown="adjusting = true"
          @input="adjusting = true"
          @change="commit('color_temperature_kelvin', kelvin)"
          @pointercancel="adjusting = false"
          @blur="adjusting = false"
        />
        <div class="flex justify-between text-[.6875rem] text-muted">
          <span>
            暖白
            <small id="min-kelvin" class="ml-1 text-[.625rem]">{{ min }} K</small>
          </span>
          <span>
            冷白
            <small id="max-kelvin" class="ml-1 text-[.625rem]">{{ max }} K</small>
          </span>
        </div>
        <div
          class="temperature-presets relative mt-4.5 flex rounded-xl bg-[#f0f1ee] p-1"
          aria-label="快捷色温"
        >
          <span
            ref="indicator"
            class="preset-indicator"
            aria-hidden="true"
            :hidden="presetIndex < 0"
          />
          <button
            v-for="(value, index) in presets"
            :key="index"
            v-press
            :data-kelvin="value"
            :aria-pressed="presetIndex === index"
            :disabled="!available"
            class="relative z-1 min-h-11 flex-1 rounded-lg px-2 text-xs text-muted"
            :class="{ 'text-ink': presetIndex === index }"
            @click="setPreset(value)"
          >
            {{ ['暖白', '中性', '冷白'][index] }}
          </button>
        </div>
      </div>
      <div class="mt-5.5">
        <div class="mb-1.5 flex items-center justify-between">
          <label for="brightness" class="text-[.8125rem] font-medium sm:text-sm">亮度</label>
          <output
            id="brightness-value"
            for="brightness"
            class="text-[1.7rem] leading-none font-normal tracking-tighter tabular-nums sm:text-[1.9rem]"
          >
            {{ values.brightness_percent == null && !adjusting ? '—' : brightness }}
            <small class="text-[.6875rem] tracking-normal text-muted">%</small>
          </output>
        </div>
        <div class="flex items-center gap-3.5 text-[#8e969c]">
          <AppIcon name="sun" class="size-4" />
          <input
            id="brightness"
            v-model.number="brightness"
            class="range brightness-range"
            :style="{ '--fill': `${brightness}%` }"
            type="range"
            min="1"
            max="100"
            :disabled="!available"
            @pointerdown="adjusting = true"
            @input="adjusting = true"
            @change="commit('brightness_percent', brightness)"
            @pointercancel="adjusting = false"
            @blur="adjusting = false"
          />
          <AppIcon name="sun" />
        </div>
      </div>
      <p
        id="control-hint"
        class="mt-4.5 text-[.625rem] leading-relaxed text-muted sm:text-[.6875rem]"
      >
        {{ hint }}
      </p>
      <div
        class="mt-3 flex items-center justify-between border-t border-[#f0f1ee] pt-2 text-[.5625rem] text-muted sm:text-[.625rem]"
      >
        <span id="last-seen">
          {{ seen ? `${available ? '状态更新于' : '最后连接于'} ${seen}` : '等待首次读取' }}
        </span>
        <button
          id="refresh-button"
          v-press
          class="inline-flex min-h-11 items-center justify-center gap-1 rounded-[.625rem] bg-transparent px-2 py-1.5 text-xs text-[#866636] hover:bg-[#e9e3d6]/40 [&_svg]:size-3.75"
          :disabled="!authenticated || !light"
          @click="refresh"
        >
          <AppIcon name="refresh" />
          刷新
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped src="./LightPanel.css"></style>
