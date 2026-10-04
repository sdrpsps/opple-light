<script setup lang="ts">
import { computed } from 'vue';
import { useLightSync } from '../composables/useLightSync.ts';
import { useLightCommands } from '../composables/useLightCommands.ts';
import { useLightSession } from '../composables/useLightSession.ts';
import { useLightTimer } from '../composables/useLightTimer.ts';
import { useLightUI } from '../composables/useLightUI.ts';
const { available } = useLightSync();
const { sending } = useLightCommands();
const { authenticated } = useLightSession();
const { timer, active, remaining, setTimer, cancelTimer } = useLightTimer();
const { attempt, openDialog } = useLightUI();
const description = computed(() => {
  if (timer.value?.status === 'executing') return '时间到了，正在确认关灯。';
  if (active.value)
    return `将在 ${new Date(timer.value!.due_at * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })} 关灯。`;
  if (timer.value?.status === 'failed') return '上次倒计时关灯未成功，请手动检查灯具。';
  if (timer.value?.status === 'expired') return '上次倒计时已过期，未补执行。';
  return '设置倒计时，安心休息。';
});
const busy = computed(() => !available.value || sending.value);
</script>

<template>
  <section
    class="mt-5 flex flex-wrap items-center justify-between gap-4.5 rounded-[1.25rem] border border-white/50 bg-[#edefeb] px-4.5 py-5 sm:mt-5.5 sm:gap-5 sm:rounded-[1.375rem] sm:p-6"
    aria-labelledby="timer-title"
  >
    <div class="flex items-center gap-3 sm:gap-4">
      <span
        class="grid size-10 place-items-center rounded-full bg-white/60 text-[#76827a] sm:size-11"
      >
        <AppIcon name="clock" />
      </span>
      <div>
        <h2 id="timer-title" class="text-sm font-semibold sm:text-[.9375rem]">倒计时关灯</h2>
        <p id="timer-description" class="mt-1 text-[.6875rem] text-muted sm:text-xs">
          {{ description }}
        </p>
      </div>
    </div>
    <div
      v-if="!active"
      id="timer-options"
      class="grid w-full grid-cols-4 gap-1.5 sm:flex sm:w-auto sm:gap-2"
    >
      <button
        v-for="minutes in [15, 30, 60]"
        :key="minutes"
        v-press
        class="flex min-h-11 items-center justify-center gap-1 rounded-xl bg-white/80 px-1 py-2.5 text-[.6875rem] font-medium text-[#59645d] hover:bg-white sm:px-4 sm:text-xs"
        :data-minutes="minutes"
        :disabled="busy"
        @click="attempt(() => setTimer(minutes))"
      >
        {{ minutes }} 分钟
      </button>
      <button
        id="custom-timer"
        v-press
        class="flex min-h-11 items-center justify-center gap-1 rounded-xl bg-white/80 px-1 py-2.5 text-[.6875rem] font-medium text-[#59645d] hover:bg-white sm:px-4 sm:text-xs"
        :disabled="busy"
        @click="openDialog('timer')"
      >
        自定义
        <AppIcon name="chevron" class="size-3" />
      </button>
    </div>
    <div v-else id="timer-active" class="ml-13 flex items-center gap-6 sm:ml-0">
      <div class="flex items-baseline gap-2">
        <span id="timer-remaining" class="text-2xl tracking-tight text-[#627168] tabular-nums">
          {{ remaining }}
        </span>
        <small class="text-xs text-muted">后关灯</small>
      </div>
      <button
        id="cancel-timer"
        v-press
        class="inline-flex min-h-11 items-center justify-center gap-1 rounded-[.625rem] bg-transparent px-2 py-1.5 text-xs text-[#866636] hover:bg-[#e9e3d6]/40 [&_svg]:size-3.75"
        :disabled="timer?.status === 'executing' || !authenticated"
        @click="cancelTimer"
      >
        取消倒计时
      </button>
    </div>
  </section>
</template>
