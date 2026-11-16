const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const TABS = ['cockpit', 'validation', 'telemetry'];
const SPEED_MAX = 180;

let state = null;
let report = null;
let selectedTab = 'cockpit';
let autoReturnToResults = false;
let androidOnline = false;
let aaosActive = false;
let androidSize = {width:1024,height:768};
let toastTimer;
let online = true;

// ---------- small UI helpers ----------

function toast(message, kind = 'info') {
  const node = $('#toast');
  node.textContent = message;
  node.className = `toast visible toast-${kind}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove('visible'), 3200);
}

// Restart a CSS animation class on an element (e.g. a "pop" when the gear changes).
function replay(el, cls) {
  if (!el || reducedMotion) return;
  el.classList.remove(cls);
  void el.offsetWidth;
  el.classList.add(cls);
}

// Ease a numeric readout toward its new value instead of jumping.
const tweens = new WeakMap();
function animateNumber(el, target) {
  if (Number(el.dataset.target) === target && el.dataset.target !== undefined) return;
  el.dataset.target = target;
  const from = Number(el.textContent) || 0;
  cancelAnimationFrame(tweens.get(el));
  if (reducedMotion || from === target) { el.textContent = target; return; }
  const start = performance.now();
  const duration = 650;
  const frame = (now) => {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - t, 3);
    el.textContent = Math.round(from + (target - from) * eased);
    if (t < 1) tweens.set(el, requestAnimationFrame(frame));
  };
  tweens.set(el, requestAnimationFrame(frame));
}

// Only touch the DOM when the rendered markup actually changed, so entry
// animations do not replay on every 450 ms poll.
function setHtml(el, html) {
  if (el.dataset.html === html) return false;
  el.dataset.html = html;
  el.innerHTML = html;
  return true;
}

function setSliderFill(value) {
  $('#speed-slider').style.setProperty('--fill', `${Math.min(100, value / SPEED_MAX * 100)}%`);
}

// ---------- navigation ----------

function tab(name) {
  if (!TABS.includes(name)) name = 'cockpit';
  const changed = name !== selectedTab;
  selectedTab = name;
  document.querySelectorAll('.page').forEach((page) => {
    const active = page.id === `${name}-page`;
    page.classList.toggle('active', active);
    if (active && changed) replay(page, 'page-enter');
  });
  document.querySelectorAll('.nav-item[data-tab]').forEach((item) => item.classList.toggle('active', item.dataset.tab === name));
  $('#page-title').innerHTML = name === 'cockpit' ? 'Cockpit <span>Overview</span>' : name === 'validation' ? 'Test <span>Validation</span>' : 'System <span>Telemetry</span>';
  history.replaceState(null, '', `#${name}`);
}
if (TABS.includes(location.hash.slice(1))) tab(location.hash.slice(1));
replay(document.querySelector('.page.active'), 'page-enter');

function time(value) {
  if (!value) return '--:--:--';
  return new Date(value).toLocaleTimeString('pt-BR', {hour12:false});
}

// ---------- state rendering ----------

function renderState(s) {
  const previous = state;
  state = s;
  animateNumber($('#speed-value'), s.speed_kmh);
  animateNumber($('#cluster-speed'), s.speed_kmh);
  $('.driver-cluster').style.setProperty('--speed', Math.min(1, s.speed_kmh / SPEED_MAX));
  if (document.activeElement !== $('#speed-slider')) {
    $('#speed-slider').value = s.speed_kmh;
    $('#speed-slider-value').textContent = `${s.speed_kmh} km/h`;
    setSliderFill(s.speed_kmh);
  }
  $('#gear-value').textContent = s.gear;
  $('#cluster-gear').textContent = s.gear;
  $('#cluster-gear').dataset.currentGear = s.gear;
  if (previous && previous.gear !== s.gear) { replay($('#cluster-gear'), 'pop'); replay($('#gear-value'), 'pop'); }
  document.querySelectorAll('#prnd-row [data-g]').forEach((g) => g.classList.toggle('active', g.dataset.g === s.gear));
  renderDriveMode(s);
  $('#gear-text').textContent = {R:'Reverse', N:'Neutral', D:'Drive'}[s.gear] || 'Park';
  document.querySelectorAll('[data-gear]').forEach((b) => b.classList.toggle('active', b.dataset.gear === s.gear));
  $('#ignition-value').textContent = s.ignition ? 'ON' : 'OFF';
  $('#ignition-dot').classList.toggle('green', s.ignition);
  $('#door-value').textContent = s.door_open ? 'OPEN' : 'CLOSED';
  $('#cluster-door').textContent = s.door_open ? 'DRIVER DOOR OPEN' : 'DOORS CLOSED';
  $('#door-dot').classList.toggle('green', !s.door_open);
  if (previous && previous.door_open !== s.door_open) replay($('#door-value'), 'pop');
  $('#projection-value').textContent = s.projection;
  $('#projection-subtitle').textContent = s.phone_connected ? 'Connected and ready' : 'Connect a phone to continue';
  $('#projection-card').classList.toggle('offline', !s.phone_connected);
  for (const [id, active] of [['bt-status',s.bluetooth],['usb-status',s.usb_connected],['phone-status',s.phone_connected]]) {
    $(`#${id}`).textContent = active ? 'ON' : 'OFF';
    $(`#${id}`).classList.toggle('off', !active);
  }
  $('#play-button').textContent = s.media_playing ? 'Ⅱ' : '▶';
  $('#play-button').dataset.event = s.media_playing ? 'pause' : 'play';
  $('#play-button').setAttribute('aria-label', s.media_playing ? 'Pausar' : 'Reproduzir');
  $('.music-card').classList.toggle('playing', s.media_playing);
  $('#progress-bar').style.width = s.media_playing ? '55%' : '39%';
  $('#phone-control').dataset.event = s.phone_connected ? 'phone_disconnect' : 'phone_connect';
  $('#phone-control').querySelector('strong').textContent = s.phone_connected ? 'Disconnect phone' : 'Connect phone';
  $('#fault-control').classList.toggle('active-fault', Boolean(s.fault));
  renderEvents($('#event-list'), s.events.slice(0, 5));
  renderEvents($('#telemetry-events'), s.events);
  const signals = [
    ['VEHICLE',s.vehicle],['IGNITION',s.ignition?'ON':'OFF'],['SPEED',`${s.speed_kmh} km/h`],['GEAR',s.gear],
    ['DRIVER DOOR',s.door_open?'OPEN':'CLOSED'],['BLUETOOTH',s.bluetooth?'ON':'OFF'],['USB',s.usb_connected?'CONNECTED':'DISCONNECTED'],
    ['PHONE',s.phone_connected?'CONNECTED':'DISCONNECTED'],['PROJECTION',s.projection],['MEDIA',s.media_playing?'PLAYING':'STOPPED'],
    ['FAULT INJECTION',s.fault||'OFF'],['EVENT COUNT',s.events.length]
  ];
  setHtml($('#signal-list'), signals.map(([label,value]) => `<div class="signal ${signalTone(label,value)}"><small>${esc(label)}</small><strong>${esc(value)}</strong></div>`).join(''));
}

// Comfort / Sport, mirroring the Unity cluster: Sport engages at 120 km/h and releases
// below 110 km/h (hysteresis, so the theme does not flicker around the threshold).
const SPORT_ON = 120, SPORT_OFF = 110;
let sport = false;
function renderDriveMode(s) {
  sport = sport ? s.speed_kmh >= SPORT_OFF : s.speed_kmh >= SPORT_ON;
  document.body.classList.toggle('mode-sport', sport);
  const mode = sport ? 'SPORT' : 'COMFORT';
  $('#drive-mode').textContent = mode;
  $('#cluster-mode').textContent = mode;
  $('#cluster-foot-mode').textContent = `${mode} MODE`;
  const links = [s.bluetooth, s.usb_connected, s.phone_connected].filter(Boolean).length;
  $('#drive-links').textContent = `${links}/3 ONLINE`;
  $('#drive-links').dataset.tone = links === 3 ? 'ok' : links ? 'warn' : 'off';
}

// Colour-codes telemetry values so state reads at a glance: ok / warn / fault / off.
function signalTone(label, value) {
  const v = String(value);
  if (label === 'FAULT INJECTION') return v === 'OFF' ? 'tone-ok' : 'tone-fault';
  if (label === 'DRIVER DOOR') return v === 'OPEN' ? 'tone-warn' : 'tone-ok';
  if (['ON','CONNECTED','PLAYING'].includes(v)) return 'tone-ok';
  if (['OFF','DISCONNECTED','STOPPED','Disconnected'].includes(v)) return 'tone-off';
  return '';
}

// Keyed by event id: only events the list has not shown before get the entry animation.
function renderEvents(container, events) {
  const shown = new Set((container.dataset.ids || '').split(',').filter(Boolean));
  const firstPaint = !container.dataset.ids;
  const ids = events.map((e) => String(e.id));
  if (ids.join(',') === container.dataset.ids) return;
  container.dataset.ids = ids.join(',');
  container.innerHTML = events.map((e) => eventHtml(e, !firstPaint && !shown.has(String(e.id)))).join('');
}

function eventHtml(event, isNew) {
  const tone = /FAULT/.test(event.source) ? ' is-fault' : '';
  return `<div class="event-item${isNew ? ' enter' : ''}${tone}"><time>${esc(time(event.time))}</time><div><strong>${esc(event.source)}</strong><span>${esc(event.message)}</span></div></div>`;
}

// ---------- validation report ----------

function renderReport(r) {
  const previous = report?.status;
  report = r;
  const labels = {idle:'No run yet',running:'Validation in progress',passed:'All checks passed',failed:'Defect detected',error:'Execution error'};
  const descriptions = {idle:'Select a scenario and run the validation.',running:'Python is driving the simulated cockpit.',passed:'The observed state matched every expected value.',failed:'Open the failed step to inspect expected and actual state.',error:r.summary};
  const icon = {idle:'◇',running:'◌',passed:'✓',failed:'!',error:'!'};
  const banner = $('#run-banner');
  banner.className = `run-banner ${r.status}`;
  const progress = r.status === 'running' ? '<span class="run-progress" aria-hidden="true"></span>' : '';
  if (setHtml(banner, `<span class="run-icon">${icon[r.status]||'◇'}</span><div><strong>${labels[r.status]||esc(r.status)}</strong><small>${esc(descriptions[r.status]||'')}</small></div>${progress}`) && previous && previous !== r.status) replay(banner, 'pop');
  const testLabel = {idle:'NO RUN YET',running:'RUNNING…',passed:'PASSED',failed:'DEFECT FOUND',error:'ERROR'};
  $('#drive-test').textContent = testLabel[r.status] || String(r.status).toUpperCase();
  $('#drive-test').dataset.tone = {passed:'ok',failed:'fault',error:'fault',running:'run'}[r.status] || 'off';
  const steps = r.steps || [];
  const container = $('#test-steps');
  const already = Number(container.dataset.count || 0);
  const html = steps.map((step,index) => `<div class="step${index >= already && previous ? ' enter' : ''} step-${esc(step.status)}"><div><strong>${String(index+1).padStart(2,'0')} · ${esc(step.label)}</strong><small>Expected: ${esc(JSON.stringify(step.expected))}<br>Actual: ${esc(JSON.stringify(step.actual))}</small></div><b class="${esc(step.status)}">${step.status==='passed'?'PASS':'FAIL'}</b></div>`).join('');
  if (setHtml(container, html)) container.dataset.count = steps.length;
  $('#result-summary').textContent = r.summary || (r.status === 'running' ? `${steps.length} steps completed` : 'Waiting for execution');
  $('#result-time').textContent = r.finished_at ? time(r.finished_at) : '—';
  $('#run-button').disabled = r.status === 'running';
  document.querySelectorAll('[data-event],[data-gear]').forEach((button) => { button.disabled = r.status === 'running'; });
  $('#speed-slider').disabled = r.status === 'running';
  if (autoReturnToResults && previous === 'running' && r.status !== 'running') {
    autoReturnToResults = false;
    tab('validation');
    toast(r.status === 'passed' ? 'Validation passed' : 'Validation found a defect', r.status === 'passed' ? 'success' : 'error');
  }
}

// ---------- server I/O ----------

async function getJson(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

async function event(name, value) {
  try {
    renderState(await getJson('/api/events', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({event:name,value})}));
  } catch (error) { toast(error.message, 'error'); }
}

function setOnline(isOnline) {
  if (isOnline === online) return;
  online = isOnline;
  document.body.classList.toggle('is-offline', !online);
  $('#lab-status-title').textContent = online ? 'SIMULATOR ONLINE' : 'SIMULATOR OFFLINE';
  $('#lab-status-detail').textContent = online ? 'Local environment · 127.0.0.1' : 'Run python3 server.py';
  toast(online ? 'Simulator reconnected' : 'Simulator unavailable. Run python3 server.py', online ? 'success' : 'error');
}

// ---------- wiring ----------

document.querySelectorAll('.nav-item[data-tab]').forEach((item) => item.addEventListener('click', () => tab(item.dataset.tab)));
document.querySelectorAll('[data-event]').forEach((item) => item.addEventListener('click', () => event(item.dataset.event)));
document.querySelectorAll('[data-gear]').forEach((item) => item.addEventListener('click', () => event('gear_set', item.dataset.gear)));
document.querySelectorAll('.scenario').forEach((item) => item.addEventListener('click', () => {
  document.querySelectorAll('.scenario').forEach((other) => other.classList.remove('selected'));
  item.classList.add('selected');
}));
let speedTimer;
$('#speed-slider').addEventListener('input', (e) => {
  $('#speed-slider-value').textContent = `${e.target.value} km/h`;
  setSliderFill(Number(e.target.value));
  clearTimeout(speedTimer);
  speedTimer = setTimeout(() => event('speed_set',Number(e.target.value)),180);
});
$('#speed-slider').addEventListener('change', (e) => e.target.blur());
$('#run-button').addEventListener('click', async () => {
  try {
    const scenario = document.querySelector('input[name="scenario"]:checked').value;
    const inject_fault = $('#inject-fault').checked;
    renderReport(await getJson('/api/scenarios',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scenario,inject_fault})}));
    autoReturnToResults = true;
    tab('cockpit');
    toast('Python validation running · watch the cockpit');
  } catch (error) { toast(error.message, 'error'); }
});
$('#android-mode').addEventListener('click', () => {
  if (!androidOnline) return;
  aaosActive = !aaosActive;
  $('.infotainment-panel').classList.toggle('aaos-active',aaosActive);
  $('#android-mode').classList.toggle('active',aaosActive);
  $('#android-mode').textContent = aaosActive ? 'AAOS LIVE · SWITCH TO DEMO' : 'AAOS READY · SHOW LIVE';
  if (aaosActive) $('#android-screen').src = `/api/android/screen?t=${Date.now()}`;
});
$('#android-screen').addEventListener('click', async (e) => {
  if (!aaosActive || !androidOnline) return;
  const image = e.currentTarget;
  const bounds = image.getBoundingClientRect();
  const imageRatio = androidSize.width / androidSize.height;
  const boxRatio = bounds.width / bounds.height;
  const contentWidth = boxRatio > imageRatio ? bounds.height * imageRatio : bounds.width;
  const contentHeight = boxRatio > imageRatio ? bounds.height : bounds.width / imageRatio;
  const left = bounds.left + (bounds.width-contentWidth)/2;
  const top = bounds.top + (bounds.height-contentHeight)/2;
  const x = Math.floor((e.clientX-left)/contentWidth*androidSize.width);
  const y = Math.floor((e.clientY-top)/contentHeight*androidSize.height);
  try { await getJson('/api/android/tap',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({x,y})}); }
  catch (error) { toast(error.message, 'error'); }
});
async function refreshAndroid() {
  try {
    const status = await getJson('/api/android/status');
    androidOnline = status.online;
    androidSize = {width:status.width||1024,height:status.height||768};
    $('#android-mode').disabled = !androidOnline;
    if (!androidOnline) {
      aaosActive = false;
      $('.infotainment-panel').classList.remove('aaos-active');
      $('#android-mode').textContent = 'AAOS OFFLINE';
    } else if (!aaosActive) $('#android-mode').textContent = 'AAOS READY · SHOW LIVE';
  } catch { androidOnline = false; }
}
function updateClock() {
  const now = new Date().toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit',hour12:false});
  $('#clock').textContent = now; $('#screen-clock').textContent = now;
}
async function refresh() {
  try {
    const [s,r] = await Promise.all([getJson('/api/state'),getJson('/api/report')]);
    setOnline(true);
    renderState(s); renderReport(r);
  } catch { setOnline(false); }
}
// ---------- climate (local UI only: the simulator has no HVAC signals) ----------

const climate = {driver:20, passenger:21, fan:3, auto:true, ac:true, sync:false};
function renderClimate() {
  $('#temp-driver').textContent = climate.driver.toFixed(1);
  $('#temp-passenger').textContent = climate.passenger.toFixed(1);
  document.querySelectorAll('#fan-bars i').forEach((bar, i) => bar.classList.toggle('on', i < climate.fan));
  for (const key of ['auto','ac','sync']) $(`#clim-${key}`).classList.toggle('on', climate[key]);
}
document.querySelectorAll('[data-climate]').forEach((button) => button.addEventListener('click', () => {
  const [key, step] = button.dataset.climate.split(':');
  if (step === undefined) climate[key] = !climate[key];
  else if (key === 'fan') { climate.fan = Math.max(1, Math.min(5, climate.fan + Number(step))); climate.auto = false; }
  else {
    climate[key] = Math.max(16, Math.min(28, climate[key] + Number(step) * 0.5));
    if (climate.sync) climate[key === 'driver' ? 'passenger' : 'driver'] = climate[key];
    replay($(`#temp-${key}`), 'pop');
  }
  if (key === 'sync' && climate.sync) climate.passenger = climate.driver;
  renderClimate();
}));
renderClimate();

// ---------- road in the windshield scrolls with the live speed ----------

let roadOffset = 0, roadLast = performance.now();
function roadFrame(now) {
  const dt = Math.min(0.1, (now - roadLast) / 1000);
  roadLast = now;
  roadOffset = (roadOffset + (state ? state.speed_kmh : 0) * dt * 1.6) % 4000;
  document.documentElement.style.setProperty('--road', `${roadOffset.toFixed(1)}px`);
  requestAnimationFrame(roadFrame);
}
if (!reducedMotion) requestAnimationFrame(roadFrame);

updateClock(); setInterval(updateClock,15000); refresh(); setInterval(refresh,450);
refreshAndroid(); setInterval(refreshAndroid,3000);
setInterval(() => { if (aaosActive && androidOnline) $('#android-screen').src = `/api/android/screen?t=${Date.now()}`; },1500);
