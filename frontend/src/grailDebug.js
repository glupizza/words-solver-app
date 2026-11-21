// Optional local diagnostics. Nothing is installed unless explicitly enabled in the URL.
let active = null;

function shortError(error) {
  const message = error && error.message ? error.message : String(error || 'Неизвестная ошибка');
  return String(message).replace(/https?:\/\/[^\s)]+/g, '[URL]').slice(0, 240);
}

function locationFromStack(stack) {
  const match = String(stack || '').match(/([^/\s():]+\.(?:js|vue)):(\d+):(\d+)/);
  return match ? `${match[1]}:${match[2]}:${match[3]}` : 'место неизвестно';
}

export function installGrailDebug(app, win, doc) {
  if (new URLSearchParams(win.location.search).get('grail_debug') !== '1') return;

  const panel = doc.createElement('details');
  panel.id = 'grail-debug-panel';
  panel.open = true;
  panel.style.cssText = 'position:relative;width:100%;background:#fff;color:#111;border:2px solid #43596d;padding:6px;font:13px/1.3 sans-serif';
  const title = doc.createElement('summary');
  title.textContent = 'Диагностика Грааля · нажмите, чтобы свернуть';
  const log = doc.createElement('textarea');
  log.readOnly = true;
  log.setAttribute('aria-label', 'Диагностика Грааля: текст можно выделить и скопировать');
  log.style.cssText = 'display:block;width:100%;height:105px;font:12px/1.3 monospace;color:#111;background:#fff;resize:vertical';
  const select = doc.createElement('button');
  select.type = 'button';
  select.textContent = 'Выделить текст для копирования';
  select.addEventListener('click', () => { log.focus(); log.select(); });
  panel.appendChild(title);
  panel.appendChild(log);
  panel.appendChild(select);
  doc.body.insertBefore(panel, doc.body.firstChild);

  const lines = [];
  active = {
    win,
    pending: null,
    write(message) {
      lines.push(`${new Date().toISOString().slice(11, 23)} ${message}`);
      if (lines.length > 60) lines.shift();
      log.value = lines.join('\n');
      log.scrollTop = log.scrollHeight;
    },
  };
  active.write('Диагностика включена. Фотографии и слова не записываются.');
  const previous = app.config.errorHandler;
  app.config.errorHandler = (error, instance, info) => {
    active.write(`Ошибка Vue (${info}): ${shortError(error)} · ${locationFromStack(error && error.stack)}`);
    if (previous) previous(error, instance, info);
    else console.error(error);
  };
  win.addEventListener('error', (event) => {
    const file = String(event.filename || '').split('/').pop().split('?')[0];
    active.write(`Ошибка window: ${shortError(event.error || event.message)} · ${file || 'место неизвестно'}:${event.lineno || 0}:${event.colno || 0}`);
  });
  win.addEventListener('unhandledrejection', (event) => {
    active.write(`Отклонён Promise: ${shortError(event.reason)} · ${locationFromStack(event.reason && event.reason.stack)}`);
  });
}

export function debugSeriesClick(vm, suffix, header) {
  if (!active) return;
  const card = header.closest('.series-card');
  const series = vm.grailSeries.find((item) => item.suffix === suffix);
  active.pending = suffix;
  active.write(`Нажатие: ${suffix}; маршрутов: ${series && Array.isArray(series.routes) ? series.routes.length : 'нет данных'}; было: ${vm.expandedSeries || 'закрыто'}; высота карточки: ${card ? Math.round(card.getBoundingClientRect().height) : 'нет'}`);
}

export function debugSeriesState(vm) {
  if (active) active.write(`Состояние expandedSeries: ${vm.expandedSeries || 'закрыто'}`);
}

export function debugSeriesUpdate(phase) {
  if (active && active.pending) active.write(`Vue ${phase}: ${active.pending}`);
}

export function debugSeriesTick(vm, suffix, header) {
  if (!active) return;
  const card = header.closest('.series-card');
  const routes = card ? card.querySelectorAll('.series-route') : [];
  const route = routes[0];
  const rect = route ? route.getBoundingClientRect() : null;
  const style = route ? active.win.getComputedStyle(route) : null;
  active.write(`nextTick: ${suffix}; состояние: ${vm.expandedSeries || 'закрыто'}; DOM маршрутов: ${routes.length}; высота карточки: ${card ? Math.round(card.getBoundingClientRect().height) : 'нет'}; маршрут: ${rect ? `top=${Math.round(rect.top)} height=${Math.round(rect.height)} display=${style.display} visibility=${style.visibility} opacity=${style.opacity}` : 'нет'}; scrollY=${Math.round(active.win.scrollY)}`);
}

export function debugSeriesScroll(header) {
  if (!active) return;
  active.write(`Коррекция прокрутки выполнена: scrollY=${Math.round(active.win.scrollY)}; заголовок top=${Math.round(header.getBoundingClientRect().top)}; высота экрана=${active.win.innerHeight}`);
  active.pending = null;
}
