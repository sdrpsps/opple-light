<script setup lang="ts">
import { computed } from 'vue';
import { useLightSync } from '../composables/useLightSync.ts';
const props = defineProps({
  kelvin: Number,
  brightness: Number,
  adjusting: Boolean,
});
const { light, available } = useLightSync();
const style = computed(() => {
  const ratio = Math.min(1, Math.max(0, ((props.kelvin || 4000) - 3000) / 2700));
  const warm = [255, 221, 171],
    cool = [227, 240, 255];
  const rgb = warm.map((value, index) => Math.round(value + (cool[index] - value) * ratio));
  return {
    '--light-color': `rgb(${rgb.join(',')})`,
    '--glow-opacity': 0.16 + ((props.brightness || 1) / 100) * 0.65,
  };
});
</script>

<template>
  <div
    id="light-visual"
    class="light-visual relative isolate flex min-h-61.5 flex-col justify-between overflow-hidden text-[#e4e7e9] sm:min-h-113"
    :class="{ off: !light?.state?.power, adjusting }"
    :style="style"
  >
    <div
      class="relative z-2 flex items-center justify-between px-6 py-5.25 text-[.6875rem] font-medium text-[#c3c8cb] sm:px-7.5 sm:py-7 sm:text-xs"
    >
      <span id="visual-state">
        {{
          !light?.state
            ? '等待灯具响应'
            : !available
              ? '最后已知灯光'
              : light.state.power
                ? '灯光已开启'
                : '灯光已关闭'
        }}
      </span>
      <span class="rounded-full border border-white/15 bg-white/3 px-2.5 py-1 text-[.6875rem]">
        {{ light?.name || '卧室' }}
      </span>
    </div>
    <div class="room-lines" aria-hidden="true" />
    <div class="light-halo" aria-hidden="true" />
    <div class="lamp-disc" aria-hidden="true">
      <div class="lamp-surface" />
    </div>
    <div class="relative z-2 flex items-end justify-between px-6 py-5.25 sm:px-7.5 sm:py-7">
      <span class="text-[.6875rem] text-[#a9afb3] sm:text-xs">一盏灯，一室自在。</span>
      <span
        id="visual-temperature"
        class="text-[1.4rem] font-normal tracking-tight tabular-nums sm:text-[1.65rem]"
      >
        {{ light?.state?.color_temperature_kelvin ?? '—' }}
        <small class="text-xs text-[#a9afb3]">K</small>
      </span>
    </div>
  </div>
</template>

<style scoped>
.light-visual {
  background: radial-gradient(ellipse at 50% 38%, #3c4145 0, #292d30 48%, #23272a 100%);
}
.room-lines {
  position: absolute;
  inset: 48% -30% -50%;
  border-top: 1px solid #ffffff0d;
  transform: perspective(380px) rotateX(62deg);
}
.room-lines::before,
.room-lines::after {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  background: #ffffff0c;
  left: 22%;
}
.room-lines::after {
  left: 78%;
}
.light-halo {
  position: absolute;
  left: 50%;
  top: 48%;
  width: 30rem;
  height: 30rem;
  border-radius: 50%;
  transform: translate(-50%, -50%);
  background: radial-gradient(circle, var(--light-color), transparent 63%);
  opacity: var(--glow-opacity);
  filter: blur(22px);
  transition: opacity 350ms;
}
.lamp-disc {
  width: 11.875rem;
  height: 11.875rem;
  padding: 0.5rem;
  position: absolute;
  left: 50%;
  top: 48%;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  background: linear-gradient(145deg, #efeeea, #b6b7b1);
  box-shadow:
    0 26px 45px #0005,
    0 1px 0 #ffffff91,
    0 0 0 1px #ffffff28;
}
.lamp-surface {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  background: var(--light-color);
  box-shadow: inset 0 1px 14px #fff8;
  transition: background-color 300ms;
}
.light-visual.off .lamp-disc {
  background: linear-gradient(145deg, #85898b, #53585c);
  box-shadow:
    0 26px 45px #0004,
    0 1px 0 #ffffff35;
}
.light-visual.off .lamp-surface {
  background: linear-gradient(135deg, #a4a8a9, #73797c);
  box-shadow: inset 0 1px 8px #fff2;
}
.light-visual.off .light-halo {
  opacity: 0;
}
.light-visual.adjusting .lamp-surface,
.light-visual.adjusting .light-halo {
  transition: none;
}
@media (max-width: 639px) {
  .lamp-disc {
    width: 8.375rem;
    height: 8.375rem;
    padding: 0.375rem;
  }
  .light-halo {
    width: 21.25rem;
    height: 21.25rem;
  }
}
</style>
