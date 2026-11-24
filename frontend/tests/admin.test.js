import assert from 'node:assert/strict';
import test from 'node:test';
import { createSSRApp } from 'vue';
import { renderToString } from '@vue/server-renderer';
import { createServer } from 'vite';

test('administration controls require the administrative route and a verified session', async () => {
  const vite = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom' });
  try {
    const { default: Home } = await vite.ssrLoadModule('/src/components/Home.vue');
    const state = { ...Home.data(), mode: 'grail', grailHasSearched: true, grailComplete: true, grailTab: 'best', grailWords: [{ name: 'кот', score: 300, path: [0, 1, 2] }], expandedBestWord: 0 };
    const render = (path, authorized) => renderToString(createSSRApp({ ...Home, data: () => ({ ...state, adminAuthorized: authorized }), computed: { ...Home.computed, adminMode: () => path === '/admin/solver' } }));
    assert.doesNotMatch(await render('/', true), /Не принято игрой|Пароль/);
    assert.doesNotMatch(await render('/admin/solver', false), /Не принято игрой/);
    assert.match(await render('/admin/solver', true), /Не принято игрой/);
  } finally { await vite.close(); }
});

test('reject waits for the server and prevents duplicate requests', async () => {
  const vite = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom' });
  const oldFetch = globalThis.fetch;
  try {
    const api = await vite.ssrLoadModule('/src/adminApi.js');
    const { default: RejectWord } = await vite.ssrLoadModule('/src/components/RejectWord.vue');
    let calls = 0;
    let finish;
    globalThis.fetch = async (url) => {
      if (url.endsWith('/session')) return { ok: true, json: async () => ({ authenticated: true, csrf_token: 'token' }) };
      calls += 1;
      return new Promise((resolve) => { finish = resolve; });
    };
    await api.session();
    const emitted = [];
    const state = { ...RejectWord.data(), word: 'кот', $emit: (...args) => emitted.push(args) };
    assert.equal(calls, 0);
    const pending = RejectWord.methods.reject.call(state);
    await RejectWord.methods.reject.call(state);
    assert.equal(calls, 1);
    assert.deepEqual(emitted, []);
    finish({ ok: true, json: async () => ({ word: 'кот', created: true }) });
    await pending;
    assert.deepEqual(emitted, [['rejected', 'кот', true]]);
  } finally { globalThis.fetch = oldFetch; await vite.close(); }
});

test('undo restores on the server before returning a word to results', async () => {
  const vite = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom' });
  const oldFetch = globalThis.fetch;
  try {
    const api = await vite.ssrLoadModule('/src/adminApi.js');
    const { default: Home } = await vite.ssrLoadModule('/src/components/Home.vue');
    let finish;
    let requests = 0;
    globalThis.fetch = async (url) => {
      if (url.endsWith('/session')) return { ok: true, json: async () => ({ authenticated: true, csrf_token: 'token' }) };
      assert.ok(url.endsWith('/rejected/restore'));
      requests += 1;
      return new Promise((resolve) => { finish = resolve; });
    };
    await api.session();
    const state = { ...Home.data(), hiddenWords: ['кот'], undoWord: 'кот' };
    const pending = Home.methods.undoReject.call(state);
    await Home.methods.undoReject.call(state);
    assert.equal(requests, 1);
    assert.deepEqual(state.hiddenWords, ['кот']);
    finish({ ok: true, json: async () => ({ word: 'кот' }) });
    await pending;
    assert.deepEqual(state.hiddenWords, []);
    assert.equal(state.undoWord, '');
  } finally { globalThis.fetch = oldFetch; await vite.close(); }
});

test('empty routes and cards disappear and return after undo without changing saved state', async () => {
  const vite = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom' });
  try {
    const { default: Home } = await vite.ssrLoadModule('/src/components/Home.vue');
    const word = (name, score) => ({ name, score, path: [0, 1, 2] });
    const first = { suffix_path: [1], words: [word('кот', 300)] };
    const second = { suffix_path: [2], words: [word('дом', 400)] };
    const other = { suffix_path: [3], words: [word('лес', 500)] };
    const state = { ...Home.data(), grailSeries: [{ suffix: 'first', routes: [first, second] }, { suffix: 'other', routes: [other] }], hiddenWords: ['кот'], expandedSeries: 'other', expandedSeriesWord: 'other|3-лес', viewedWordKeys: { viewed: true }, showAllSeriesWords: { 'other|3': true } };
    const original = JSON.stringify(state.grailSeries);
    let visible = Home.computed.visibleGrailSeries.call(state);
    assert.equal(visible[0].routes.length, 1);
    assert.equal(visible[0].routes[0].originalRouteIndex, 1);
    assert.equal(visible[0].good_count, 1);
    state.hiddenWords.push('дом');
    visible = Home.computed.visibleGrailSeries.call(state);
    assert.deepEqual(visible.map((item) => item.suffix), ['other']);
    assert.equal(state.expandedSeries, 'other');
    assert.equal(state.expandedSeriesWord, 'other|3-лес');
    assert.deepEqual(state.viewedWordKeys, { viewed: true });
    assert.deepEqual(state.showAllSeriesWords, { 'other|3': true });
    state.hiddenWords = ['кот'];
    visible = Home.computed.visibleGrailSeries.call(state);
    assert.deepEqual(visible.map((item) => item.suffix), ['first', 'other']);
    assert.equal(visible[0].routes[0].words[0].name, 'дом');
    state.hiddenWords = [];
    visible = Home.computed.visibleGrailSeries.call(state);
    assert.equal(visible[0].routes.length, 2);
    assert.equal(visible[0].routes[0].words[0].name, 'кот');
    assert.equal(JSON.stringify(state.grailSeries), original);
  } finally { await vite.close(); }
});

test('login and logout rotate CSRF headers for subsequent protected requests', async () => {
  const vite = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom' });
  const oldFetch = globalThis.fetch;
  try {
    const api = await vite.ssrLoadModule('/src/adminApi.js');
    const requests = [];
    const responses = [
      { authenticated: false, csrf_token: 'anonymous-a' },
      { authenticated: true, csrf_token: 'authenticated-b' },
      { word: 'кот', created: true },
      { word: 'кот' },
      { authenticated: false, csrf_token: 'anonymous-c' },
      { authenticated: true, csrf_token: 'authenticated-d' },
    ];
    globalThis.fetch = async (url, options) => {
      requests.push({ url, method: options.method || 'GET', csrf: options.headers?.['X-CSRF-Token'] });
      const body = responses.shift();
      assert.ok(body, 'unexpected request');
      return { ok: true, json: async () => body };
    };
    assert.equal(await api.session(), false);
    await api.adminRequest('login', { password: 'test' });
    await api.adminRequest('rejected', { word: 'кот' });
    await api.adminRequest('rejected/restore', { word: 'кот' });
    await api.adminRequest('logout', {});
    await api.adminRequest('login', { password: 'test' });
    assert.deepEqual(requests, [
      { url: '/api/admin/session', method: 'GET', csrf: undefined },
      { url: '/api/admin/login', method: 'POST', csrf: 'anonymous-a' },
      { url: '/api/admin/rejected', method: 'POST', csrf: 'authenticated-b' },
      { url: '/api/admin/rejected/restore', method: 'POST', csrf: 'authenticated-b' },
      { url: '/api/admin/logout', method: 'POST', csrf: 'authenticated-b' },
      { url: '/api/admin/login', method: 'POST', csrf: 'anonymous-c' },
    ]);
    assert.equal(responses.length, 0);
  } finally { globalThis.fetch = oldFetch; await vite.close(); }
});

test('editing controls and fixed undo notification appear only in the admin solver', async () => {
  const { readFile } = await import('node:fs/promises');
  const source = await readFile(new URL('../src/components/Home.vue', import.meta.url), 'utf8');
  assert.match(source, /\.admin-toast\s*\{[^}]*position:\s*fixed;[^}]*z-index:\s*1000;[^}]*safe-area-inset-bottom/s);
  assert.match(source, /v-if="adminMode && \(undoWord \|\| adminError\)"/);
  const vite = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom' });
  try {
    const { default: Home } = await vite.ssrLoadModule('/src/components/Home.vue');
    const state = { ...Home.data(), mode: 'grail', grailHasSearched: true, grailComplete: true, grailTab: 'best', grailWords: [{ name: 'кот', score: 300, path: [0, 1, 2] }], expandedBestWord: 0, undoWord: 'слово' };
    const render = (adminMode) => renderToString(createSSRApp({ ...Home, data: () => ({ ...state, adminAuthorized: true }), computed: { ...Home.computed, adminMode: () => adminMode } }));
    const normal = await render(false);
    assert.doesNotMatch(normal, /Режим редактирования|Не принято игрой|Слово исключено/);
    const admin = await render(true);
    assert.match(admin, /Режим редактирования/);
    assert.match(admin, /Слово исключено/);
    assert.match(admin, /Отменить/);
    assert.ok(admin.indexOf('Путь слова на поле') < admin.indexOf('Не принято игрой'));
  } finally { await vite.close(); }
});

test('undo timers last 3000ms, replace older timers and are cleared on unmount', async () => {
  const vite = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom' });
  const originalSet = globalThis.setTimeout;
  const originalClear = globalThis.clearTimeout;
  const oldWindow = globalThis.window;
  try {
    const { default: Home } = await vite.ssrLoadModule('/src/components/Home.vue');
    const timers = [];
    const cleared = [];
    globalThis.setTimeout = (callback, delay) => { const timer = { callback, delay }; timers.push(timer); return timer; };
    globalThis.clearTimeout = (timer) => cleared.push(timer);
    const state = { ...Home.data(), saveSnapshot() {}, abortGrailStream() {}, clearGrailPreviews() {} };
    Home.methods.onRejected.call(state, 'кот', true);
    assert.equal(state.undoWord, 'кот');
    assert.equal(timers[0].delay, 3000);
    Home.methods.onRejected.call(state, 'дом', true);
    assert.ok(cleared.includes(timers[0]));
    timers[0].callback();
    assert.equal(state.undoWord, 'дом');
    timers[1].callback();
    assert.equal(state.undoWord, '');
    Home.methods.onRejected.call(state, 'лес', true);
    globalThis.window = { removeEventListener() {} };
    Home.beforeUnmount.call(state);
    assert.ok(cleared.includes(timers[2]));
  } finally {
    globalThis.setTimeout = originalSet;
    globalThis.clearTimeout = originalClear;
    if (oldWindow === undefined) delete globalThis.window; else globalThis.window = oldWindow;
    await vite.close();
  }
});

test('undo failure keeps the word hidden and reports the server error', async () => {
  const vite = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom' });
  const oldFetch = globalThis.fetch;
  try {
    const { default: Home } = await vite.ssrLoadModule('/src/components/Home.vue');
    globalThis.fetch = async () => ({ ok: false, json: async () => ({ error: 'Не удалось вернуть слово' }) });
    const state = { ...Home.data(), hiddenWords: ['кот'], undoWord: 'кот' };
    await Home.methods.undoReject.call(state);
    assert.deepEqual(state.hiddenWords, ['кот']);
    assert.equal(state.adminError, 'Не удалось вернуть слово');
  } finally { globalThis.fetch = oldFetch; await vite.close(); }
});

test('snapshot indicator is set only for restored results and cleared on new images', async () => {
  const vite = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom' });
  const oldStorage = globalThis.sessionStorage;
  try {
    const { default: Home } = await vite.ssrLoadModule('/src/components/Home.vue');
    let snapshot = { version: 1, time: Date.now(), state: { grailHasSearched: true, grailWords: [{ name: 'кот' }], grailSeries: [] } };
    globalThis.sessionStorage = { getItem: () => JSON.stringify(snapshot) };
    const state = { ...Home.data(), ...Home.methods };
    state.restoreSnapshot();
    assert.equal(state.restoredGrailResults, true);
    state.handleGrailFilesChange({ target: { files: [], value: '' } });
    assert.equal(state.restoredGrailResults, false);
    snapshot = { version: 1, time: Date.now(), state: { grailHasSearched: true, grailWords: [], grailSeries: [] } };
    state.restoreSnapshot();
    assert.equal(state.restoredGrailResults, false);
  } finally {
    if (oldStorage === undefined) delete globalThis.sessionStorage; else globalThis.sessionStorage = oldStorage;
    await vite.close();
  }
});

test('rejected page distinguishes empty database and search and keeps export protected by the session view', async () => {
  const vite = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom' });
  try {
    const { default: Admin } = await vite.ssrLoadModule('/src/components/Admin.vue');
    const render = (state) => renderToString(createSSRApp({ ...Admin, data: () => ({ ...Admin.data(), loading: false, ...state }), computed: { rejectedPage: () => true } }));
    const empty = await render({ authenticated: true });
    assert.match(empty, /Исключённых слов пока нет/);
    assert.match(empty, /Экспорт TXT/);
    const noMatch = await render({ authenticated: true, search: 'несуществующее' });
    assert.match(noMatch, /По вашему запросу ничего не найдено/);
    assert.doesNotMatch(noMatch, /Исключённых слов пока нет/);
    assert.doesNotMatch(await render({ authenticated: false }), /Экспорт TXT/);
  } finally { await vite.close(); }
});

test('rejected page restores through the API and refreshes its list', async () => {
  const vite = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom' });
  const oldFetch = globalThis.fetch;
  try {
    const { default: Admin } = await vite.ssrLoadModule('/src/components/Admin.vue');
    const calls = [];
    globalThis.fetch = async (url, options) => {
      calls.push({ url, method: options.method || 'GET' });
      const result = options.method === 'POST' ? { word: 'кот' } : { total: 0, matched: 0, words: [] };
      return { ok: true, json: async () => result };
    };
    const state = { ...Admin.data(), ...Admin.methods, words: [{ word: 'кот' }], total: 1 };
    await state.restore('кот');
    assert.deepEqual(calls.map((call) => call.method), ['POST', 'GET']);
    assert.match(calls[0].url, /rejected\/restore$/);
    assert.deepEqual(state.words, []);
    assert.equal(state.total, 0);
  } finally { globalThis.fetch = oldFetch; await vite.close(); }
});

test('confirmation is shown before the reject action is available', async () => {
  const vite = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom' });
  try {
    const { default: RejectWord } = await vite.ssrLoadModule('/src/components/RejectWord.vue');
    const render = (confirming) => renderToString(createSSRApp({ ...RejectWord, data: () => ({ ...RejectWord.data(), confirming }) }, { word: 'кот' }));
    const closed = await render(false);
    assert.match(closed, /Не принято игрой/);
    assert.doesNotMatch(closed, /Исключить слово/);
    const open = await render(true);
    assert.match(open, /Исключить слово «кот»/);
    assert.match(open, /Отмена/);
    assert.match(open, /Исключить/);
  } finally { await vite.close(); }
});

test('saved-result explanation is limited to restored admin results', async () => {
  const vite = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom' });
  try {
    const { default: Home } = await vite.ssrLoadModule('/src/components/Home.vue');
    const render = (restored, adminMode) => renderToString(createSSRApp({
      ...Home,
      data: () => ({ ...Home.data(), mode: 'grail', adminAuthorized: true, restoredGrailResults: restored }),
      computed: { ...Home.computed, adminMode: () => adminMode },
    }));
    assert.match(await render(true, true), /Показаны сохранённые результаты/);
    assert.doesNotMatch(await render(false, true), /Показаны сохранённые результаты/);
    assert.doesNotMatch(await render(true, false), /Показаны сохранённые результаты/);
  } finally { await vite.close(); }
});
