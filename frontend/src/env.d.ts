import type Icon from './components/Icon.vue';
import type { press } from './lib/motion.ts';

declare module 'vue' {
  interface GlobalComponents {
    AppIcon: typeof Icon;
  }
  interface GlobalDirectives {
    vPress: typeof press;
  }
}
export {};
