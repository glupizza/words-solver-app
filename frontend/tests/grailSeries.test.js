import assert from 'node:assert/strict';
import test from 'node:test';
import { createSSRApp } from 'vue';
import { renderToString } from '@vue/server-renderer';
import { createServer } from 'vite';
import { seriesBundles, visibleSeriesWords } from '../src/grailSeries.js';

test('multi-letter links are unique and shorter fallback groups remain', () => {
  const suffix = 'ирование';
  const names = ['минирование', 'аминирование', 'ламинирование', 'номинирование', 'доминирование', 'тестирование', 'мастирование', 'зонирование'];
  const words = names.map((name) => {
    const prefix = name.slice(0, -suffix.length);
    const link = prefix.endsWith('мин') ? [4, 5, 6] : prefix.endsWith('ст') ? [7, 8] : [9];
    return { name, score: 500, path: [...Array(prefix.length - link.length).fill(0), ...link, ...Array(suffix.length).fill(10)] };
  });
  const bundles = seriesBundles(suffix, { words }, true);
  assert.deepEqual(bundles.find((bundle) => bundle.label === 'мин + ирование').words.map((word) => word.name), names.slice(0, 5));
  assert.equal(bundles.find((bundle) => bundle.label === 'ст + ирование').words.length, 2);
  assert.equal(bundles.find((bundle) => bundle.label === 'н + ирование').words.length, 1);
  assert.equal(new Set(bundles.flatMap((bundle) => bundle.words)).size, words.length);
});

test('long useful links win over larger short links and require matching cells', () => {
  const suffix = 'ирование';
  const prefixes = ['мин', 'амин', 'ламин', 'номин', 'домин', 'бин', 'вин', 'гин', 'дин'];
  const words = prefixes.map((prefix) => ({ name: prefix + suffix, score: 500,
    path: [...Array(prefix.length - 2).fill(4), 5, 6, ...Array(suffix.length).fill(10)] }));
  const bundles = seriesBundles(suffix, { words }, true);
  assert.equal(bundles.find((bundle) => bundle.label === 'мин + ирование').words.length, 5);
  assert.equal(bundles.flatMap((bundle) => bundle.words).length, 9);
  const pair = [
    { name: 'амин' + suffix, path: [0, 1, 2, 3, ...Array(suffix.length).fill(10)] },
    { name: 'бмин' + suffix, path: [0, 4, 5, 6, ...Array(suffix.length).fill(10)] },
  ];
  assert.ok(!seriesBundles(suffix, { words: pair }, true).some((bundle) => bundle.label === 'мин + ирование'));
  pair[1].path = [9, 1, 2, 3, ...Array(suffix.length).fill(10)];
  assert.equal(seriesBundles(suffix, { words: pair }, true).find((bundle) => bundle.label === 'мин + ирование').words.length, 2);
});

test('two routes reveal independently and retain their full metadata', async () => {
  const vite = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom' });
  try {
    const { default: Home } = await vite.ssrLoadModule('/src/components/Home.vue');
    const makeRoute = (prefix, count) => ({
      suffix_path: [prefix === 'first' ? 1 : 2],
      good_count: count, average_score: 500,
      words: Array.from({ length: count }, (_, index) => ({ name: `${prefix}${index}suffix`, score: 500, path: Array(15).fill(0) })),
    });
    const routes = [makeRoute('first', 25), makeRoute('second', 23)];
    assert.equal(visibleSeriesWords(routes[0], false).length, 20);
    const Component = {
      ...Home,
      data() {
        return { ...Home.data(), mode: 'grail', grailHasSearched: true, expandedSeries: 'suffix',
          showAllSeriesWords: { 'suffix|1': true },
          grailSeries: [{ suffix: 'suffix', good_count: 48, average_score: 500, routes }] };
      },
    };
    const html = await renderToString(createSSRApp(Component));
    assert.match(html, /first24suffix/);
    assert.doesNotMatch(html, /second20suffix/);
    assert.match(html, /Показать ещё \(3\)/);
    assert.match(html, /Свернуть/);
    assert.match(html, /Маршрут 1/);
    assert.match(html, /Маршрут 2/);
    const state = { showAllSeriesWords: {}, expandedSeriesWord: null };
    Home.methods.toggleRouteWords.call(state, 0);
    assert.deepEqual(state.showAllSeriesWords, { 0: true });
    Home.methods.toggleRouteWords.call(state, 1);
    assert.deepEqual(state.showAllSeriesWords, { 0: true, 1: true });
    Home.methods.toggleRouteWords.call(state, 0);
    assert.deepEqual(state.showAllSeriesWords, { 0: false, 1: true });
    const state2 = { ...Home.data(), grailRequestToken: 7, viewedWordKeys: { viewed: true } };
    const apply = (event) => Home.methods.applyGrailStreamEvent.call(state2, event, 7);
    const card = (suffix) => ({ suffix, routes: [] });
    apply({ type: 'priority', series: [card('ирование')] });
    state2.expandedSeries = 'ирование';
    state2.showAllSeriesWords = { 'ирование|1': true };
    apply({ type: 'series_batch', series: [card('строение'), card('ировать')] });
    apply({ type: 'series_batch', series: [] });
    apply({ type: 'series_batch', series: [card('ирование'), card('ировка')] });
    assert.equal(state2.grailSeries.filter((item) => item.suffix === 'ирование').length, 1);
    assert.equal(state2.expandedSeries, 'ирование');
    assert.equal(state2.showAllSeriesWords['ирование|1'], true);
    assert.equal(state2.viewedWordKeys.viewed, true);
    apply({ type: 'error' });
    assert.ok(state2.grailErrorMessage);
    assert.equal(state2.grailSeries.length, 4);
    apply({ type: 'complete', series: [card('ировка'), card('ирование'), card('строение')], words: [] });
    assert.deepEqual(state2.grailSeries.map((item) => item.suffix), ['ирование', 'ировка', 'строение']);
    assert.equal(state2.expandedSeries, 'ирование');
    assert.equal(state2.grailSearchingRemaining, false);
  } finally {
    await vite.close();
  }
});
