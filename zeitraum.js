// Zeitraum-Rechner im Browser. Rechnet GENAU wie saisonalitaet.zeitraum() in Python (ein Test vergleicht beide).
// tage: sortierte Tagesnummern (Tage seit 1970-01-01), preise: zugehörige Kurse.
const ZEITRAUM_ZINS = 1.6, ZEITRAUM_HANDELSTAGE = 252;

function ztag(jahr, monat, tag) {
  const dim = new Date(Date.UTC(jahr, monat, 0)).getUTCDate();
  return Date.UTC(jahr, monat - 1, Math.min(tag, dim)) / 864e5;
}
function zsuche(tage, wert, rechts) {            // wie numpy searchsorted: links = erster Index >= wert, rechts = erster Index > wert
  let lo = 0, hi = tage.length;
  while (lo < hi) { const m = (lo + hi) >> 1; if (rechts ? tage[m] <= wert : tage[m] < wert) lo = m + 1; else hi = m; }
  return lo;
}
function zmedian(a) { const s = [...a].sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; }
function zampel(winrate, sharpe) {
  if (winrate === null || sharpe === null) return "neutral";
  if (winrate >= 60 && sharpe >= 1) return "long";
  if (winrate <= 40 && sharpe <= -1) return "short";
  return "neutral";
}

function zeitraumRechnen(tage, preise, start, ende, n, bisJahr, zins = ZEITRAUM_ZINS) {
  const ueber = (ende[0] < start[0]) || (ende[0] === start[0] && ende[1] < start[1]);
  const fenster = [], tages = [], jahre = [];
  for (let y = bisJahr - n + 1; y <= bisJahr; y++) {
    const a = ztag(y, start[0], start[1]), b = ztag(y + (ueber ? 1 : 0), ende[0], ende[1]);
    if (a < tage[0] || b > tage[tage.length - 1]) continue;
    const i0 = zsuche(tage, a, false), i1 = zsuche(tage, b, true) - 1;
    if (i1 <= i0) continue;
    const r = preise[i1] / preise[i0] - 1;
    fenster.push(r * 100);
    for (let i = i0 + 1; i <= i1; i++) tages.push(preise[i] / preise[i - 1] - 1);
    jahre.push({jahr: y, rendite: r * 100});
  }
  const k = fenster.length;
  const kal = Math.round(ztag(2001 + (ueber ? 1 : 0), ende[0], ende[1]) - ztag(2001, start[0], start[1]));
  const leer = {n: k, jahre, kalendertage: kal, plus: null, minus: null, winrate: null, mean: null, median: null, std: null,
                jahresrendite: null, schwankung: null, sharpe: null, ampel: "neutral"};
  if (k < 5) return leer;
  const mw = fenster.reduce((x, y) => x + y, 0) / k;
  const sf = Math.sqrt(fenster.reduce((x, y) => x + (y - mw) ** 2, 0) / (k - 1));
  const mt = tages.reduce((x, y) => x + y, 0) / tages.length;
  const st = Math.sqrt(tages.reduce((x, y) => x + (y - mt) ** 2, 0) / (tages.length - 1));
  const jr = ((1 + mt) ** ZEITRAUM_HANDELSTAGE - 1) * 100, vol = st * Math.sqrt(ZEITRAUM_HANDELSTAGE) * 100;
  const sharpe = vol > 1e-6 ? (jr - zins) / vol : null;
  const plus = fenster.filter(x => x > 0).length, winrate = plus / k * 100;
  return {...leer, plus, minus: k - plus, winrate, mean: mw, median: zmedian(fenster), std: sf, jahresrendite: jr, schwankung: vol,
          sharpe, ampel: zampel(winrate, sharpe)};
}
if (typeof module !== "undefined") module.exports = {zeitraumRechnen, ztag};
