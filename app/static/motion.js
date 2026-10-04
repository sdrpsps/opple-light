'use strict';
// Retargetable springs retain their current position and velocity.
const LightMotion = (() => {
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const mobile = matchMedia('(max-width: 600px)');
  const springs = new WeakMap();
  const dialogs = new WeakMap();
  function spring(element, target, render, options = {}) {
    let state = springs.get(element);
    if (!state) { state = {value: options.initial ?? target, velocity: 0, frame: 0}; springs.set(element, state); }
    state.target = target; state.render = render; state.rest = options.rest;
    state.damping = options.damping ?? 1; state.response = options.response ?? .32;
    if (options.velocity != null) state.velocity = options.velocity;
    if (reduced.matches) {
      cancelAnimationFrame(state.frame); state.frame = 0; state.value = target; state.velocity = 0;
      render(target); state.rest?.(); return state;
    }
    if (state.frame) return state;
    let previous = performance.now();
    function tick(now) {
      const elapsed = Math.min(.04, Math.max(.001, (now - previous) / 1000)); previous = now;
      const omega = 2 * Math.PI / state.response;
      const steps = Math.ceil(elapsed / .008), dt = elapsed / steps;
      for (let i = 0; i < steps; i++) {
        state.velocity += (-omega * omega * (state.value - state.target) - 2 * state.damping * omega * state.velocity) * dt;
        state.value += state.velocity * dt;
      }
      state.render(state.value);
      if (Math.abs(state.velocity) < .003 && Math.abs(state.value - state.target) < .0003) {
        state.value = state.target; state.velocity = 0; state.frame = 0; state.render(state.value); state.rest?.();
      } else state.frame = requestAnimationFrame(tick);
    }
    state.frame = requestAnimationFrame(tick); return state;
  }
  function paintDialog(dialog, progress) {
    const distance = mobile.matches ? dialog.getBoundingClientRect().height + 24 : 28;
    dialog.style.setProperty('--sheet-progress', Math.max(0, Math.min(1, progress)));
    dialog.style.opacity = Math.max(0, Math.min(1, progress));
    dialog.style.transform = reduced.matches ? 'none' : mobile.matches
      ? `translateY(${(1-progress)*distance}px)`
      : `translateY(${(1-progress)*distance}px) scale(${.97 + progress*.03})`;
  }
  function open(dialog) {
    if (!dialog.open) {
      dialog.showModal(); springs.delete(dialog); paintDialog(dialog, 0);
    }
    dialogs.set(dialog, {closing: false});
    spring(dialog, 1, value => paintDialog(dialog,value), {initial:0});
  }
  function close(dialog, velocity = null, gesture = false) {
    if (!dialog.open) return;
    dialogs.set(dialog, {closing: true});
    spring(dialog, 0, value => paintDialog(dialog,value), {velocity, damping:gesture ? .85 : 1, rest:()=>{
      if (dialogs.get(dialog)?.closing) { dialog.close(); dialog.style.removeProperty('transform'); }
    }});
  }
  document.addEventListener('pointerdown', event => {
    const button = event.target.closest('button');
    if (!button || button.disabled || event.button !== 0) return;
    spring(button, .965, value=>button.style.transform=`scale(${value})`,{initial:1,response:.22});
    const release=()=>{
      spring(button,1,value=>button.style.transform=`scale(${value})`,{response:.28});
      document.removeEventListener('pointerup',release);document.removeEventListener('pointercancel',release);
    };
    document.addEventListener('pointerup',release);document.addEventListener('pointercancel',release);
  });
  document.querySelectorAll('dialog:not(.login-dialog)').forEach(dialog => {
    dialog.addEventListener('cancel', event => { event.preventDefault(); close(dialog); });
    dialog.addEventListener('click', event => {
      if (event.target !== dialog) return;
      const r=dialog.getBoundingClientRect();
      if(event.clientX<r.left || event.clientX>r.right || event.clientY<r.top || event.clientY>r.bottom) close(dialog);
    });
    const handle=dialog.querySelector('.dialog-heading'); if(!handle) return;
    let drag=null;
    handle.addEventListener('pointerdown', event=>{
      if(!mobile.matches || event.target.closest('button') || event.button!==0) return;
      const state=springs.get(dialog);
      drag={start:event.clientY,last:event.clientY,at:event.timeStamp,velocity:0,initial:state?.value??1,moved:false};
      handle.setPointerCapture(event.pointerId);
      if(state) {cancelAnimationFrame(state.frame);state.frame=0;}
    });
    handle.addEventListener('pointermove', event=>{
      if(!drag) return;
      const delta=event.clientY-drag.start;
      if(!drag.moved && Math.abs(delta)<8) return;
      drag.moved=true;
      const dt=Math.max(1,event.timeStamp-drag.at);
      drag.velocity=(event.clientY-drag.last)/dt*1000; drag.last=event.clientY; drag.at=event.timeStamp;
      const distance=dialog.getBoundingClientRect().height+24;
      const y=(1-drag.initial)*distance+delta;
      const resisted=y<0 ? (y*distance*.55)/(distance+.55*Math.abs(y)) : y;
      const state=springs.get(dialog);
      state.value=1-resisted/distance;state.velocity=-drag.velocity/distance;paintDialog(dialog,state.value);
    });
    function release(event) {
      if(!drag) return;
      if(handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId);
      const state=springs.get(dialog), distance=dialog.getBoundingClientRect().height+24;
      const velocity=event.timeStamp-drag.at>100 ? 0 : drag.velocity;
      const projected=(1-state.value)*distance+(velocity/1000)*.99/(1-.99);
      if(event.type!=='pointercancel' && drag.moved && projected>distance*.35) close(dialog,-velocity/distance,true);
      else spring(dialog,1,value=>paintDialog(dialog,value),{velocity:-velocity/distance,damping:drag.moved?.85:1});
      drag=null;
    }
    handle.addEventListener('pointerup',release);handle.addEventListener('pointercancel',release);
  });
  reduced.addEventListener('change',()=>{
    document.querySelectorAll('dialog[open]').forEach(dialog=>{
      const state=springs.get(dialog); if(state) spring(dialog,state.target,value=>paintDialog(dialog,value),{rest:state.rest});
    });
  });
  function selectPreset(index) {
    const rail=document.querySelector('.temperature-presets');
    const indicator=rail.querySelector('.preset-indicator');
    indicator.hidden=index<0;
    if(index<0) return;
    spring(indicator,index,value=>indicator.style.transform=`translateX(${value*(rail.clientWidth-8)/3}px)`,{initial:index,response:.3});
  }
  return {open,close,selectPreset};
})();
