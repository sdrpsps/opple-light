import type { Directive } from 'vue';

// Springs keep presentation position and velocity when their target changes.
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const mobile = matchMedia('(max-width: 639px)');
interface SpringOptions {
  initial?: number;
  velocity?: number | null;
  rest?: () => void;
  damping?: number;
  response?: number;
}
interface SpringState {
  value: number;
  velocity: number;
  frame: number;
  target: number;
  render: (value: number) => void;
  rest?: () => void;
  damping: number;
  response: number;
}
interface DragState {
  start: number;
  initial: number;
  history: { y: number; at: number }[];
  moved: boolean;
}
type PressElement = HTMLElement & { disabled?: boolean };
const springs = new WeakMap<HTMLElement, SpringState>();
const pressControllers = new WeakMap<HTMLElement, AbortController>();

export function stopSpring(element: HTMLElement) {
  const state = springs.get(element);
  if (state) cancelAnimationFrame(state.frame);
  springs.delete(element);
}

export function spring(
  element: HTMLElement,
  target: number,
  render: (value: number) => void,
  options: SpringOptions = {},
) {
  const state = springs.get(element) ?? {
    value: options.initial ?? target,
    velocity: 0,
    frame: 0,
    target,
    render,
    damping: 1,
    response: 0.32,
  };
  springs.set(element, state);
  Object.assign(state, {
    target,
    render,
    rest: options.rest,
    damping: options.damping ?? 1,
    response: options.response ?? 0.32,
  });
  if (options.velocity != null) state.velocity = options.velocity;
  if (reduced.matches) {
    cancelAnimationFrame(state.frame);
    Object.assign(state, { frame: 0, value: target, velocity: 0 });
    render(target);
    state.rest?.();
    return state;
  }
  if (state.frame) return state;
  let previous = performance.now();
  function tick(now: number) {
    const elapsed = Math.min(0.04, Math.max(0.001, (now - previous) / 1000));
    previous = now;
    const omega = (2 * Math.PI) / state.response;
    const steps = Math.ceil(elapsed / 0.008),
      dt = elapsed / steps;
    for (let i = 0; i < steps; i++) {
      state.velocity +=
        (-omega * omega * (state.value - state.target) -
          2 * state.damping * omega * state.velocity) *
        dt;
      state.value += state.velocity * dt;
    }
    state.render(state.value);
    if (Math.abs(state.velocity) < 0.003 && Math.abs(state.value - state.target) < 0.0003) {
      Object.assign(state, { value: state.target, velocity: 0, frame: 0 });
      state.render(state.value);
      state.rest?.();
    } else state.frame = requestAnimationFrame(tick);
  }
  state.frame = requestAnimationFrame(tick);
  return state;
}

export function bindDialog(
  dialog: HTMLDialogElement,
  { dismissible, onClose }: { dismissible: boolean; onClose: () => void },
) {
  const controller = new AbortController(),
    options = { signal: controller.signal };
  let closing = false;
  let drag: DragState | null = null;
  const distance = () => (mobile.matches ? dialog.offsetHeight + 24 : 28);
  function paint(progress: number) {
    const clamped = Math.max(0, Math.min(1, progress));
    dialog.style.setProperty('--sheet-progress', String(clamped));
    dialog.style.opacity = String(clamped);
    dialog.style.transform = reduced.matches
      ? 'none'
      : mobile.matches
        ? `translateY(${(1 - progress) * distance()}px)`
        : `translateY(${(1 - progress) * distance()}px) scale(${0.97 + progress * 0.03})`;
  }
  function open() {
    closing = false;
    if (!dialog.open) {
      dialog.showModal();
      stopSpring(dialog);
      paint(0);
    }
    spring(dialog, 1, paint, { initial: 0 });
  }
  function close(velocity: number | null = null, gesture = false) {
    if (!dialog.open || closing) return;
    closing = true;
    spring(dialog, 0, paint, {
      velocity,
      damping: gesture ? 0.85 : 1,
      rest: () => {
        if (closing) {
          dialog.close();
          dialog.style.removeProperty('transform');
        }
      },
    });
  }
  function dismiss(velocity: number | null = null, gesture = false) {
    onClose();
    close(velocity, gesture);
  }
  dialog.addEventListener(
    'cancel',
    (event) => {
      event.preventDefault();
      if (dismissible) dismiss();
    },
    options,
  );
  dialog.addEventListener(
    'click',
    (event) => {
      if (!dismissible || event.target !== dialog) return;
      const r = dialog.getBoundingClientRect();
      if (
        event.clientX < r.left ||
        event.clientX > r.right ||
        event.clientY < r.top ||
        event.clientY > r.bottom
      )
        dismiss();
    },
    options,
  );
  const handle = dialog.querySelector<HTMLElement>('.dialog-heading');
  if (dismissible && handle) {
    handle.addEventListener(
      'pointerdown',
      (event) => {
        if (
          !mobile.matches ||
          (event.target instanceof Element && event.target.closest('button')) ||
          event.button !== 0
        )
          return;
        const state = springs.get(dialog);
        drag = {
          start: event.clientY,
          initial: state?.value ?? 1,
          history: [{ y: event.clientY, at: event.timeStamp }],
          moved: false,
        };
        handle.setPointerCapture(event.pointerId);
        if (state) {
          cancelAnimationFrame(state.frame);
          state.frame = 0;
        }
      },
      options,
    );
    handle.addEventListener(
      'pointermove',
      (event) => {
        if (!drag) return;
        const delta = event.clientY - drag.start;
        if (!drag.moved && Math.abs(delta) < 8) return;
        drag.moved = true;
        drag.history.push({ y: event.clientY, at: event.timeStamp });
        drag.history = drag.history.filter((point) => event.timeStamp - point.at <= 100);
        const size = distance(),
          y = (1 - drag.initial) * size + delta;
        const resisted = y < 0 ? (y * size * 0.55) / (size + 0.55 * Math.abs(y)) : y;
        const state = springs.get(dialog)!;
        state.value = 1 - resisted / size;
        paint(state.value);
      },
      options,
    );
    function release(event: PointerEvent) {
      if (!drag || !handle) return;
      if (handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId);
      const first = drag.history[0],
        last = drag.history.at(-1)!;
      const velocity =
        event.timeStamp - last.at > 100
          ? 0
          : ((last.y - first.y) / Math.max(1, last.at - first.at)) * 1000;
      const state = springs.get(dialog)!,
        size = distance();
      const projected = (1 - state.value) * size + ((velocity / 1000) * 0.99) / (1 - 0.99);
      if (event.type !== 'pointercancel' && drag.moved && projected > size * 0.35)
        dismiss(-velocity / size, true);
      else {
        closing = false;
        spring(dialog, 1, paint, {
          velocity: -velocity / size,
          damping: drag.moved ? 0.85 : 1,
        });
      }
      drag = null;
    }
    handle.addEventListener('pointerup', release, options);
    handle.addEventListener('pointercancel', release, options);
  }
  reduced.addEventListener(
    'change',
    () => {
      const state = springs.get(dialog);
      if (dialog.open && state) spring(dialog, state.target, paint, { rest: state.rest });
    },
    options,
  );
  return {
    open,
    close,
    dismiss,
    destroy() {
      controller.abort();
      stopSpring(dialog);
      if (dialog.open) dialog.close();
    },
  };
}

export const press: Directive<PressElement> = {
  mounted(element) {
    const controller = new AbortController();
    pressControllers.set(element, controller);
    const options = { signal: controller.signal };
    element.addEventListener(
      'pointerdown',
      (event) => {
        if (element.disabled || event.button !== 0) return;
        spring(
          element,
          0.965,
          (value) => {
            element.style.transform = `scale(${value})`;
          },
          { initial: 1, response: 0.22 },
        );
      },
      options,
    );
    const release = () => {
      if (springs.has(element))
        spring(
          element,
          1,
          (value) => {
            element.style.transform = `scale(${value})`;
          },
          { response: 0.28 },
        );
    };
    document.addEventListener('pointerup', release, options);
    document.addEventListener('pointercancel', release, options);
  },
  unmounted(element) {
    pressControllers.get(element)?.abort();
    pressControllers.delete(element);
    stopSpring(element);
  },
};
