<script setup lang="ts">
import BrandMark from './BrandMark.vue';
import AppDialog from './AppDialog.vue';
import { useLightSession } from '../composables/useLightSession.ts';
const { loginRequired } = useLightSession();
</script>

<template>
  <AppDialog
    id="login-dialog"
    :open="loginRequired"
    :dismissible="false"
    title="欢迎回到一室光"
    class="login-dialog"
  >
    <div class="dialog-body flex flex-col items-center gap-5 text-center">
      <BrandMark large class="mb-1" />
      <h2 class="text-[1.375rem] leading-[1.35] font-semibold tracking-tight">欢迎回到一室光</h2>
      <p id="login-description" class="text-sm leading-relaxed text-muted">
        使用你的通行密钥登录，继续控制灯光。
      </p>
      <a
        id="pocket-login"
        class="inline-flex min-h-12 items-center justify-center rounded-xl bg-[#b58c51] px-4 py-3 text-center text-sm font-medium text-white hover:bg-[#a67b3f] mt-1 w-full"
        href="/auth/login"
      >
        通过 Pocket ID 登录
      </a>
      <p class="text-xs text-muted">登录由 Pocket ID 提供。</p>
    </div>
  </AppDialog>
</template>

<style scoped>
.dialog-body {
  padding: 2.25rem 2rem 1.75rem;
}
@media (max-width: 639px) {
  .login-dialog {
    border-radius: 1.5rem;
  }
  .dialog-body {
    padding: 1.875rem 1.5rem 1.5rem;
  }
}
</style>
