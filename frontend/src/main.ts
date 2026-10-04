import { createApp } from 'vue';
import App from './App.vue';
import AuthErrorPage from './components/AuthErrorPage.vue';
import Icon from './components/Icon.vue';
import { press } from './lib/motion.ts';
import './style.css';

const isAuthError = window.location.pathname === '/auth/callback';
const error = new URLSearchParams(window.location.search).get('error');
if (isAuthError) {
  // Remove authorization codes and state before mounting the error page.
  window.history.replaceState(null, '', window.location.pathname);
  document.title = '登录未完成 · 一室光';
}

createApp(isAuthError ? AuthErrorPage : App, isAuthError ? { error } : undefined)
  .component('AppIcon', Icon)
  .directive('press', press)
  .mount('#app');
