import { computed, ref } from 'vue';
import { createSharedComposable, useIntervalFn } from '@vueuse/core';
import { useLightSession } from './useLightSession.ts';
import { useLightSync } from './useLightSync.ts';
import { useLightUI } from './useLightUI.ts';

export const useLightTimer = createSharedComposable(() => {
  const { api } = useLightSession();
  const { selectedId, light, serverOffset, update, onUpdated } = useLightSync();
  const { notify, attempt } = useLightUI();
  const now = ref(Date.now() / 1000);
  const timer = computed(() => light.value?.timer);
  const active = computed(() => ['active', 'executing'].includes(timer.value?.status ?? ''));
  const remaining = computed(() => {
    const seconds = Math.max(
      0,
      Math.ceil((timer.value?.due_at || 0) - now.value - serverOffset.value),
    );
    return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
  });
  async function setTimer(minutes: number) {
    await api(`/lights/${selectedId.value}/timer`, { method: 'PUT', json: { minutes } });
    notify(`已设置 ${minutes} 分钟后关灯`);
    await update();
  }
  const cancelTimer = () =>
    attempt(async () => {
      await api(`/lights/${selectedId.value}/timer`, { method: 'DELETE' });
      await update();
      notify('倒计时已取消');
    });
  onUpdated(({ previous, current }) => {
    if (
      previous?.id === current?.id &&
      previous?.timer?.status === 'executing' &&
      current?.timer?.status === 'completed'
    )
      notify('倒计时结束，已关灯');
  });
  useIntervalFn(() => {
    now.value = Date.now() / 1000;
  }, 1000);
  return { timer, active, remaining, setTimer, cancelTimer };
});
