// Hilfsskript für tests/test_zeitraum_js.py: liest JSON von stdin, rechnet mit zeitraum.js, schreibt JSON nach stdout.
const {zeitraumRechnen} = require("../zeitraum.js");
let eingabe = "";
process.stdin.on("data", c => eingabe += c);
process.stdin.on("end", () => {
  const {tage, preise, faelle} = JSON.parse(eingabe);
  const ausgabe = faelle.map(f => {
    const r = zeitraumRechnen(tage, preise, f.start, f.ende, f.n, f.bis);
    return {n: r.n, plus: r.plus, winrate: r.winrate, mean: r.mean, median: r.median, std: r.std,
            jahresrendite: r.jahresrendite, schwankung: r.schwankung, sharpe: r.sharpe, ampel: r.ampel, kalendertage: r.kalendertage};
  });
  process.stdout.write(JSON.stringify(ausgabe));
});
