<script setup lang="ts">
import AppDialog from './AppDialog.vue';
import { useLightSync } from '../composables/useLightSync.ts';
import { useLightSession } from '../composables/useLightSession.ts';
import { useLightSettings } from '../composables/useLightSettings.ts';
import { useLightUI } from '../composables/useLightUI.ts';
const { light } = useLightSync();
const { loginEnabled, logout } = useLightSession();
const { events, eventError, eventsLoading, backup } = useLightSettings();
const { dialog, closeDialog } = useLightUI();
const date = (at: string) =>
  new Date(at).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
</script>

<template>
  <AppDialog
    id="settings-dialog"
    :open="dialog === 'settings'"
    title="设置与记录"
    class="settings-dialog"
    @close="closeDialog('settings')"
  >
    <div class="dialog-body px-6 pt-3 pb-7">
      <div
        id="device-details"
        class="rounded-2xl bg-[#f0f2ed] p-4 text-xs leading-relaxed text-[#75806f]"
      >
        <strong class="font-semibold text-[#3a4238]">{{ light?.name || '灯具' }}</strong>
        <div>
          设备地址：{{ light?.host || '—' }} · 色温范围：{{
            light?.capabilities.min_kelvin || '—'
          }}–{{ light?.capabilities.max_kelvin || '—' }} K
        </div>
        <div>配置、场景和倒计时保存在服务的数据目录。</div>
      </div>
      <div class="my-5 flex flex-wrap gap-3">
        <button
          id="backup-button"
          v-press
          class="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border border-[#e6e9e2] bg-[#f3f4f0] px-4 py-2 text-xs text-[#687568] hover:bg-[#e6e9e2]"
          @click="backup"
        >
          <AppIcon name="download" />
          导出配置备份
        </button>
        <button
          v-if="loginEnabled"
          id="logout-button"
          v-press
          class="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border border-[#e6e9e2] bg-[#f3f4f0] px-4 py-2 text-xs text-[#687568] hover:bg-[#e6e9e2]"
          @click="logout"
        >
          退出登录
        </button>
      </div>
      <h3 class="mb-3 text-sm font-semibold">最近操作</h3>
      <div id="event-list" class="max-h-64 overflow-y-auto">
        <p v-if="eventError || !events.length" class="py-3 text-xs text-muted">
          {{ eventsLoading ? '正在读取操作记录…' : eventError || '暂无操作记录。' }}
        </p>
        <div
          v-for="(event, index) in events"
          :key="event.id || index"
          class="flex gap-3 border-b border-[#edf0e9] py-3 text-xs"
          :class="event.kind"
        >
          <time :datetime="event.at" class="shrink-0 text-muted">
            {{ date(event.at) }}
          </time>
          <span class="text-[#667062]">{{ event.message }}</span>
        </div>
      </div>
      <p class="mt-5 text-xs text-muted">一室光 1.0 · OPPLE 本地控制</p>
    </div>
  </AppDialog>
</template>
