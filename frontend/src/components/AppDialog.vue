<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue';
import { bindDialog } from '../lib/motion.ts';
const props = defineProps({
  open: Boolean,
  title: String,
  dismissible: { type: Boolean, default: true },
});
const emit = defineEmits(['open', 'close']);
const element = ref<HTMLDialogElement | null>(null);
let motion: ReturnType<typeof bindDialog> | undefined;
function open() {
  if (!motion) return;
  emit('open');
  motion.open();
}
onMounted(() => {
  motion = bindDialog(element.value!, {
    dismissible: props.dismissible,
    onClose: () => emit('close'),
  });
  if (props.open) open();
});
watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) open();
    else motion?.close();
  },
);
onUnmounted(() => motion?.destroy());
defineExpose({ open, close: () => motion?.close() });
</script>

<template>
  <dialog ref="element" :aria-label="title" class="app-dialog">
    <div
      v-if="dismissible"
      class="dialog-heading flex items-center justify-between gap-3 px-6 pt-6 pb-2"
    >
      <h2 class="text-lg font-semibold tracking-tight">{{ title }}</h2>
      <button
        v-press
        class="inline-flex size-11 shrink-0 items-center justify-center rounded-full bg-white/65 text-[#545b62] hover:bg-white"
        :aria-label="`关闭${title}`"
        @click="motion?.dismiss()"
      >
        <AppIcon name="close" />
      </button>
    </div>
    <slot />
  </dialog>
</template>

<style scoped>
.app-dialog {
  width: min(27.5rem, calc(100% - 2rem));
  max-height: 85dvh;
  margin: auto;
  padding: 0;
  border: 1px solid #ffffffbb;
  border-radius: 1.75rem;
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(24px) saturate(150%);
  box-shadow: 0 24px 100px #1d26302b;
  overscroll-behavior: contain;
}

.app-dialog::backdrop {
  background: rgba(25, 28, 32, calc(var(--sheet-progress, 1) * 0.25));
}

@media (max-width: 639px) {
  .app-dialog:not(.login-dialog) {
    width: 100%;
    max-width: 100%;
    max-height: 90dvh;
    margin: auto 0 0;
    border-radius: 1.75rem 1.75rem 0 0;
    border-bottom: 0;
    padding-bottom: env(safe-area-inset-bottom);
  }

  .dialog-heading {
    padding: 1.75rem 1.375rem 0.5rem;
    position: sticky;
    top: 0;
    z-index: 1;
    background: #ffffffed;
    touch-action: none;
    cursor: grab;
  }

  .dialog-heading::before {
    content: '';
    position: absolute;
    top: 0.625rem;
    left: calc(50% - 1.125rem);
    width: 2.25rem;
    height: 0.25rem;
    border-radius: 0.25rem;
    background: #cdd2cc;
  }
}

@media (prefers-reduced-transparency: reduce) {
  .app-dialog {
    backdrop-filter: none;
    background: white;
  }
}

@media (prefers-contrast: more) {
  .app-dialog {
    border: 1px solid #707770;
    background: white;
    backdrop-filter: none;
  }
}
</style>
