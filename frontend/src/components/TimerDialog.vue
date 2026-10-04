<script setup lang="ts">
import { ref } from 'vue';
import { errorMessage } from '../lib/api.ts';
import AppDialog from './AppDialog.vue';
import { useLightTimer } from '../composables/useLightTimer.ts';
import { useLightUI } from '../composables/useLightUI.ts';
const { setTimer } = useLightTimer();
const { dialog, closeDialog } = useLightUI();
const minutes = ref(45),
  error = ref(''),
  busy = ref(false);
async function submit() {
  busy.value = true;
  try {
    await setTimer(minutes.value);
    closeDialog('timer');
  } catch (failure) {
    error.value = errorMessage(failure);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <AppDialog
    id="timer-dialog"
    :open="dialog === 'timer'"
    title="倒计时关灯"
    @open="error = ''"
    @close="closeDialog('timer')"
  >
    <form id="timer-form" class="dialog-body px-6 pt-3 pb-7" @submit.prevent="submit">
      <label for="timer-minutes" class="mb-2 block text-xs font-medium text-[#6e767c]">
        多少分钟后关灯？
      </label>
      <input
        id="timer-minutes"
        v-model.number="minutes"
        type="number"
        min="1"
        max="1440"
        required
        class="min-h-12 w-full min-w-0 rounded-xl border border-[#e6e9e3] bg-[#f6f7f4] px-3.5 py-3 text-base focus:border-[#c8a670] focus:bg-white"
      />
      <p class="mt-3 text-xs leading-relaxed text-muted">支持 1–1440 分钟，设置后可以随时取消。</p>
      <p id="timer-error" class="mt-3 text-xs leading-relaxed text-[#aa6058]" role="alert">
        {{ error }}
      </p>
      <button
        v-press
        type="submit"
        class="inline-flex min-h-12 items-center justify-center rounded-xl bg-[#b58c51] px-4 py-3 text-center text-sm font-medium text-white hover:bg-[#a67b3f] mt-4 w-full"
        :disabled="busy"
      >
        {{ busy ? '正在设置…' : '开始倒计时' }}
      </button>
    </form>
  </AppDialog>
</template>
