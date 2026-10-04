<script setup lang="ts">
import BrandMark from './BrandMark.vue';
const props = defineProps<{ error?: string | null }>();
const messages: Record<string, string> = {
  access_denied: 'Pocket ID 拒绝了登录，请确认你的账户允许访问一室光，或重新授权。',
  invalid_request: 'Pocket ID 拒绝了登录参数，请检查客户端设置和回调地址。',
  invalid_scope: 'Pocket ID 不支持请求的登录权限，请检查客户端设置。',
  invalid_target: 'Pocket ID 未授权请求的 API 资源，请检查客户端的 API access 设置。',
};
const message =
  props.error && Object.hasOwn(messages, props.error)
    ? messages[props.error]
    : 'Pocket ID 登录未完成，登录请求可能已过期。请重新登录，或检查客户端配置后重试。';
</script>

<template>
  <div class="auth-page">
    <main class="auth-card login-dialog">
      <div class="dialog-body">
        <BrandMark large aria-hidden="true" />
        <h2>登录未完成</h2>
        <p role="alert">{{ message }}</p>
        <a
          class="inline-flex min-h-12 items-center justify-center rounded-xl bg-[#b58c51] px-4 py-3 text-center text-sm font-medium text-white hover:bg-[#a67b3f]"
          href="/auth/login"
        >
          重新通过 Pocket ID 登录
        </a>
        <a class="login-help" href="/">返回一室光</a>
      </div>
    </main>
  </div>
</template>

<style scoped>
.auth-page {
  min-height: 100dvh;
  display: grid;
  place-items: center;
  padding: 1.5rem 1rem;
}

.auth-card {
  width: min(27.5rem, 100%);
  border: 1px solid #ffffffbb;
  border-radius: 1.75rem;
  background: white;
  box-shadow: 0 24px 80px #1d263018;
}

.auth-card .dialog-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1.25rem;
  padding: 2rem;
  text-align: center;
}

.auth-card h2 {
  font-size: 1.375rem;
  font-weight: 600;
}

.auth-card p {
  font-size: 0.875rem;
  line-height: 1.65;
}

@media (max-width: 639px) {
  .auth-card {
    border-radius: 1.5rem;
  }

  .auth-card .dialog-body {
    padding: 1.875rem 1.5rem 1.5rem;
  }
}
</style>
