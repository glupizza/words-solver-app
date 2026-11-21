export function visibleSeriesWords(route, showAll) {
  const words = Array.isArray(route.words) ? route.words : [];
  return showAll ? words : words.slice(0, 20);
}

export function seriesBundles(suffix, route, showAll) {
  const words = Array.isArray(route.words) ? route.words : [];
  const candidates = new Map();
  words.forEach((word) => {
    const prefix = Array.from(word.name).slice(0, -Array.from(suffix).length).join('');
    for (let length = 2; length <= Array.from(prefix).length; length += 1) {
      const link = Array.from(prefix).slice(-length).join('');
      const prefixLength = Array.from(prefix).length;
      const path = Array.isArray(word.path) ? word.path.slice(prefixLength - length, prefixLength) : [];
      if (path.length !== length || path.some((cell) => !Number.isInteger(cell) || cell < 0 || cell >= 25)) continue;
      const key = JSON.stringify([link, path]);
      if (!candidates.has(key)) candidates.set(key, { link, path, words: [] });
      candidates.get(key).words.push(word);
    }
  });
  const remaining = new Set(words);
  const bundles = [];
  const links = Array.from(candidates.values()).sort((a, b) => (
    Math.min(b.link.length, 4) * Math.sqrt(b.words.length)
      - Math.min(a.link.length, 4) * Math.sqrt(a.words.length)
    || b.words.length - a.words.length || b.link.length - a.link.length
    || a.link.localeCompare(b.link) || JSON.stringify(a.path).localeCompare(JSON.stringify(b.path))
  ));
  links.forEach(({ link, words: candidatesForLink }) => {
    const members = candidatesForLink.filter((word) => remaining.has(word));
    if (members.length < 2) return;
    members.forEach((word) => remaining.delete(word));
    bundles.push({ label: `${link} + ${suffix}`, words: members });
  });
  const fallback = new Map();
  words.filter((word) => remaining.has(word)).forEach((word) => {
    const prefix = Array.from(word.name).slice(0, -Array.from(suffix).length);
    const link = prefix[prefix.length - 1] || '';
    if (!fallback.has(link)) fallback.set(link, []);
    fallback.get(link).push(word);
  });
  fallback.forEach((members, link) => bundles.push({ label: link ? `${link} + ${suffix}` : suffix, words: members }));
  const visible = new Set(visibleSeriesWords(route, showAll));
  return bundles.flatMap((bundle) => {
    const selected = bundle.words.filter((word) => visible.has(word));
    return selected.length ? [{ ...bundle, words: selected }] : [];
  });
}

const suffixOrder = 'ирование ироваться ировать ированный ировка строение аскивание аскиваться аскивать аривание ариваться аривать таться тать енный тельный ческий нность ность ведение образование водство ывание ываться ывать ивание иваться ивать олотиться олотить'.split(' ');

export function mergeSeries(current, incoming) {
  const bySuffix = new Map(current.map((series) => [series.suffix, series]));
  incoming.forEach((series) => bySuffix.set(series.suffix, series));
  return Array.from(bySuffix.values()).sort((a, b) => suffixOrder.indexOf(a.suffix) - suffixOrder.indexOf(b.suffix));
}

export function routeKey(suffix, route) {
  return `${suffix}|${(route.suffix_path || []).join(',')}`;
}
