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
