'use strict';
const $ = id => document.getElementById(id);
let snapshot = null, scenes = [], selectedId = localStorage.getItem('opple-light') || 'bedroom';
let authenticated = false, connectionLost = false, editingScene = null, serverOffset = 0;
let pendingTarget = null, sending = false, toastTimeout = null, updatePromise = null;
let pointerRange = null, lastTimerStatus = null, sceneSignature = null;
const terminalStatuses = ['confirmed', 'staged', 'failed', 'expired', 'cancelled', 'superseded'];

function icon(name) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', `#i-${name}`); svg.append(use); svg.setAttribute('aria-hidden', 'true'); return svg;
}
function currentLight() { return snapshot?.lights.find(light => light.id === selectedId); }
function notify(message, error = false) {
  clearTimeout(toastTimeout); $('toast').textContent = message; $('toast').classList.toggle('error', error); $('toast').hidden = false;
  toastTimeout = setTimeout(() => { $('toast').hidden = true; }, error ? 6500 : 3200);
}
function showLogin() {
  authenticated = false;
  for (const dialog of document.querySelectorAll('dialog[open]')) LightMotion.close(dialog);
  if (!$('login-dialog').open) LightMotion.open($('login-dialog'));
}
async function api(path, options = {}) {
  const abort = new AbortController(), timeout = setTimeout(() => abort.abort(), 12000);
  try {
    const response = await fetch(`/api/v1${path}`, {credentials: 'same-origin', ...options,
      headers: {'Content-Type': 'application/json', ...options.headers}, signal: abort.signal});
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      if (response.status === 401 && path !== '/session') showLogin();
      const detail = Array.isArray(data.detail) ? '请检查输入的数值和格式' : data.detail;
      throw new Error(detail || `请求未完成（${response.status}）`);
    }
    if (response.status === 204) return null;
    return options.blob ? response.blob() : response.json();
  } catch (error) {
    if (error.name === 'AbortError' || error instanceof TypeError) throw new Error('服务暂时无法连接，请检查部署设备和网络');
    throw error;
  } finally { clearTimeout(timeout); }
}
function effectiveSettings(light) {
  return {...(light?.state || {}), ...(!light?.state?.power ? light?.pending_settings : {})};
}
function temperatureColor(kelvin) {
  const ratio = Math.min(1, Math.max(0, (kelvin - 3000) / 2700));
  const warm = [255, 221, 171], cool = [227, 240, 255];
  return `rgb(${warm.map((value, index) => Math.round(value + (cool[index] - value) * ratio)).join(',')})`;
}
function previewLight(kelvin, brightness) {
  $('light-visual').style.setProperty('--light-color', temperatureColor(kelvin || 4000));
  $('light-visual').style.setProperty('--glow-opacity', .16 + (brightness || 1) / 100 * .65);
  $('brightness').style.setProperty('--fill', `${brightness || 1}%`);
}
function setOutput(id, value, unit) {
  const small = document.createElement('small'); small.textContent = unit;
  $(id).replaceChildren(document.createTextNode(value == null ? '— ' : `${value} `), small);
}
function render() {
  const light = currentLight(); if (!light) return;
  const available = light.online && !connectionLost && authenticated;
  const actual = light.state, values = effectiveSettings(light), on = Boolean(actual?.power);
  $('light-name').textContent = light.name;
  document.title = `一室光 · ${light.name}`;
  $('device-status').className = `status-pill ${available ? 'online' : 'offline'}`;
  $('device-status').querySelector('span').textContent = available ? '设备在线' : '设备离线';
  $('connection-label').textContent = '局域网直连';
  $('connection-warning').hidden = available;
  $('connection-warning').textContent = connectionLost ? '服务连接中断。请检查运行服务的设备，页面会自动重连。' : (light.error || '正在连接灯具。请确认灯具有电，且服务能够访问灯具所在的局域网。');
  $('power-button').disabled = !available || sending;
  $('power-button').setAttribute('aria-checked', String(on));
  $('power-button').setAttribute('aria-label', on ? '关闭灯具' : '开启灯具');
  $('power-description').textContent = sending ? '正在更新灯光…' : !available ? '等待设备连接' : on ? '已开启，让光陪着你。' : '已关闭，留一点安静。';
  $('visual-state').textContent = !available ? '最后已知灯光' : on ? '灯光已开启' : '灯光已关闭';
  if (!actual) $('visual-state').textContent = '等待灯具响应';
  $('light-visual').classList.toggle('off', !on || !actual);
  setOutput('visual-temperature', actual?.color_temperature_kelvin, 'K');
  const temperature = $('temperature'), brightness = $('brightness');
  temperature.min = light.capabilities.min_kelvin; temperature.max = light.capabilities.max_kelvin;
  $('min-kelvin').textContent = `${temperature.min} K`; $('max-kelvin').textContent = `${temperature.max} K`;
  for (const [input, key, output, unit] of [[temperature, 'color_temperature_kelvin', 'temperature-value', 'K'], [brightness, 'brightness_percent', 'brightness-value', '%']]) {
    input.disabled = !available;
    if (pointerRange !== input.id && !sending) {
      if (values[key] != null) input.value = values[key];
      setOutput(output, values[key], unit);
    }
  }
  const presets = [...document.querySelectorAll('[data-kelvin]')];
  [light.capabilities.min_kelvin, Math.min(light.capabilities.max_kelvin, Math.max(light.capabilities.min_kelvin, 4000)), light.capabilities.max_kelvin].forEach((value, index) => {
    presets[index].dataset.kelvin = value; presets[index].disabled = !available;
    presets[index].classList.toggle('active', Math.abs((values.color_temperature_kelvin || 0) - value) < 50);
  });
  LightMotion.selectPreset(presets.findIndex(button => button.classList.contains('active')));
  if (!pointerRange && !sending) previewLight(values.color_temperature_kelvin, values.brightness_percent);
  const pending = Object.keys(light.pending_settings || {}).length > 0;
  $('control-hint').textContent = !on ? (pending ? '已保存下次开灯设置。开灯时会应用这些参数。' : '关灯时调节参数，将保存为下次开灯设置。') : '操作后会读取灯具状态，确认灯光已更新。';
  const time = light.last_seen ? new Date(light.last_seen).toLocaleTimeString('zh-CN', {hour: '2-digit', minute: '2-digit', second: '2-digit'}) : null;
  $('last-seen').textContent = time ? `${available ? '状态更新于' : '最后连接于'} ${time}` : '等待首次读取';
  const selector = $('light-select'); selector.hidden = snapshot.lights.length < 2;
  if (selector.options.length !== snapshot.lights.length) {
    selector.replaceChildren(...snapshot.lights.map(item => { const option = document.createElement('option'); option.value = item.id; option.textContent = item.name; return option; }));
  }
  selector.value = selectedId; selector.disabled = sending;
  $('add-scene').disabled = !actual;
  renderScenes(); renderTimer();
}
function renderScenes() {
  const light = currentLight(); if (!light) return;
  const available = light.online && !connectionLost && authenticated && !sending;
  const items = scenes.filter(scene => scene.light_id === selectedId);
  const signature = JSON.stringify([selectedId, items, available, light.state]);
  if (sceneSignature === signature) return;
  sceneSignature = signature;
  $('scene-list').replaceChildren();
  if (!items.length) { const p = document.createElement('p'); p.className = 'scene-empty'; p.textContent = '保存一组喜欢的灯光，下一次一触即达。'; $('scene-list').append(p); }
  for (const scene of items) {
    const active = light.state?.power && Math.abs(light.state.color_temperature_kelvin - scene.color_temperature_kelvin) <= 50 && Math.abs(light.state.brightness_percent - scene.brightness_percent) <= 1;
    const wrapper = document.createElement('div'); wrapper.className = `scene${active ? ' active' : ''}`; wrapper.dataset.icon = scene.icon;
    const apply = document.createElement('button'); apply.className = 'scene-apply'; apply.disabled = !available; apply.setAttribute('aria-label', `应用${scene.name}场景`);
    apply.setAttribute('aria-pressed', String(Boolean(active)));
    const emblem = document.createElement('span'); emblem.className = 'scene-icon'; emblem.append(icon(scene.icon));
    const text = document.createElement('span'); text.className = 'scene-copy'; const name = document.createElement('strong'), summary = document.createElement('small');
    name.textContent = scene.name; summary.textContent = `${scene.color_temperature_kelvin} K / ${scene.brightness_percent}%`; text.append(name, summary); apply.append(emblem, text);
    apply.addEventListener('click', () => applyScene(scene));
    const edit = document.createElement('button'); edit.className = 'scene-edit'; edit.textContent = '⋯'; edit.setAttribute('aria-label', `编辑${scene.name}场景`); edit.addEventListener('click', () => openScene(scene));
    wrapper.append(apply, edit); if (active) { const check = icon('check'); check.classList.add('scene-check'); wrapper.append(check); }
    $('scene-list').append(wrapper);
  }
}
function renderTimer() {
  const light = currentLight(); if (!light) return;
  const timer = light.timer, active = timer && ['active', 'executing'].includes(timer.status);
  $('timer-options').hidden = Boolean(active); $('timer-active').hidden = !active;
  if (active) {
    const seconds = Math.max(0, Math.ceil(timer.due_at - (Date.now() / 1000 + serverOffset)));
    const minutes = Math.floor(seconds / 60), remainder = seconds % 60;
    $('timer-remaining').textContent = `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`;
    $('timer-description').textContent = timer.status === 'executing' ? '时间到了，正在确认关灯。' : `将在 ${new Date(timer.due_at * 1000).toLocaleTimeString('zh-CN', {hour:'2-digit',minute:'2-digit'})} 关灯。`;
    $('cancel-timer').disabled = timer.status === 'executing';
  } else {
    $('timer-description').textContent = timer?.status === 'failed' ? '上次倒计时关灯未成功，请手动检查灯具。' : timer?.status === 'expired' ? '上次倒计时已过期，未补执行。' : '设置倒计时，安心休息。';
  }
  if (timer?.status === 'completed' && lastTimerStatus === 'executing') notify('倒计时结束，已关灯');
  lastTimerStatus = timer?.status;
}
async function update() {
  if (!authenticated) return;
  if (updatePromise) return updatePromise;
  updatePromise = (async () => {
    try {
      snapshot = await api('/status'); serverOffset = snapshot.server_time - Date.now() / 1000;
      if (!snapshot.lights.some(light => light.id === selectedId)) selectedId = snapshot.lights[0].id;
      connectionLost = false; render();
    } catch (error) { connectionLost = true; if (snapshot) render(); }
    finally { updatePromise = null; }
  })();
  return updatePromise;
}
async function waitOperation(operation) {
  const deadline = Date.now() + 45000;
  while (!terminalStatuses.includes(operation.status)) {
    if (Date.now() > deadline) throw new Error('操作确认时间较长，请刷新查看实际灯光状态');
    await new Promise(resolve => setTimeout(resolve, 300));
    operation = await api(`/operations/${operation.id}`);
  }
  if (!['confirmed', 'staged'].includes(operation.status)) throw new Error(operation.message);
  return operation;
}
async function control(target) {
  // Coalesce successive slider changes while an operation is in flight.
  pendingTarget = {...pendingTarget, ...target};
  if (sending) return;
  sending = true; render();
  try {
    while (pendingTarget) {
      const next = pendingTarget; pendingTarget = null;
      const operation = await waitOperation(await api(`/lights/${selectedId}/state`, {method:'PATCH', body:JSON.stringify(next)}));
      notify(operation.message);
      await update();
    }
  } catch (error) { pendingTarget = null; notify(error.message, true); }
  finally { sending = false; await update(); render(); }
}
async function applyScene(scene) {
  if (sending) return; sending = true; render();
  try { const operation = await waitOperation(await api(`/scenes/${scene.id}/apply`, {method:'POST'})); notify(`${scene.name}场景已应用`); }
  catch (error) { notify(error.message, true); }
  finally { sending = false; await update(); render(); if (pendingTarget) control({}); }
}
function openScene(scene = null) {
  editingScene = scene; const light = currentLight(), values = effectiveSettings(light);
  $('scene-dialog-title').textContent = scene ? '编辑灯光场景' : '保存灯光场景';
  $('scene-name').value = scene?.name || ''; $('scene-kelvin').value = scene?.color_temperature_kelvin ?? values.color_temperature_kelvin ?? 4000;
  $('scene-brightness').value = scene?.brightness_percent ?? values.brightness_percent ?? 70;
  $('scene-icon').value = scene?.icon || 'spark'; $('scene-kelvin').min = light.capabilities.min_kelvin; $('scene-kelvin').max = light.capabilities.max_kelvin;
  $('delete-scene').hidden = !scene; $('scene-error').textContent = ''; LightMotion.open($('scene-dialog'));
}
async function setTimer(minutes) {
  await api(`/lights/${selectedId}/timer`, {method:'PUT', body:JSON.stringify({minutes})});
  notify(`已设置 ${minutes} 分钟后关灯`); await update();
}
async function openSettings() {
  const light = currentLight(); $('device-details').replaceChildren();
  const name = document.createElement('strong'); name.textContent = light?.name || '灯具';
  const details = document.createElement('div'); details.textContent = `设备地址：${light?.host} · 色温范围：${light?.capabilities.min_kelvin}–${light?.capabilities.max_kelvin} K`;
  const note = document.createElement('div'); note.textContent = '配置、场景和倒计时保存在服务的数据目录。'; $('device-details').append(name, details, note);
  LightMotion.open($('settings-dialog'));
  try {
    const events = await api('/events'); $('event-list').replaceChildren();
    if (!events.length) { const p = document.createElement('p'); p.textContent = '暂无操作记录。'; $('event-list').append(p); }
    for (const event of events) {
      const row = document.createElement('div'); row.className = `event-item ${event.kind}`;
      const time = document.createElement('time'); time.dateTime = event.at; time.textContent = new Date(event.at).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
      const message = document.createElement('span'); message.textContent = event.message; row.append(time, message); $('event-list').append(row);
    }
  } catch (error) { $('event-list').textContent = error.message; }
}

$('power-button').addEventListener('click', () => control({power:!currentLight()?.state?.power}));
for (const [id, key, output, unit] of [['temperature','color_temperature_kelvin','temperature-value','K'],['brightness','brightness_percent','brightness-value','%']]) {
  const input = $(id);
  input.addEventListener('pointerdown', () => { pointerRange = id; $('light-visual').classList.add('adjusting'); });
  input.addEventListener('input', () => { setOutput(output, Number(input.value), unit); previewLight(Number($('temperature').value), Number($('brightness').value)); });
  input.addEventListener('change', () => { pointerRange = null; control({[key]:Number(input.value)}); });
  input.addEventListener('blur', () => { pointerRange = null; });
}
document.addEventListener('pointerup', () => { pointerRange = null; $('light-visual').classList.remove('adjusting'); });
document.addEventListener('pointercancel', () => { pointerRange = null; $('light-visual').classList.remove('adjusting'); });
for (const button of document.querySelectorAll('[data-kelvin]')) button.addEventListener('click', () => control({color_temperature_kelvin:Number(button.dataset.kelvin)}));
$('light-select').addEventListener('change', event => { selectedId = event.target.value; localStorage.setItem('opple-light', selectedId); lastTimerStatus = null; render(); });
$('refresh-button').addEventListener('click', async () => {
  try { await api(`/lights/${selectedId}/refresh`, {method:'POST'}); notify('已请求刷新灯具状态'); setTimeout(update, 1000); } catch (error) { notify(error.message, true); }
});
$('add-scene').addEventListener('click', () => openScene());
$('scene-form').addEventListener('submit', async event => {
  event.preventDefault(); const body = {name:$('scene-name').value.trim(),color_temperature_kelvin:Number($('scene-kelvin').value),brightness_percent:Number($('scene-brightness').value),icon:$('scene-icon').value};
  const submit = event.submitter; submit.disabled = true;
  try {
    await api(editingScene ? `/scenes/${editingScene.id}` : `/lights/${selectedId}/scenes`, {method:editingScene?'PUT':'POST',body:JSON.stringify(body)});
    scenes = await api('/scenes'); LightMotion.close($('scene-dialog')); renderScenes(); notify('场景已保存');
  } catch (error) { $('scene-error').textContent = error.message; } finally { submit.disabled = false; }
});
$('delete-scene').addEventListener('click', async () => {
  if (!editingScene || !confirm(`删除“${editingScene.name}”场景？`)) return;
  try { await api(`/scenes/${editingScene.id}`, {method:'DELETE'}); scenes = await api('/scenes'); LightMotion.close($('scene-dialog')); renderScenes(); notify('场景已删除'); }
  catch (error) { $('scene-error').textContent = error.message; }
});
for (const button of document.querySelectorAll('[data-minutes]')) button.addEventListener('click', () => setTimer(Number(button.dataset.minutes)).catch(error => notify(error.message, true)));
$('custom-timer').addEventListener('click', () => { $('timer-error').textContent = ''; LightMotion.open($('timer-dialog')); });
$('timer-form').addEventListener('submit', async event => {
  event.preventDefault(); event.submitter.disabled = true;
  try { await setTimer(Number($('timer-minutes').value)); LightMotion.close($('timer-dialog')); } catch (error) { $('timer-error').textContent = error.message; }
  finally { event.submitter.disabled = false; }
});
$('cancel-timer').addEventListener('click', async () => { try { await api(`/lights/${selectedId}/timer`, {method:'DELETE'}); await update(); notify('倒计时已取消'); } catch (error) { notify(error.message, true); } });
$('settings-button').addEventListener('click', openSettings); $('history-button').addEventListener('click', openSettings);
for (const button of document.querySelectorAll('[data-close]')) button.addEventListener('click', () => LightMotion.close($(button.dataset.close)));
$('login-dialog').addEventListener('cancel', event => event.preventDefault());
$('logout-button').addEventListener('click', async () => { try { await api('/session', {method:'DELETE'}); showLogin(); } catch (error) { notify(error.message, true); } });
$('backup-button').addEventListener('click', async () => {
  try { const blob = await api('/backup', {blob:true}); const url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url; link.download = 'opple-backup.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url),1000); notify('配置备份已导出'); } catch (error) { notify(error.message,true); }
});
async function boot() {
  try {
    const session = await api('/session'); authenticated = session.authenticated;
    if (!authenticated) { showLogin(); return; }
    scenes = await api('/scenes'); await update();
  } catch (error) { $('connection-warning').hidden = false; $('connection-warning').textContent = error.message; setTimeout(boot, 5000); }
}
document.addEventListener('visibilitychange', () => { if (!document.hidden) update(); });
setInterval(update, 3000); setInterval(renderTimer, 1000); boot();
