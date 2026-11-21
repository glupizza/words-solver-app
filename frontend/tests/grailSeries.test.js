import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { createSSRApp } from 'vue';
import { renderToString } from '@vue/server-renderer';
import { createServer } from 'vite';
import { mergeSeries, seriesBundles, visibleSeriesWords } from '../src/grailSeries.js';

test('all thirty endings stay in the agreed order without duplicate cards', () => {
  const suffixes = 'ирование ироваться ировать ированный ировка строение аскивание аскиваться аскивать аривание ариваться аривать таться тать енный тельный ческий нность ность ведение образование водство ывание ываться ывать ивание иваться ивать олотиться олотить'.split(' ');
  const cards = suffixes.map((suffix) => ({ suffix }));
  assert.deepEqual(mergeSeries(cards.slice().reverse(), [cards[0]]).map((card) => card.suffix), suffixes);
});

test('series grouping works without Array.prototype.at', () => {
  const descriptor = Object.getOwnPropertyDescriptor(Array.prototype, 'at');
  const suffix = 'ирование';
  const words = [
    { name: 'минирование', score: 500, path: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10] },
    { name: 'зонирование', score: 400, path: [11, 12, 13, 3, 4, 5, 6, 7, 8, 9, 10] },
  ];
  let bundles;
  try {
    Object.defineProperty(Array.prototype, 'at', { value: undefined, configurable: true });
    bundles = seriesBundles(suffix, { words }, true);
  } finally {
    if (descriptor) Object.defineProperty(Array.prototype, 'at', descriptor);
    else delete Array.prototype.at;
  }
  assert.deepEqual(bundles.flatMap((bundle) => bundle.words), words);
  assert.deepEqual(bundles.map((bundle) => bundle.label), ['н + ирование']);
});

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
      words: Array.from({ length: count }, (_, index) => ({
        name: `${prefix}${index}suffix`, score: 500,
        path: Array.from({ length: `${prefix}${index}suffix`.length }, (_cell, position) => position),
      })),
    });
    const routes = [makeRoute('first', 30), makeRoute('second', 23)];
    assert.equal(visibleSeriesWords(routes[0], false).length, 20);
    const Component = {
      ...Home,
      data() {
        return { ...Home.data(), mode: 'grail', grailHasSearched: true, expandedSeries: 'suffix',
          showAllSeriesWords: { 'suffix|1': true },
          grailSeries: [{ suffix: 'suffix', good_count: 53, average_score: 500, routes }] };
      },
    };
    const html = await renderToString(createSSRApp(Component));
    assert.match(html, /first24suffix/);
    assert.doesNotMatch(html, /second20suffix/);
    assert.match(html, /Показать ещё \(3\)/);
    assert.match(html, /Свернуть/);
    assert.match(html, /Маршрут 1/);
    assert.match(html, /Маршрут 2/);
    assert.doesNotMatch(html, /\+ suffix/);
    const collapsedRoute = await renderToString(createSSRApp({ ...Component, data() {
      return { ...Component.data(), showAllSeriesWords: {} };
    } }));
    assert.match(collapsedRoute, /Показать ещё \(10\)/);
    assert.doesNotMatch(collapsedRoute, /first20suffix/);
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

    const state3 = { ...Home.data(), ...Home.methods, grailRequestToken: 1,
      mode: 'grail', grailHasSearched: true, grailSeries: [{ suffix: 'suffix', good_count: 53, average_score: 500, routes }] };
    let afterRender;
    state3.$nextTick = (callback) => { afterRender = callback; };
    let top = 100;
    state3.toggleSeries('suffix', { currentTarget: { getBoundingClientRect: () => ({ top }) } });
    assert.equal(state3.expandedSeries, 'suffix');
    const oldWindow = globalThis.window;
    const scrolls = [];
    try {
      globalThis.window = { scrollBy: (...args) => scrolls.push(args) };
      top = 120;
      afterRender();
    } finally {
      if (oldWindow === undefined) delete globalThis.window;
      else globalThis.window = oldWindow;
    }
    assert.deepEqual(scrolls, [[0, 20]]);
    const firstWord = routes[0].words[0];
    state3.toggleSeriesWord('suffix|1', firstWord);
    state3.toggleRouteWords('suffix|1');
    state3.applyGrailStreamEvent({ type: 'series_batch', series: [{ suffix: 'строение', routes: [] }] }, 1);
    assert.equal(state3.expandedSeries, 'suffix');
    assert.equal(state3.expandedSeriesWord, `suffix|1-${firstWord.name}`);
    assert.equal(state3.showAllSeriesWords['suffix|1'], true);
    assert.equal(state3.viewedWordKeys[state3.wordKey(firstWord)], true);
    const renderState = { ...state3 };
    Object.keys(Home.methods).forEach((name) => delete renderState[name]);
    delete renderState.$nextTick;
    const expanded = await renderToString(createSSRApp({ ...Home, data: () => renderState }));
    assert.match(expanded, /Маршрут 1/);
    assert.match(expanded, /Маршрут 2/);
    assert.match(expanded, /Путь слова на поле 5 на 5/);
    assert.match(expanded, /first24suffix/);
    let scrollOptions;
    state3.toggleSeries('suffix', { currentTarget: { getBoundingClientRect: () => ({ top: 5 }), scrollIntoView: (options) => { scrollOptions = options; } } });
    assert.equal(state3.expandedSeries, null);
    afterRender();
    assert.deepEqual(scrollOptions, { block: 'start', behavior: 'auto' });
  } finally {
    await vite.close();
  }
});

test('sticky header and grid geometry preserve cell centres for sparse paths', async () => {
  const homeSource = await readFile(new URL('../src/components/Home.vue', import.meta.url), 'utf8');
  const mapSource = await readFile(new URL('../src/components/GrailPathMap.vue', import.meta.url), 'utf8');
  assert.match(homeSource, /\.series-header-open\s*\{[^}]*position:\s*sticky;[^}]*top:\s*env\(safe-area-inset-top/s);
  assert.match(homeSource, /\.series-bundle \+ \.series-bundle\s*\{[^}]*border-top:/s);
  assert.match(mapSource, /grid-template-rows:\s*repeat\(5,\s*minmax\(0,\s*1fr\)\)/);
  assert.match(mapSource, /grid-template-columns:\s*repeat\(5,\s*minmax\(0,\s*1fr\)\)/);
  const vite = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom' });
  try {
    const { default: Map } = await vite.ssrLoadModule('/src/components/GrailPathMap.vue');
    for (const path of [[0, 6, 12, 18, 24], [5, 6, 7], [0, 1, 2], [10, 11, 12], [1, 6, 11, 16, 21]]) {
      const word = 'abcdefgh'.slice(0, path.length);
      const context = { word, path, suffix: '', wordCharacters: Array.from(word), suffixStartIndex: null };
      const usedCells = Map.computed.usedCells.call(context);
      const cells = Map.computed.cells.call({ usedCells });
      assert.equal(cells.length, 25);
      assert.deepEqual(cells.map((cell) => cell.position), Array.from({ length: 25 }, (_, index) => index));
      const points = Map.computed.points.call(context);
      assert.equal(points, path.map((position) => `${(position % 5) * 50 + 25},${Math.floor(position / 5) * 50 + 25}`).join(' '));
    }
  } finally {
    await vite.close();
  }
});
