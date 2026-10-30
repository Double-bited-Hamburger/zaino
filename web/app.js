"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const GIORNI = ["domenica", "lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato"];
const MESI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"];
const MESI_LUNGHI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"];
const MINUTI_VALIDITA = 30; // oltre questa età i dati vengono riscaricati all'apertura
const SCHEDE = ["oggi", "agenda", "compiti", "orario", "voti", "carico", "assenze"];

let D = null; // dati elaborati dal server
let fatti = new Set(); // id dei compiti spuntati
let scheda = "oggi";
let ricerca = ""; // testo cercato nella scheda Compiti
let nascondiFatti = false;
let settimanaOrario = 0;
let oraOrario = null; // la casella scelta nella griglia dell'orario, «data|inizio» (null = l'ora in corso)
let editorOrario = null; // le righe dell'orario scritto a mano mentre lo modifichi; null = si vede la griglia
let materiaGrafico = "";
let simMateria = "";
let simulati = []; // voti ipotetici: {materia, voto}
let simVoto = null; // il voto che si sta provando nel simulatore, non ancora aggiunto
let sezioniAperte = new Set(); // sezioni a scomparsa aperte (Voti: grafici, tutti i voti, consigli; Agenda: gli elenchi completi)
let meseAgenda = 0; // il mese del calendario dell'Agenda, rispetto a quello di oggi
let giornoAgenda = null; // il giorno scelto sul calendario (null = oggi)
let settimanaCompitiScelta = 0; // la settimana dei Compiti, rispetto a quella di oggi
let giornoCompiti = null; // il giorno scelto nella settimana dei Compiti (sul telefono)
let giornoCarico = null; // il giorno scelto tra i prossimi 14 del Carico di lavoro (null = oggi)
let caricoPer = "materia"; // «Da dove arriva il lavoro»: per materia o per docente
let caricoTutte = false; // se mostrare tutte le righe o solo le prime 5

/* ---------- utilità ---------- */

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const giorno = (iso) => { const [y, m, d] = iso.slice(0, 10).split("-").map(Number); return new Date(y, m - 1, d); };
const giorniDa = (iso) => Math.round((giorno(iso) - giorno(D.oggi)) / 864e5);
const num = (v) => (v == null ? "–" : v.toLocaleString("it-IT", { maximumFractionDigits: 2 }));
const media = (v) => (v == null ? "–" : v.toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
const dataBreve = (iso) => { const d = giorno(iso); return `${d.getDate()} ${MESI[d.getMonth()]}`; };
const dataLunga = (iso) => { const d = giorno(iso); return `${GIORNI[d.getDay()]} ${d.getDate()} ${MESI[d.getMonth()]}`; };
const mese = (ym) => { const [y, m] = ym.split("-").map(Number); return `${MESI[m - 1]} ${y}`; };
const plurale = (n, uno, molti) => `${n} ${n === 1 ? uno : molti}`;
const tip = (html) => `data-tip="${esc(html)}"`;
const arrotondaSu = (v) => Math.ceil(v * 4 - 1e-9) / 4;
const isoDi = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const spostaGiorni = (iso, n) => { const d = giorno(iso); d.setDate(d.getDate() + n); return isoDi(d); };
const dataCompleta = (iso) => { const d = giorno(iso); return `${GIORNI[d.getDay()]} ${d.getDate()} ${MESI_LUNGHI[d.getMonth()]} ${d.getFullYear()}`; };
const oraDi = (d) => `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
const minuti = (hhmm) => { const [h, m] = hhmm.split(":").map(Number); return h * 60 + m; };
// Per cercare senza badare a maiuscole e accenti: «perché» si trova anche scrivendo «perche».
const piega = (s) => String(s ?? "").normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();

function quando(iso) {
  const n = giorniDa(iso);
  if (n === 0) return "oggi";
  if (n === 1) return "domani";
  if (n === -1) return "ieri";
  return n > 0 ? `tra ${n} giorni` : `${-n} giorni fa`;
}

async function api(percorso, corpo) {
  const opzioni = corpo === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Parser-Compiti": "1" },
    body: JSON.stringify(corpo),
  };
  const risposta = await fetch(percorso, opzioni);
  const json = await risposta.json();
  if (!risposta.ok) throw new Error(json.errore || "Errore imprevisto.");
  return json;
}

let titoloAttuale = ["Zaino", ""];
// Il titolo in alto: col tema «Nothing» la prima parte è a punti e il resto (il nome) va a capo in piccolo.
function impostaTitolo(testo, resto = "") {
  titoloAttuale = [testo, resto];
  const sotto = resto ? `<span class="titolo-resto">${esc(resto)}</span>` : "";
  if (temaNothing()) $("#titolo").innerHTML = aPunti(testo, 3.4) + sotto;
  // Col tema «Ultra» il titolo è composto come il fronte della lattina: riga in alto tra due trattini, nome grande e graffiato, parola azzurra spaziata, «Ultra».
  else if (temaUltra()) $("#titolo").innerHTML = `<span class="ultra-zero" id="ultra-zero">${esc(sloganUltra())}</span>
    <span class="wordmark">${esc(testo === "Zaino" ? "ZAINØ" : testo)}</span><span class="ultra-azzurro">Scuola</span><span class="ultra-nome">Ultra</span>${sotto}`;
  else $("#titolo").textContent = resto ? `${testo} ${resto}` : testo;
}

const temaUltra = () => document.documentElement.dataset.tema === "ultra";
// La riga in alto del tema «Ultra», al posto dello «zero zuccheri»: i compiti scaduti non spuntati.
function sloganUltra() {
  if (!D || D.vuoto) return "Zero stress";
  const n = D.compiti.filter((c) => giorniDa(c.consegna) < 0 && !fatti.has(c.id)).length;
  return n ? `${n} ${n === 1 ? "arretrato" : "arretrati"}` : "Zero arretrati";
}

function avviso(testo, errore = false) {
  const el = $("#avviso");
  el.hidden = !testo;
  el.textContent = testo || "";
  el.classList.toggle("errore", errore);
}

/* ---------- grafici ---------- */

// Grafico a colonne (anche impilate). cats: [{label, valori: [n…], tip}], serie: [colore CSS…]
function colonne(w, cats, serie, opt = {}) {
  const h = opt.h || 190, m = { t: 18, r: 8, b: 26, l: 26 };
  const totali = cats.map((c) => c.valori.reduce((a, b) => a + b, 0));
  const max = Math.max(1, ...totali);
  const passo = max <= 5 ? 1 : max <= 10 ? 2 : max <= 25 ? 5 : Math.ceil(max / 4 / 5) * 5;
  const cima = Math.ceil(max / passo) * passo;
  const pw = w - m.l - m.r, ph = h - m.t - m.b, banda = pw / cats.length;
  const lb = Math.min(24, Math.max(3, banda - 6));
  const y = (v) => m.t + ph - (v / cima) * ph;
  const ogni = Math.max(1, Math.ceil(cats.length / Math.max(1, Math.floor(pw / 48))));
  let s = "";
  for (let v = 0; v <= cima; v += passo) {
    s += `<line class="${v ? "grid" : "axis"}" x1="${m.l}" x2="${w - m.r}" y1="${y(v)}" y2="${y(v)}"/>`;
    s += `<text x="${m.l - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`;
  }
  cats.forEach((c, i) => {
    const x = m.l + banda * i + (banda - lb) / 2;
    const ultimo = c.valori.reduce((u, v, j) => (v > 0 ? j : u), -1);
    let base = 0;
    c.valori.forEach((v, j) => {
      if (v <= 0) return;
      const yb = y(base) - (base > 0 ? 2 : 0), yt = y(base + v), alt = Math.max(1, yb - yt);
      if (j === ultimo) {
        const r = Math.min(4, alt / 2, lb / 2);
        s += `<path fill="${serie[j]}" d="M${x},${yb}V${yt + r}Q${x},${yt} ${x + r},${yt}H${x + lb - r}Q${x + lb},${yt} ${x + lb},${yt + r}V${yb}Z"/>`;
      } else {
        s += `<rect fill="${serie[j]}" x="${x}" y="${yt}" width="${lb}" height="${alt}"/>`;
      }
      base += v;
    });
    if (totali[i] > 0 && cats.length <= 16) s += `<text class="val" x="${x + lb / 2}" y="${y(totali[i]) - 5}" text-anchor="middle">${totali[i]}</text>`;
    if (i % ogni === 0) s += `<text x="${m.l + banda * (i + 0.5)}" y="${h - 8}" text-anchor="middle"${c.evid ? ' class="val"' : ""}>${esc(c.label)}</text>`;
    s += `<rect class="hit" x="${m.l + banda * i}" y="${m.t}" width="${banda}" height="${ph}" ${tip(c.tip)}/>`;
  });
  return `<svg class="chart" viewBox="0 0 ${w} ${h}" height="${h}" role="img" aria-label="${esc(opt.titolo || "")}">${s}</svg>`;
}

// Voti nel tempo. punti: [{t: Date, y, tip}], linea: [{t, y}] (se assente unisce i punti)
function andamento(w, punti, linea) {
  const h = 220, m = { t: 12, r: 16, b: 26, l: 26 };
  const pw = w - m.l - m.r, ph = h - m.t - m.b;
  const tempi = punti.map((p) => +p.t), t0 = Math.min(...tempi), t1 = Math.max(...tempi);
  const x = (t) => (t1 === t0 ? m.l + pw / 2 : m.l + ((t - t0) / (t1 - t0)) * pw);
  const y = (v) => m.t + ph - ((v - 1) / 9) * ph; // scala dei voti: da 1 a 10
  let s = "";
  for (let v = 2; v <= 10; v += 2) {
    s += `<line class="grid" x1="${m.l}" x2="${w - m.r}" y1="${y(v)}" y2="${y(v)}"/><text x="${m.l - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`;
  }
  s += `<line class="ref" x1="${m.l}" x2="${w - m.r}" y1="${y(D.sufficienza)}" y2="${y(D.sufficienza)}"/>`;
  s += `<line class="axis" x1="${m.l}" x2="${w - m.r}" y1="${m.t + ph}" y2="${m.t + ph}"/>`;
  const tacche = t1 === t0 ? [t0] : (pw >= 360 ? [0, 0.25, 0.5, 0.75, 1] : [0, 0.5, 1]).map((f) => t0 + f * (t1 - t0));
  let precedente = "";
  tacche.forEach((t, i) => {
    const d = new Date(t), ancora = t1 === t0 ? "middle" : i === 0 ? "start" : i === tacche.length - 1 ? "end" : "middle";
    const testo = `${d.getDate()} ${MESI[d.getMonth()]}`;
    if (testo !== precedente) s += `<text x="${x(t)}" y="${h - 8}" text-anchor="${ancora}">${testo}</text>`;
    precedente = testo;
  });
  const tratto = linea || punti;
  if (tratto.length > 1) s += `<path fill="none" stroke="var(--series-1)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" d="${tratto.map((p, i) => `${i ? "L" : "M"}${x(+p.t)},${y(p.y)}`).join("")}"/>`;
  punti.forEach((p) => { s += `<circle class="pt" cx="${x(+p.t)}" cy="${y(p.y)}" r="5" fill="var(--series-1)"/>`; });
  punti.forEach((p) => { s += `<circle class="hit" cx="${x(+p.t)}" cy="${y(p.y)}" r="12" ${tip(p.tip)}/>`; });
  return `<svg class="chart" viewBox="0 0 ${w} ${h}" height="${h}" role="img" aria-label="Andamento dei voti nel tempo">${s}</svg>`;
}

// Barre orizzontali in HTML. righe: [{label, segmenti: [{v, colore}], val, tip}]
function barre(righe, max, rif) {
  if (!righe.length) return '<p class="muted">Ancora nessun dato.</p>';
  return `<div class="hbar">${righe.map((r) => `
    <div class="lab" title="${esc(r.label)}">${esc(r.label)}</div>
    <div class="trk" ${tip(r.tip)}>${r.segmenti.filter((g) => g.v > 0).map((g) => `<i style="width:${(g.v / max) * 100}%;background:${g.colore}"></i>`).join("")}${rif ? `<i class="rif" style="left:${(rif / max) * 100}%"></i>` : ""}</div>
    <div class="val">${r.val}</div>`).join("")}</div>`;
}

const legenda = (voci) => `<div class="legend">${voci.map(([nome, colore]) => `<span><i style="background:${colore}"></i>${nome}</span>`).join("")}</div>`;
const grafico = (titolo, sotto, corpo) => `<div class="box pad"><p class="chart-title">${titolo}</p><p class="chart-sub">${sotto}</p>${corpo}</div>`;

// I grafici SVG hanno bisogno della larghezza reale: vengono disegnati dopo aver inserito l'HTML.
let daDisegnare = [];
const segnaposto = (fn) => { daDisegnare.push(fn); return `<div data-svg="${daDisegnare.length - 1}"></div>`; };
function disegna(radice) {
  radice.querySelectorAll("[data-svg]").forEach((el) => { el.innerHTML = daDisegnare[+el.dataset.svg](Math.max(260, el.clientWidth)); });
}

/* ---------- pezzi condivisi ---------- */

const lezioniOrario = () => (D.orario ? D.orario.lezioni : []);

// Dettagli di una variazione d'orario: «al posto di …» e la nota di WebUntis.
function dettagliVariazione(l) {
  const previsto = [...l.docenti_previsti, ...l.aule_previste].join(", ");
  return [previsto ? `al posto di ${esc(previsto)}` : "", esc(l.nota)].filter(Boolean).join(" · ");
}

// L'aula in cui si svolge un promemoria, se a quell'ora c'è una lezione in orario.
function aulaPromemoria(p) {
  const inizio = (p.orario || "").slice(0, 5);
  const lezioni = lezioniOrario().filter((l) => l.data === p.data && l.inizio === inizio && l.stato !== "annullata");
  const aule = [...new Set(lezioni.flatMap((l) => l.aule))];
  return aule.length ? `Aula ${aule.join(", ")}` : ""; // testo semplice: chi lo mette in pagina lo passa da esc
}

function tabellaPromemoria(lista) {
  if (!lista.length) return '<div class="box"><div class="empty">Niente in programma.</div></div>';
  const righe = lista.map((p) => {
    const urgente = giorniDa(p.data) <= 2 ? ` <span class="tag">${quando(p.data)}</span>` : "";
    const aula = aulaPromemoria(p);
    return `<tr><td class="when">${dataLunga(p.data)}${urgente}<small>${esc(p.orario) || quando(p.data)}</small></td>
      <td>${puntoNuovo(p.verifica && nuovo("verifiche", chiaveVerifica(p)))}<strong>${esc(p.materia) || "—"}</strong><div class="muted">${esc(p.docente)}</div></td><td>${esc(p.testo)}${aula ? `<div class="muted">${esc(aula)}</div>` : ""}</td></tr>`;
  });
  return `<div class="box"><table><thead><tr><th>Quando</th><th>Materia</th><th>Dettagli</th></tr></thead><tbody>${righe.join("")}</tbody></table></div>`;
}

function listaCompiti(lista, vuoto, testa = "") {
  if (nascondiFatti) lista = lista.filter((c) => !fatti.has(c.id));
  if (!lista.length) return `<div class="box"><div class="empty">${vuoto}</div></div>`;
  const perGiorno = new Map();
  lista.forEach((c) => perGiorno.set(c.consegna, [...(perGiorno.get(c.consegna) || []), c]));
  let html = "";
  perGiorno.forEach((compiti, data) => {
    const scaduto = giorniDa(data) < 0 && compiti.some((c) => !fatti.has(c.id));
    html += `<div class="day${scaduto ? " scaduto" : ""}">Per ${dataLunga(data)} <span class="muted">· ${quando(data)}</span></div><ul class="todo">`;
    html += compiti.map((c) => `<li class="${fatti.has(c.id) ? "fatto" : ""}"><label>
      <input type="checkbox" data-id="${c.id}" ${fatti.has(c.id) ? "checked" : ""}>
      <span>${puntoNuovo(nuovo("compiti", c.id))}<strong>${esc(c.materia)}</strong> — ${esc(c.testo)}</span></label></li>`).join("");
    html += "</ul>";
  });
  return `<div class="box">${testa}${html}</div>`;
}

function listaConsigli(voci) {
  if (!voci.length) return '<div class="box"><div class="empty">Nessun punto critico al momento.</div></div>';
  const icona = { critico: "!", attenzione: "!", info: "i" };
  return `<div class="box"><ul class="consigli">${voci.map((v) => `<li class="${v.livello}"><span class="icona" aria-hidden="true">${icona[v.livello]}</span>
    <div><strong>${esc(v.titolo)}</strong><div class="muted">${esc(v.testo)}</div></div></li>`).join("")}</ul></div>`;
}

// Col tema «Nothing» numeri brevi e nomi in evidenza diventano scritte a punti; il testo vero resta per i lettori di schermo.
const temaNothing = () => document.documentElement.dataset.tema === "nothing";
const aPunti = (testo, passo) => `<span class="a-punti" role="img" aria-label="${esc(testo)}">${puntini(testo, passo)}</span>`;
const grande = (testo, passo = 3) => (temaNothing() ? aPunti(testo, passo) : esc(testo));

const tessera = (valore, etichetta, classe = "", sotto = "") => {
  const v = String(valore);
  return `<div class="card"><b class="${classe}">${temaNothing() && v.length <= 7 && !/[<&]/.test(v) ? aPunti(v, 4) : v}</b><span>${etichetta}</span>${sotto}</div>`;
};

// Barra di avanzamento sottile; «barraTacche» è divisa in pezzi [peso, "si" | "ora" | ""] (uno per passo, o per 5 minuti di lezione).
const barra = (quota, classe = "") => `<div class="progresso ${classe}"><i style="width:${Math.round(Math.min(1, Math.max(0, quota)) * 100)}%"></i></div>`;
const barraTacche = (pezzi, etichetta) => `<div class="tacche" role="img" aria-label="${esc(etichetta)}">${pezzi.map(([peso, classe]) =>
  `<i class="${classe}" style="flex-grow:${peso}"></i>`).join("")}</div>`;

/* ---------- novità ---------- */

// Voti, verifiche e compiti comparsi da quando li hai visti l'ultima volta (per profilo, su questo dispositivo):
// hanno un puntino rosso finché non esci dalla scheda che li mostra. Alla primissima apertura tutto conta come già visto.
const chiaveVoto = (v) => `${v.data}|${v.materia}|${v.codice}|${v.descrizione}`;
const chiaveVerifica = (p) => `${p.data}|${p.materia}|${p.testo}`;
const VISTE_DA = { agenda: ["verifiche", "compiti"], compiti: ["compiti"], voti: ["voti"] };
let visti = null; // {voti, verifiche, compiti}: Set di chiavi

const chiaviAttuali = () => ({ voti: D.voti.map(chiaveVoto), verifiche: verificheFuture().map(chiaveVerifica), compiti: D.compiti.map((c) => c.id) });
const chiaveVisti = () => `visti-${(P && P.attivo) || ""}`;

function caricaVisti() {
  const attuali = chiaviAttuali();
  let salvati = null;
  try { salvati = JSON.parse(localStorage.getItem(chiaveVisti())); } catch {}
  if (!salvati || typeof salvati !== "object") {
    salvati = attuali;
    try { localStorage.setItem(chiaveVisti(), JSON.stringify(attuali)); } catch {}
  }
  visti = Object.fromEntries(Object.keys(attuali).map((c) => [c, new Set(Array.isArray(salvati[c]) ? salvati[c] : [])]));
}

const nuovo = (categoria, chiave) => Boolean(visti && !visti[categoria].has(chiave));
const contaNuovi = (categoria) => (visti && D && !D.vuoto ? chiaviAttuali()[categoria].filter((k) => !visti[categoria].has(k)).length : 0);
const puntoNuovo = (si) => (si ? '<span class="punto-nuovo" role="img" aria-label="Nuovo" title="Nuovo"></span>' : "");

function segnaVisti(schedaVista) {
  const categorie = VISTE_DA[schedaVista];
  if (!categorie || !visti || !D || D.vuoto) return;
  const attuali = chiaviAttuali();
  let cambiato = false;
  categorie.forEach((c) => attuali[c].forEach((k) => { if (!visti[c].has(k)) { visti[c].add(k); cambiato = true; } }));
  if (!cambiato) return;
  try { localStorage.setItem(chiaveVisti(), JSON.stringify(Object.fromEntries(Object.entries(visti).map(([c, s]) => [c, [...s].slice(-1500)])))); } catch {}
}

// Il numero di novità accanto al nome delle schede.
function contatoriSchede() {
  document.querySelectorAll(".tabs button").forEach((b) => {
    const n = (VISTE_DA[b.dataset.tab] || []).reduce((t, c) => t + contaNuovi(c), 0);
    b.querySelector(".conta-nuovi")?.remove();
    if (n) b.insertAdjacentHTML("beforeend", `<span class="conta-nuovi" aria-label="${n} novità">${n}</span>`);
  });
}

/* ---------- schede ---------- */

function listaVariazioni(lista) {
  return `<div class="box"><table><thead><tr><th>Quando</th><th>Lezione</th><th>Variazione</th></tr></thead><tbody>${lista.map((l) => `
    <tr><td class="when">${dataLunga(l.data)}${l.nuova ? ' <span class="tag bad">nuova</span>' : ""}<small>${l.inizio}–${l.fine}</small></td>
    <td><strong>${esc(l.materia)}</strong><div class="muted">${esc([l.docenti.join(", "), l.aule.join(", ")].filter(Boolean).join(" · "))}</div></td>
    <td><span class="tag">${esc(l.stato)}</span><div class="muted">${dettagliVariazione(l)}</div></td></tr>`).join("")}</tbody></table></div>`;
}

// La sigla di una materia per la griglia del telefono: «Lingua e letteratura italiana» → ITA, «Scienze motorie e sportive» → SMS.
const PAROLE_VUOTE = new Set(["e", "ed", "di", "del", "della", "delle", "dei", "degli", "la", "le", "lo", "il", "i", "gli", "a", "al", "in", "per", "con", "lingua", "letteratura", "cultura"]);
function sigla(materia) {
  return String(materia).split("/").map((m) => {
    m = m.replace(/\(.*?\)/g, " ").trim();
    if (/^[A-Z]{2,5}$/.test(m)) return m;
    const parole = m.split(/[\s'’.,-]+/).filter((w) => w && !PAROLE_VUOTE.has(w.toLowerCase()));
    if (!parole.length) return m.slice(0, 3).toUpperCase();
    return (parole.length === 1 ? parole[0].slice(0, 3) : parole.slice(0, 3).map((w) => w[0]).join("")).toUpperCase();
  }).join("/");
}
// Un colore per materia: le materie dell'orario in ordine alfabetico prendono le tinte una dopo l'altra, così due materie
// diverse non si somigliano; chiaro e scuro li decide il tema (style.css).
const TINTE = [215, 25, 150, 275, 45, 190, 340, 100, 250, 5, 170, 305];
function tintaMateria(materia) {
  const tutte = [...new Set(lezioniOrario().map((l) => l.materia))].sort();
  return TINTE[Math.max(0, tutte.indexOf(materia)) % TINTE.length];
}

function cartaVariazione(l) {
  const grave = l.stato === "annullata";
  const chi = [l.docenti.join(", "), l.aule.length ? "aula " + l.aule.join(", ") : ""].filter(Boolean).join(" · ");
  return `<li class="${grave ? "grave" : ""}"><span class="cambio-ora">${l.inizio}</span><div>
    <div class="cambio-testa"><strong>${esc(l.materia)}</strong><span class="tag${grave ? " bad" : ""}">${esc(l.stato)}</span>${l.nuova ? '<span class="tag pieno">nuova</span>' : ""}</div>
    <div class="cambio-quando">${dataLunga(l.data).replace(/^./, (c) => c.toUpperCase())} · ${quando(l.data)}</div>
    <div class="muted">${[grave ? "" : esc(chi), dettagliVariazione(l)].filter(Boolean).join(" · ")}</div></div></li>`;
}

/* ---------- orario scritto a mano ---------- */

const GIORNI_SCUOLA = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato"];
const oreScritte = () => ((D.profilo && D.profilo.orario_personale) || {}).ore || [];
const hhmm =(m) => `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
const ORA_VALIDA = /^\d\d:\d\d$/;

function apriEditorOrario() {
  editorOrario = oreScritte().map((o) => ({ ...o }));
  if (!editorOrario.length) editorOrario = [{ giorno: 0, inizio: "08:00", fine: "09:00", materia: "", aula: "", docente: "" }];
  mostra();
}

// Copia nelle righe ciò che è scritto nei campi, così ridisegnare (aggiungere un'ora, ruotare il telefono) non perde nulla.
function leggiEditorOrario() {
  document.querySelectorAll("#editor-orario [data-riga]").forEach((riga) => {
    const ora = editorOrario[+riga.dataset.riga];
    if (ora) riga.querySelectorAll("[data-campo]").forEach((campo) => { ora[campo.dataset.campo] = campo.value.trim(); });
  });
}

function aggiungiOra(giorno) {
  leggiEditorOrario();
  const suoi = editorOrario.filter((o) => o.giorno === giorno && ORA_VALIDA.test(o.fine)).sort((a, b) => a.fine.localeCompare(b.fine));
  const ultima = suoi[suoi.length - 1];
  // La nuova ora parte quando finisce l'ultima e dura come lei (60 minuti se il giorno è vuoto).
  const durata = ultima && ORA_VALIDA.test(ultima.inizio) ? Math.max(30, minuti(ultima.fine) - minuti(ultima.inizio)) : 60;
  const inizio = ultima ? ultima.fine : "08:00";
  editorOrario.push({ giorno, inizio, fine: hhmm(minuti(inizio) + durata), materia: "", aula: "", docente: "" });
  mostra();
  const nuove = document.querySelectorAll(`#editor-orario [data-giorno-righe="${giorno}"] [data-campo="materia"]`);
  if (nuove.length) nuove[nuove.length - 1].focus();
}

// Lo stesso giorno su un altro: comodo quando due giorni hanno le stesse ore (le materie si cambiano dopo).
function copiaGiorno(da, a) {
  leggiEditorOrario();
  editorOrario = editorOrario.filter((o) => o.giorno !== a).concat(editorOrario.filter((o) => o.giorno === da).map((o) => ({ ...o, giorno: a })));
  mostra();
}

async function salvaOrario(ore) {
  try {
    const pagina = await api("/api/orario", { ore });
    editorOrario = null;
    avviso("");
    applica(pagina);
  } catch (errore) { avviso(errore.message, true); }
}

function vistaEditorOrario() {
  if ($("#editor-orario")) leggiEditorOrario();
  const materie = [...new Set([...(D.materie || []), ...editorOrario.map((o) => o.materia)].filter(Boolean))].sort();
  const giorno = (g) => {
    const righe = editorOrario.map((o, i) => [o, i]).filter(([o]) => o.giorno === g).sort(([a], [b]) => a.inizio.localeCompare(b.inizio));
    return `<div class="box pad giorno-editor" data-giorno-righe="${g}"><h3>${GIORNI_SCUOLA[g]}</h3>
      ${righe.length ? righe.map(([o, i]) => `<div class="riga-ora" data-riga="${i}">
        <label><span>Dalle</span><input data-campo="inizio" type="time" value="${esc(o.inizio)}" required></label>
        <label><span>Alle</span><input data-campo="fine" type="time" value="${esc(o.fine)}" required></label>
        <label><span>Materia</span><input data-campo="materia" list="materie-orario" value="${esc(o.materia)}" placeholder="Es. Matematica" maxlength="60"></label>
        <label><span>Aula</span><input data-campo="aula" value="${esc(o.aula)}" maxlength="40"></label>
        <label><span>Docente</span><input data-campo="docente" value="${esc(o.docente)}" maxlength="40"></label>
        <button type="button" class="btn ghost small" data-togli-ora="${i}" aria-label="Togli quest'ora">Togli</button></div>`).join("") : '<p class="muted">Nessuna lezione.</p>'}
      <div class="segmenti"><button type="button" class="btn ghost small" data-aggiungi-ora="${g}">+ Aggiungi un'ora</button>
        ${g > 0 && editorOrario.some((o) => o.giorno === g - 1) ? `<button type="button" class="btn ghost small" data-copia-giorno="${g - 1}|${g}">Come ${GIORNI_SCUOLA[g - 1].toLowerCase()}</button>` : ""}</div></div>`;
  };
  return `<div id="editor-orario">
    ${titolo("Il tuo orario", "uguale ogni settimana")}
    <p class="sub" style="margin:0 0 12px">Scrivi le ore di ogni giorno: compariranno nella griglia, nella scheda Oggi e nel PDF. La materia si può scegliere tra quelle del registro o scrivere come vuoi.</p>
    <datalist id="materie-orario">${materie.map((m) => `<option value="${esc(m)}">`).join("")}</datalist>
    <div class="editor-giorni">${[0, 1, 2, 3, 4, 5].map(giorno).join("")}</div>
    <div class="segmenti" style="margin-top:16px"><button type="button" class="btn" data-orario-azione="salva">Salva l'orario</button>
      <button type="button" class="btn ghost" data-orario-azione="annulla">Annulla</button>
      ${oreScritte().length ? `<button type="button" class="btn ghost" data-orario-azione="cancella">Cancella tutto l'orario</button>` : ""}</div></div>`;
}

// La scelta per un'ora che WebUntis scrive come due materie: vale per quel giorno della settimana e quell'ora.
function sceltaDivisione(l) {
  if (!l.scelte || !l.scelte.length) return "";
  const chiave = `${l.originale.toLowerCase()}|${(giorno(l.data).getDay() + 6) % 7}|${l.inizio}`;
  const attuale = (((D.profilo && D.profilo.orario_personale) || {}).divisione || {})[chiave] || "";
  const bottone = (valore, testo) => `<button type="button" class="btn small${attuale === valore ? "" : " ghost"}" data-dividi="${esc(chiave)}" data-materia="${esc(valore)}" aria-pressed="${attuale === valore}">${esc(testo)}</button>`;
  return `<div class="dividi"><span class="muted">Su WebUntis è «${esc(l.originale)}». Ogni ${GIORNI[giorno(l.data).getDay()]} alle ${l.inizio} è:</span>
    <div class="segmenti">${l.scelte.map((m) => bottone(m, m)).join("")}${bottone("", "Tutte e due")}</div></div>`;
}

async function dividiOra(chiave, materia) {
  try { applica(await api("/api/orario", { chiave, materia })); } catch (errore) { avviso(errore.message, true); }
}

function schedaOrario() {
  if (editorOrario) return vistaEditorOrario();
  const o = D.orario;
  if (!o) return `<div class="box" style="margin-top:20px"><div class="empty">${D.profilo && !D.profilo.untis
    ? `Questo profilo non ha l'orario WebUntis.<br>Puoi scrivere il tuo orario a mano: basta farlo una volta.
      <div class="segmenti" style="justify-content:center;margin-top:12px"><button type="button" class="btn" data-orario-azione="apri">Scrivi il tuo orario</button></div>
      <p class="note">Se la scuola usa WebUntis, puoi invece aggiungerlo da Profili → Modifica.</p>`
    : "Orario non ancora scaricato: premi «Aggiorna»."}</div></div>`;
  if (!o.settimane.length) return '<div class="box" style="margin-top:20px"><div class="empty">Nessuna lezione in orario per questa settimana e la prossima (vacanze?).</div></div>';
  settimanaOrario = Math.min(settimanaOrario, o.settimane.length - 1);
  const s = o.settimane[settimanaOrario];
  const lezioni = o.lezioni.filter((l) => l.data >= s.inizio && l.data <= s.fine);
  const variazioni = lezioni.filter((l) => l.variazione);
  const adesso = oraDi(new Date());
  const passata = (l) => l.data < D.oggi || (l.data === D.oggi && l.fine <= adesso);
  const inCorso = (l) => l.data === D.oggi && l.inizio <= adesso && adesso < l.fine && l.stato !== "annullata";
  // Senza una scelta si vedono i dettagli dell'ora in corso.
  const scelta = oraOrario || (lezioni.find(inCorso) ? `${D.oggi}|${lezioni.find(inCorso).inizio}` : null);
  const cella = (g, inizio) => {
    const qui = lezioni.filter((l) => l.data === g && l.inizio === inizio);
    if (!qui.length) return '<div class="cella vuota"></div>';
    const chiave = `${g}|${inizio}`, ann = qui.every((l) => l.stato === "annullata"), varia = qui.some((l) => l.variazione);
    const classi = ["cella", passata(qui[0]) ? "passata" : "", qui.some(inCorso) ? "ora" : "", ann ? "annullata" : varia ? "variata" : "", chiave === scelta ? "scelta" : ""].filter(Boolean).join(" ");
    const etichetta = `${dataLunga(g)}, ${inizio}: ${qui.map((l) => l.materia + (l.variazione ? ", " + l.stato : "")).join("; ")}`;
    return `<button type="button" class="${classi}" style="--tinta:${tintaMateria(qui[0].materia)}" data-cella="${chiave}" aria-pressed="${chiave === scelta}" aria-label="${esc(etichetta)}">
      <span class="sigla">${esc(qui.map((l) => sigla(l.materia)).join("/"))}</span><span class="nome-m">${esc(qui.map((l) => l.materia).join(" / "))}</span>
      <span class="cella-sotto">${varia ? esc(qui.find((l) => l.variazione).stato) : esc(qui.flatMap((l) => l.aule).join(", "))}</span>${varia ? '<i class="pallino" aria-hidden="true"></i>' : ""}</button>`;
  };
  const dettaglio = () => {
    const qui = scelta ? lezioni.filter((l) => `${l.data}|${l.inizio}` === scelta) : [];
    if (!qui.length) return '<p class="cella-dettaglio vuoto muted">Tocca un\'ora per vedere aula, docente e variazioni.</p>';
    return qui.map((l) => `<div class="cella-dettaglio" style="--tinta:${tintaMateria(l.materia)}"><div>
      <strong>${esc(l.materia)}</strong>${inCorso(l) ? ' <span class="tag accento">adesso</span>' : ""}${l.variazione ? ` <span class="tag${l.stato === "annullata" || l.nuova ? " bad" : ""}">${esc(l.stato)}</span>` : ""}
      <div class="muted">${dataLunga(l.data).replace(/^./, (c) => c.toUpperCase())} · ${l.inizio}–${l.fine}${dettagliLezione(l) ? " · " + dettagliLezione(l) : ""}${l.variazione && dettagliVariazione(l) ? " · " + dettagliVariazione(l) : ""}</div>${sceltaDivisione(l)}</div></div>`).join("");
  };
  const t = new Date(o.scaricato);
  const manuale = o.fonte === "manuale";
  const fonte = manuale ? "il tuo orario, scritto a mano"
    : `orario letto da WebUntis ${quando(o.scaricato) === "oggi" ? "oggi" : "il " + dataBreve(o.scaricato)} alle ${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}`;
  const doppie = lezioni.some((l) => l.scelte && l.scelte.length);
  return `<div class="barra-azioni">
      <div class="segmenti" role="group" aria-label="Settimana">${o.settimane.map((x, i) => `<button type="button" class="btn small${i === settimanaOrario ? "" : " ghost"}" data-settimana="${i}">${i === 0 ? "Questa settimana" : i === 1 ? "Prossima" : "Dal " + dataBreve(x.inizio)}</button>`).join("")}</div>
      <div class="segmenti">${manuale ? `<button type="button" class="btn ghost small" data-orario-azione="apri">Modifica l'orario</button>` : ""}
        <a class="btn ghost small" href="/api/pdf?settimana=${settimanaOrario}" target="_blank" rel="noopener">Scarica PDF</a></div>
    </div>
    <p class="sub" style="margin:0 0 12px">Dal ${dataBreve(s.inizio)} al ${dataBreve(s.fine)}${manuale ? "" : ` · ${variazioni.length ? plurale(variazioni.length, "variazione", "variazioni") : "nessuna variazione"}`} · ${fonte}</p>
    ${doppie ? `<p class="note" style="margin:-4px 0 12px">Alcune ore mettono insieme due materie: tocca l'ora e scegli quale è davvero, così la griglia, la scheda Oggi e il PDF tornano giusti.</p>` : ""}
    <div class="orario-layout"><div>
      ${titolo("La settimana", "tocca un'ora per i dettagli")}
      <div class="box pad"><div class="griglia-orario" style="--giorni:${s.giorni.length}">
        <span></span>${s.giorni.map((g) => `<span class="testa-giorno${g === D.oggi ? " oggi" : ""}">${GIORNI[giorno(g).getDay()].slice(0, 3)}<b>${giorno(g).getDate()}</b></span>`).join("")}
        ${s.fasce.map(([inizio, fine]) => `<span class="ora-fascia${s.giorni.includes(D.oggi) && inizio <= adesso && adesso < fine ? " ora" : ""}"><b>${inizio}</b><small>${fine}</small><i>${inizio.slice(0, 2)}</i></span>${s.giorni.map((g) => cella(g, inizio)).join("")}`).join("")}
      </div>
      ${dettaglio()}
      <div class="legenda-orario"><span class="l-ora">adesso</span><span class="l-var">variazione</span><span class="l-ann">annullata</span></div></div>
    </div><div>
      ${manuale ? `${titolo("Variazioni")}<div class="box"><div class="empty">L'orario scritto a mano non ha supplenze né ore annullate: quelle arrivano solo da WebUntis.</div></div>` : `
      ${titolo("Cosa cambia", variazioni.length ? plurale(variazioni.length, "variazione", "variazioni") : "")}
      ${variazioni.length ? `<ul class="cambi">${variazioni.map(cartaVariazione).join("")}</ul>` : '<div class="box"><div class="empty">Nessuna variazione questa settimana.</div></div>'}`}
      <p class="note">Le lezioni in parallelo che non ti riguardano si nascondono da config.py (ORARIO_NASCONDI). Un docente indicato con una sigla è un supplente che non compare nel tuo registro.</p>
    </div></div>`;
}

// Gli impegni di ogni giorno, per il calendario dell'Agenda: verifiche, altri promemoria, compiti e variazioni d'orario.
function impegniPerGiorno() {
  const m = new Map(), di = (iso) => { if (!m.has(iso)) m.set(iso, { verifiche: [], promemoria: [], compiti: [], variazioni: [] }); return m.get(iso); };
  D.promemoria.forEach((p) => di(p.data)[p.verifica ? "verifiche" : "promemoria"].push(p));
  D.compiti.forEach((c) => di(c.consegna).compiti.push(c));
  lezioniOrario().filter((l) => l.variazione).forEach((l) => di(l.data).variazioni.push(l));
  return m;
}

// Il mese come griglia (dal lunedì). In ogni giorno un puntino per impegno; sul PC al posto dei puntini i nomi delle materie.
function calendarioMese(impegni) {
  const base = giorno(D.oggi), primo = new Date(base.getFullYear(), base.getMonth() + meseAgenda, 1);
  const giorniMese = new Date(primo.getFullYear(), primo.getMonth() + 1, 0).getDate(), vuoti = (primo.getDay() + 6) % 7;
  const celle = Array(vuoti).fill('<span class="giorno-cal fuori"></span>');
  for (let g = 1; g <= giorniMese; g++) {
    const iso = isoDi(new Date(primo.getFullYear(), primo.getMonth(), g)), x = impegni.get(iso);
    const voci = x ? [...x.verifiche.map((p) => ["v", p.materia || "Verifica"]), ...x.variazioni.map((l) => ["x", l.materia]),
      ...x.compiti.map((c) => [fatti.has(c.id) ? "c fatto" : "c", c.materia]), ...x.promemoria.map((p) => ["p", p.materia || "Promemoria"])] : [];
    const classe = [iso === D.oggi ? "oggi" : "", iso === giornoAgenda ? "scelto" : "", iso < D.oggi ? "passato" : "", (new Date(primo.getFullYear(), primo.getMonth(), g).getDay() + 6) % 7 > 4 ? "festivo" : ""].filter(Boolean).join(" ");
    const descrizione = voci.length ? `: ${plurale(voci.length, "impegno", "impegni")}` : "";
    celle.push(`<button type="button" class="giorno-cal ${classe}" data-giorno="${iso}" aria-pressed="${iso === giornoAgenda}" aria-label="${esc(dataLunga(iso) + descrizione)}">
      <span class="num">${g}</span><span class="cal-punti">${voci.slice(0, 4).map(([t]) => `<i class="${t}"></i>`).join("")}</span>
      <span class="cal-et">${voci.slice(0, 3).map(([t, n]) => `<i class="${t}">${esc(n)}</i>`).join("")}${voci.length > 3 ? `<small>+${voci.length - 3}</small>` : ""}</span></button>`);
  }
  const nome = `${MESI_LUNGHI[primo.getMonth()].replace(/^./, (c) => c.toUpperCase())} ${primo.getFullYear()}`;
  return `<h2 class="con-destra">${nome}<span class="h2-destra mesi"><button type="button" class="link" data-mese="-1" aria-label="Mese precedente">‹</button>
      <button type="button" class="link" data-mese="0">oggi</button><button type="button" class="link" data-mese="1" aria-label="Mese seguente">›</button></span></h2>
    <div class="box pad calendario-mese"><div class="cal-griglia">${["L", "M", "M", "G", "V", "S", "D"].map((g) => `<span class="cal-testa">${g}</span>`).join("")}${celle.join("")}</div>
      <div class="cal-legenda"><span><i class="v"></i>verifica</span><span><i class="c"></i>compito</span><span><i class="x"></i>variazione</span><span><i class="p"></i>promemoria</span></div></div>`;
}

// Cosa c'è nel giorno scelto sul calendario; i compiti si spuntano da qui come nella scheda Compiti.
function giornoScelto(impegni, iso = giornoAgenda) {
  const x = impegni.get(iso) || { verifiche: [], promemoria: [], compiti: [], variazioni: [] };
  const riga = (classe, titolo, sotto, coda = "") => `<li class="evento ${classe}"><i aria-hidden="true"></i><div>${titolo}<div class="muted">${sotto}</div></div>${coda}</li>`;
  const eventi = [
    ...x.verifiche.map((p) => riga("v", `${puntoNuovo(nuovo("verifiche", chiaveVerifica(p)))}<strong>${esc(p.materia) || "Verifica"}</strong>`,
      [esc(p.testo), esc(p.orario), esc(aulaPromemoria(p))].filter(Boolean).join(" · "), '<span class="tag bad">verifica</span>')),
    ...x.variazioni.map((l) => riga("x", `<strong>${esc(l.materia)}</strong>`, `${l.inizio}–${l.fine}${dettagliVariazione(l) ? " · " + dettagliVariazione(l) : ""}`, `<span class="tag${l.nuova || l.stato === "annullata" ? " bad" : ""}">${esc(l.stato)}</span>`)),
    ...x.promemoria.map((p) => riga("p", `<strong>${esc(p.materia) || "Promemoria"}</strong>`, [esc(p.testo), esc(p.orario)].filter(Boolean).join(" · "))),
  ].join("");
  const compiti = x.compiti.map((c) => `<li class="${fatti.has(c.id) ? "fatto" : ""}"><label><input type="checkbox" data-id="${c.id}" ${fatti.has(c.id) ? "checked" : ""}>
    <span>${puntoNuovo(nuovo("compiti", c.id))}<strong>${esc(c.materia)}</strong> — ${esc(c.testo)}</span></label></li>`).join("");
  const testa = dataLunga(iso).replace(/^./, (c) => c.toUpperCase());
  return `${titolo(testa, quando(iso))}<div class="box giorno-scelto">${eventi || compiti
    ? `${eventi ? `<ul class="eventi">${eventi}</ul>` : ""}${compiti ? `<ul class="todo">${compiti}</ul>` : ""}` : '<div class="empty">Niente in programma per questo giorno.</div>'}</div>`;
}

function schedaAgenda() {
  const verifiche = D.promemoria.filter((p) => p.verifica && giorniDa(p.data) >= 0), altri = D.promemoria.filter((p) => !p.verifica && giorniDa(p.data) >= 0);
  const variazioni = lezioniOrario().filter((l) => l.variazione && giorniDa(l.data) >= 0);
  const futuri = D.compiti.filter((c) => giorniDa(c.consegna) >= 0);
  const daFare = futuri.filter((c) => !fatti.has(c.id)).length;
  const urgenti = D.consigli.filter((c) => c.livello !== "info").slice(0, 3);
  if (!giornoAgenda) giornoAgenda = D.oggi;
  const impegni = impegniPerGiorno();
  // Sul PC il calendario a sinistra e il giorno scelto a destra; sul telefono uno sotto l'altro. Gli elenchi completi restano, chiusi, in fondo.
  return `<div class="cards">
      ${tessera(verifiche.length, "verifiche in arrivo")}
      ${tessera(daFare, "compiti da fare")}
      ${tessera(variazioni.length, "variazioni d'orario")}
      ${tessera(media(D.media_generale), "media generale")}
    </div>
    <div class="agenda-griglia"><div class="agenda-colonna">${calendarioMese(impegni)}</div>
      <div class="agenda-colonna">${giornoScelto(impegni)}${urgenti.length ? `${titolo("Da tenere d'occhio")}${listaConsigli(urgenti)}` : ""}</div></div>
    <div class="sezioni">
      ${sezione("a-verifiche", "Tutte le verifiche in arrivo", verifiche.length, tabellaPromemoria(verifiche))}
      ${sezione("a-compiti", "Tutti i compiti da fare", daFare, listaCompiti(futuri, "Nessun compito da fare."))}
      ${variazioni.length ? sezione("a-variazioni", "Variazioni d'orario", variazioni.length, listaVariazioni(variazioni)) : ""}
      ${altri.length ? sezione("a-promemoria", "Altri promemoria", altri.length, `${tabellaPromemoria(altri)}
        <p class="note">Promemoria futuri senza parole chiave da verifica: dai un'occhiata, potrebbe essercene una scritta in modo insolito.</p>`) : ""}
      ${riquadroCalendario()}
    </div>`;
}

// Mappa stile GitHub: una casella per giorno di consegna, blu pieno se hai fatto tutto, più chiaro man mano che ne salti.
function coloreGiorno(quota) { return `color-mix(in srgb, var(--series-1) ${Math.round(30 + quota * 70)}%, var(--track))`; }

function mappaCompiti() {
  const tutti = D.compiti_anno || [];
  if (!tutti.length) return "";
  const perGiorno = new Map();
  tutti.forEach((c) => { const g = perGiorno.get(c.consegna) || { n: 0, fatti: 0 }; g.n++; if (fatti.has(c.id)) g.fatti++; perGiorno.set(c.consegna, g); });
  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const lunedi = (d) => { const r = new Date(d); r.setDate(r.getDate() - ((r.getDay() + 6) % 7)); return r; };
  const date = [...perGiorno.keys()].sort();
  const inizio = lunedi(giorno(date[0])), fine = lunedi(giorno(date[date.length - 1] > D.oggi ? date[date.length - 1] : D.oggi));

  let caselle = "", mesi = "", ultimoMese = -1, passati = 0, passatiFatti = 0, serie = 0, serieAperta = true;
  const giorniPassati = [];
  for (let s = new Date(inizio), col = 0; s <= fine; s.setDate(s.getDate() + 7), col++) {
    const primo = new Date(s);
    if (primo.getMonth() !== ultimoMese) { mesi += `<span style="grid-column:${col + 1}">${MESI[primo.getMonth()]}</span>`; ultimoMese = primo.getMonth(); }
    for (let r = 0; r < 7; r++) {
      const d = new Date(s); d.setDate(d.getDate() + r);
      const k = iso(d), g = perGiorno.get(k), oggi = k === D.oggi, passato = k < D.oggi;
      const cl = [oggi ? "oggi" : "", !g ? "vuoto" : ""];
      if (!g) { caselle += `<i class="${cl.join(" ")}" ${tip(`<b>${dataLunga(k)}</b><br>Nessun compito`)}></i>`; continue; }
      const quota = g.fatti / g.n, finito = g.fatti === g.n;
      const aperto = !passato && !oggi; // consegna ancora lontana: si può ancora fare
      if (!aperto) { passati += g.n; passatiFatti += g.fatti; }
      const testo = `<b>${dataLunga(k)}</b><br>${g.fatti} su ${plurale(g.n, "compito fatto", "compiti fatti")}`;
      if (aperto && !finito) caselle += `<i class="futuro ${cl.join(" ")}" ${tip(testo)}></i>`;
      else if (g.fatti === 0) caselle += `<i class="nessuno ${cl.join(" ")}" ${tip(testo)}></i>`;
      else caselle += `<i class="${cl.join(" ")}" style="background:${coloreGiorno(quota)}" ${tip(testo)}></i>`;
      if (!aperto) giorniPassati.push({ k, finito, oggi });
    }
  }
  // Serie: giorni di consegna consecutivi (dal più recente) con tutto fatto. Oggi non incompleto non interrompe la serie.
  for (let i = giorniPassati.length - 1; i >= 0 && serieAperta; i--) {
    if (giorniPassati[i].finito) serie++;
    else if (!giorniPassati[i].oggi) serieAperta = false;
  }
  const quotaTot = passati ? Math.round((passatiFatti / passati) * 100) : null;
  const giorniNomi = ["Lun", "", "Mer", "", "Ven", "", ""].map((n) => `<span>${n}</span>`).join("");
  const legendaMappa = `<div class="heat-legenda">Niente <i class="leg-nessuno"></i>${[0.25, 0.5, 0.75, 1].map((q) => `<i style="background:${coloreGiorno(q)}"></i>`).join("")} Tutto fatto
    <span style="margin-left:12px"><i style="border:1px dashed var(--axis)"></i> da consegnare</span></div>`;
  return `<h2>Il tuo andamento</h2>
    <div class="cards" style="margin-top:0">
      ${tessera(quotaTot == null ? "–" : quotaTot + "%", "compiti fatti, tra quelli già in scadenza")}
      ${tessera(serie, "giorni di fila con tutto fatto", serie ? "ok" : "")}
    </div>
    <div class="box pad" style="margin-top:12px"><p class="chart-title">Compiti fatti, giorno per giorno</p>
      <p class="chart-sub">Ogni casella è un giorno di consegna: colore pieno se hai spuntato tutto, sempre più chiaro se ne salti. ${temaNothing() ? "Rosso" : "Grigio"} = nessuno fatto.</p>
      <div class="heat" data-ultimo><div class="heat-in"><div class="heat-mesi" style="grid-template-columns:repeat(${Math.round((fine - inizio) / 6048e5) + 1},15px)">${mesi}</div>
        <div class="heat-corpo"><div class="heat-giorni">${giorniNomi}</div><div class="heat-griglia">${caselle}</div></div></div></div>
      ${legendaMappa}
      <p class="note">I compiti che non hai mai spuntato contano come non fatti, anche quelli di prima di iniziare a usare l'app.</p></div>`;
}

const GIORNI_BREVI = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"];

// La settimana dei compiti: una colonna per giorno sul PC; sul telefono la stessa struttura diventa una striscia di giorni
// da toccare con l'elenco del giorno scelto sotto (style.css). La domenica compare solo se c'è qualcosa da consegnare.
function settimanaCompiti() {
  const tutti = D.compiti_anno && D.compiti_anno.length ? D.compiti_anno : D.compiti;
  const oggi = giorno(D.oggi), lunedi = new Date(oggi);
  lunedi.setDate(oggi.getDate() - ((oggi.getDay() + 6) % 7) + (oggi.getDay() === 0 ? 7 : 0) + 7 * settimanaCompitiScelta); // di domenica si guarda già la settimana dopo
  const giorni = Array.from({ length: 7 }, (_, i) => isoDi(new Date(lunedi.getFullYear(), lunedi.getMonth(), lunedi.getDate() + i)));
  const per = new Map(giorni.map((g) => [g, []]));
  tutti.forEach((c) => per.has(c.consegna) && per.get(c.consegna).push(c));
  const visibili = giorni.filter((g, i) => i < 6 || per.get(g).length);
  if (!visibili.includes(giornoCompiti)) giornoCompiti = visibili.includes(D.oggi) ? D.oggi : visibili.find((g) => per.get(g).some((c) => !fatti.has(c.id))) || visibili[0];
  const primo = giorno(visibili[0]), ultimo = giorno(visibili[visibili.length - 1]);
  const intervallo = primo.getMonth() === ultimo.getMonth() ? `${primo.getDate()}–${ultimo.getDate()} ${MESI_LUNGHI[primo.getMonth()]}` : `${primo.getDate()} ${MESI[primo.getMonth()]} – ${ultimo.getDate()} ${MESI[ultimo.getMonth()]}`;
  const colonne = visibili.map((g) => {
    const compiti = per.get(g), lista = compiti.filter((c) => !nascondiFatti || !fatti.has(c.id)), d = giorno(g);
    const nome = dataLunga(g).replace(/^./, (c) => c.toUpperCase()), daFare = compiti.filter((c) => !fatti.has(c.id)).length;
    return `<div class="sett-giorno${g === giornoCompiti ? " scelto" : ""}${g === D.oggi ? " oggi" : ""}${g < D.oggi ? " passato" : ""}">
      <button type="button" class="sett-testa" data-giorno-compiti="${g}" aria-pressed="${g === giornoCompiti}" aria-label="${esc(nome)}: ${plurale(daFare, "compito da fare", "compiti da fare")}">
        <span>${GIORNI_BREVI[(d.getDay() + 6) % 7]}</span><b>${d.getDate()}</b><span class="sett-punti">${compiti.slice(0, 4).map((c) => `<i class="${fatti.has(c.id) ? "fatto" : ""}"></i>`).join("")}</span></button>
      <div class="sett-corpo"><p class="sett-titolo">${nome} <span class="muted">· ${quando(g)}</span></p>
        ${lista.length ? `<ul class="todo sett-lista">${lista.map((c) => `<li class="${fatti.has(c.id) ? "fatto" : ""}"><label><input type="checkbox" data-id="${c.id}" ${fatti.has(c.id) ? "checked" : ""}>
          <span>${puntoNuovo(nuovo("compiti", c.id))}<strong>${esc(c.materia)}</strong> <span class="sett-testo">${esc(c.testo)}</span></span></label></li>`).join("")}</ul>`
          : `<p class="sett-vuoto muted">${compiti.length ? "Tutto fatto ✓" : "Libero 🎉"}</p>`}</div></div>`;
  }).join("");
  return `<h2 class="con-destra">Settimana ${intervallo}<span class="h2-destra mesi"><button type="button" class="link" data-sett-compiti="-1" aria-label="Settimana precedente">‹</button>
      <button type="button" class="link" data-sett-compiti="0">questa</button><button type="button" class="link" data-sett-compiti="1" aria-label="Settimana seguente">›</button></span></h2>
    <div class="settimana" style="--giorni:${visibili.length}">${colonne}</div>`;
}

function schedaCompiti() {
  const futuri = D.compiti.filter((c) => giorniDa(c.consegna) >= 0), scaduti = D.compiti.filter((c) => giorniDa(c.consegna) < 0);
  const nFatti = futuri.filter((c) => fatti.has(c.id)).length;
  const nonFatti = scaduti.filter((c) => !fatti.has(c.id)).length;
  return `<div class="cerca"><input type="search" id="cerca-compiti" value="${esc(ricerca)}" placeholder="Cerca nei compiti di tutto l'anno: materia, parola, pagina…" aria-label="Cerca nei compiti" autocomplete="off"></div>
    <div id="risultati-ricerca" class="risultati">${risultatiRicerca()}</div>
    <div id="compiti-normali"${ricerca.trim() ? " hidden" : ""}>
    <div class="barra-azioni">
      <div style="flex:1;min-width:220px"><strong>Fatti ${nFatti} su ${futuri.length}</strong> <span class="muted">tra quelli da consegnare</span>
        <div class="progresso"><i style="width:${futuri.length ? (nFatti / futuri.length) * 100 : 0}%"></i></div></div>
      <label><input type="checkbox" id="nascondi" ${nascondiFatti ? "checked" : ""}> Nascondi i fatti</label>
      <a class="btn ghost small" href="/api/esporta-compiti" target="_blank" rel="noopener">Scarica tutti i compiti (PDF)</a>
    </div>
    ${settimanaCompiti()}
    ${nonFatti ? `<h2>Scaduti negli ultimi giorni <span class="tag bad">${nonFatti} non spuntati</span></h2>${listaCompiti(scaduti.slice().reverse(), "Nessun arretrato.")}` : ""}
    ${mappaCompiti()}
    <div class="sezioni">
      ${sezione("c-futuri", "Tutti i compiti da fare", futuri.length - nFatti, listaCompiti(futuri, nascondiFatti && futuri.length ? "Tutto fatto!" : "Nessun compito da fare."))}
      ${scaduti.length && !nonFatti ? sezione("c-scaduti", "Scaduti negli ultimi giorni", scaduti.length, listaCompiti(scaduti.slice().reverse(), "Nessun compito scaduto di recente.")) : ""}
    </div>
    <p class="note">Spunta un compito quando l'hai fatto: resta salvato anche dopo l'aggiornamento dei dati.</p></div>`;
}

// Avvisa se la media calcolata qui non coincide con quella del registro (es. voti pesati).
function notaRegistro(s) {
  if (s.media_registro == null || Math.abs(s.media_registro - s.media) < 0.05) return "";
  return ` <span title="Il registro può pesare i voti in modo diverso">Sul registro la media risulta ${media(s.media_registro)}.</span>`;
}

function testoMinimo(s) {
  const v = s.minimo_sufficienza;
  if (s.insufficiente) return v > 10 ? "Una sola prova non basta per tornare al 6: servono più voti alti." : `Per tornare al 6 alla prossima prova serve almeno <strong>${num(v)}</strong>.`;
  if (v <= 1) return "Alla prossima prova resti al 6 con <strong>qualsiasi voto</strong>.";
  return `Voto minimo alla prossima prova per restare al 6: <strong>${num(v)}</strong>.`;
}

// «Che voto mi serve?»: tocchi la materia e il voto e vedi subito le medie che cambierebbero.
// I voti già aggiunti (simulati) restano in pila; simVoto è quello che stai provando adesso.
function simulatore() {
  const tutte = [...new Set([...D.materie, ...D.statistiche.map((s) => s.materia)])].sort();
  if (!tutte.includes(simMateria)) simMateria = (D.statistiche[0] || {}).materia || tutte[0] || "";
  const base = Object.fromEntries(D.statistiche.map((s) => [s.materia, { somma: s.somma, n: s.numero }]));
  const conVoti = (lista) => {
    const o = JSON.parse(JSON.stringify(base));
    lista.forEach((x) => { const m = (o[x.materia] ||= { somma: 0, n: 0 }); m.somma += x.voto; m.n += 1; });
    return o;
  };
  const prova = simVoto == null ? simulati : [...simulati, { materia: simMateria, voto: simVoto }];
  const pila = conVoti(simulati), dopo = conVoti(prova);
  const mediaDi = (o) => (o && o.n ? o.somma / o.n : null);
  const generale = (o) => { const m = Object.values(o).filter((x) => x.n).map(mediaDi); return m.length ? m.reduce((a, b) => a + b, 0) / m.length : null; };
  const cur = pila[simMateria] || { somma: 0, n: 0 };
  const serve = (obiettivo) => {
    const v = arrotondaSu(obiettivo * (cur.n + 1) - cur.somma);
    return v > 10 ? "non basta una prova" : v <= 1 ? "qualsiasi voto" : `almeno ${num(v)}`;
  };
  const ora = mediaDi(base[simMateria]), poi = mediaDi(dopo[simMateria]);
  const riquadro = (etichetta, prima, adesso) => `<div><span>${etichetta}</span><p><s>${media(prima)}</s> <b class="${adesso != null && adesso < D.sufficienza ? "bad" : "ok"}">${media(adesso)}</b></p></div>`;
  let frase = "";
  if (simVoto != null && ora != null && poi != null) {
    const nome = esc(simMateria), voto = num(simVoto);
    frase = ora < D.sufficienza && poi >= D.sufficienza ? `<p class="ok">✓ Con un ${voto} ${nome} torna al 6.</p>`
      : ora >= D.sufficienza && poi < D.sufficienza ? `<p class="bad">Attenzione: con un ${voto} ${nome} scende sotto il 6.</p>`
      : `<p class="muted">Con un ${voto} ${nome} passa da ${media(ora)} a ${media(poi)}.</p>`;
  }
  const altro = simVoto != null && ![4, 5, 6, 7, 8, 9, 10].includes(simVoto) ? simVoto : "";
  return `<div class="box pad simulatore" id="simulatore">
    <p class="sim-etichetta">Materia</p>
    <div class="sim-scelte">${tutte.map((m) => `<button type="button" class="sim-scelta${m === simMateria ? " attiva" : ""}" data-sim="${esc(m)}">${esc(m)}</button>`).join("")}</div>
    <p class="sim-etichetta">Se alla prossima prendo…</p>
    <div class="sim-voti">${[4, 5, 6, 7, 8, 9, 10].map((v) => `<button type="button" class="sim-voto${v === simVoto ? " attiva" : ""}" data-sim-voto="${v}">${v}</button>`).join("")}
      <label class="sim-altro"><span class="sr">Altro voto, anche con i decimali</span><input id="sim-voto" type="number" min="1" max="10" step="0.25" placeholder="altro" value="${altro}"></label></div>
    ${simVoto == null && !simulati.length ? '<p class="note">Tocca un voto per vedere come cambierebbero le medie. Non modifica nulla sul registro.</p>'
      : `<div class="sim-esito">${riquadro(esc(simMateria), ora, poi)}${riquadro("Media generale", generale(base), generale(dopo))}</div>${frase}`}
    ${simulati.length ? `<div class="chips">${simulati.map((x, i) => `<span class="chip">${esc(x.materia)}: <strong>${num(x.voto)}</strong><button type="button" data-togli="${i}" aria-label="Togli">✕</button></span>`).join("")}</div>` : ""}
    <div class="sim-azioni">${simVoto != null ? '<button class="btn ghost small" id="sim-aggiungi" type="button">+ Aggiungi e prova un altro voto</button>' : ""}
      ${simulati.length || simVoto != null ? '<button class="btn ghost small" id="sim-azzera" type="button">Azzera</button>' : ""}</div>
    <p class="note">In ${esc(simMateria)}, alla prova successiva${simulati.length ? " (dopo quelli aggiunti)" : ""}: per avere 6 → ${serve(6)} · 7 → ${serve(7)} · 8 → ${serve(8)}.</p>
  </div>`;
}

// Tema «Nothing»: la media di ogni materia come dieci puntini (uno per punto), mezzo acceso per i decimali.
function votiAPunti(lista) {
  if (!lista.length) return '<p class="muted">Ancora nessun dato.</p>';
  const soglia = Math.round(D.sufficienza);
  return `<div class="voti-punti">${lista.map((s) => {
    const pieni = Math.floor(s.media), mezzo = s.media - pieni >= 0.25;
    const punti = Array.from({ length: 10 }, (_, i) => `<i class="${i < pieni ? "si" : i === pieni && mezzo ? "mezzo" : ""}"></i>${i + 1 === soglia ? '<b class="linea"></b>' : ""}`).join("");
    return `<div class="lab" title="${esc(s.materia)}">${esc(s.materia)}</div>
      <div class="fila${s.insufficiente ? " sotto" : ""}" ${tip(`<b>${esc(s.materia)}</b><br>Media ${media(s.media)} su ${plurale(s.numero, "voto", "voti")}`)}>${punti}</div>
      <div class="val${s.insufficiente ? " bad" : ""}">${media(s.media)}</div>`;
  }).join("")}</div>`;
}

const ANDAMENTO = { su: ["▲", "in salita", "ok"], giu: ["▼", "in calo", "bad"], stabile: ["=", "stabile", "neutro"] };

// Mini-grafico degli ultimi voti di una materia: linea tratteggiata sul 6, punti rossi sotto.
// Si allarga alla scheda (preserveAspectRatio="none"); i punti sono tratti di lunghezza zero con le estremità tonde, così restano rotondi.
function sparkVoti(materia) {
  const voti = D.voti.filter((v) => v.materia === materia && v.valore != null).sort((a, b) => (a.data < b.data ? -1 : 1)).slice(-8);
  if (!voti.length) return "";
  const w = 160, h = 44, y = (v) => (6 + (h - 12) * (1 - (Math.min(10, Math.max(3, v)) - 3) / 7)).toFixed(1);
  const x = (i) => (voti.length === 1 ? w / 2 : 6 + (i * (w - 12)) / (voti.length - 1)).toFixed(1);
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Ultimi voti: ${voti.map((v) => num(v.valore)).join(", ")}">
    <line class="rif" x1="0" x2="${w}" y1="${y(D.sufficienza)}" y2="${y(D.sufficienza)}"/>
    ${voti.length > 1 ? `<polyline points="${voti.map((v, i) => `${x(i)},${y(v.valore)}`).join(" ")}"/>` : ""}
    ${voti.map((v, i) => `<path class="${v.valore < D.sufficienza ? "sotto" : ""}" d="M${x(i)} ${y(v.valore)}h0"/>`).join("")}</svg>`;
}

// Una scheda per materia: tutto quello che c'era nella vecchia tabella, leggibile anche sul telefono.
function schedaMateria(s) {
  const [freccia, parola, classe] = ANDAMENTO[s.andamento] || ["·", "pochi voti", "neutro"];
  const tipi = [["Scritto", s.media_scritto], ["Orale", s.media_orale], ["Pratico", s.media_pratico]].filter(([, v]) => v != null);
  const valore = media(s.media);
  return `<div class="materia${s.insufficiente ? " insuff" : ""}">
    <div class="materia-testa"><strong>${esc(s.materia)}</strong><span class="tag ${classe}" title="Gli ultimi 3 voti confrontati con i precedenti">${freccia} ${parola}</span></div>
    <div class="materia-media"><div><b class="${s.insufficiente ? "bad" : ""}">${temaNothing() ? aPunti(valore, 4) : valore}</b><span>${plurale(s.numero, "voto", "voti")}</span></div>${sparkVoti(s.materia)}</div>
    ${tipi.length ? `<div class="materia-tipi">${tipi.map(([n, v]) => `<span>${n} <strong>${media(v)}</strong></span>`).join("")}</div>` : ""}
    <p class="muted materia-estremi">min ${num(s.minimo)} · max ${num(s.massimo)} · ultimo ${num(s.ultimo)}</p>
    <p class="materia-serve${s.insufficiente ? " sotto" : ""}">${testoMinimo(s)}${notaRegistro(s)}</p>
    <button type="button" class="link" data-sim="${esc(s.materia)}">E se prendo… →</button>
  </div>`;
}

// «Cosa fare adesso»: le materie sotto il 6, quelle in calo e le verifiche della settimana nelle materie in bilico.
function azioniVoti() {
  const voci = new Map();
  const prova = (s) => `<button type="button" class="link" data-sim="${esc(s.materia)}">Prova nel simulatore →</button>`;
  D.statistiche.filter((s) => s.insufficiente).forEach((s) => voci.set(s.materia, { s, livello: "critico", testo: testoMinimo(s), azione: prova(s) }));
  D.statistiche.filter((s) => s.andamento === "giu" && !s.insufficiente)
    .forEach((s) => voci.set(s.materia, { s, livello: "attenzione", testo: `In calo: gli ultimi voti sono sotto i precedenti. ${testoMinimo(s)}`, azione: prova(s) }));
  verificheFuture().filter((p) => giorniDa(p.data) <= 7).forEach((p) => {
    const s = D.statistiche.find((x) => x.materia === p.materia);
    if (!s || s.media >= D.sufficienza + 0.5) return;
    const verifica = `<strong>Verifica ${quando(p.data)}.</strong> `;
    if (voci.has(s.materia)) voci.get(s.materia).testo = verifica + voci.get(s.materia).testo;
    else voci.set(s.materia, { s, livello: "attenzione", testo: `${verifica}La media è appena sopra il 6: conviene prepararla bene.`, azione: prova(s) });
  });
  const lista = [...voci.values()];
  if (!lista.length) return '<div class="box"><div class="empty">Tutte le materie sono sopra il 6 e nessuna è in calo. Continua così!</div></div>';
  return `<div class="azioni-voti">${lista.slice(0, 3).map((v) => `<div class="azione ${v.livello}"><span class="azione-media">${media(v.s.media)}</span>
    <div><strong>${esc(v.s.materia)}</strong><p>${v.testo}</p>${v.azione}</div></div>`).join("")}</div>
    ${lista.length > 3 ? `<p class="note">E ${plurale(lista.length - 3, "altra materia", "altre materie")} da tenere d'occhio: le trovi nelle schede qui sotto.</p>` : ""}`;
}

// Una sezione che si apre con un tocco; resta aperta anche quando la scheda si ridisegna (sezioniAperte).
const sezione = (nome, testo, conto, corpo) => `<details class="sezione" data-sezione="${nome}"${sezioniAperte.has(nome) ? " open" : ""}>
  <summary>${testo} <span class="muted">${conto}</span></summary><div class="sezione-corpo">${corpo}</div></details>`;

function schedaVoti() {
  const st = D.statistiche, insufficienti = st.filter((s) => s.insufficiente).length;
  const migliore = st.length ? st[st.length - 1] : null;

  const perMateria = temaNothing() ? votiAPunti(st.slice().reverse()) : barre(st.slice().reverse().map((s) => ({
    label: s.materia, segmenti: [{ v: s.media, colore: "var(--series-1)" }], val: `<strong>${media(s.media)}</strong>${s.insufficiente ? ' <span class="tag bad">sotto il 6</span>' : ""}`,
    tip: `<b>${esc(s.materia)}</b><br>Media ${media(s.media)} su ${plurale(s.numero, "voto", "voti")}`,
  })), 10, D.sufficienza);

  const materieConVoti = st.map((s) => s.materia).sort();
  if (!materieConVoti.includes(materiaGrafico)) materiaGrafico = "";
  const scelti = D.voti.filter((v) => !materiaGrafico || v.materia === materiaGrafico);
  const punti = scelti.map((v) => ({ t: giorno(v.data), y: v.valore, tip: `<b>${esc(v.materia)}: ${esc(v.codice)}</b><br>${dataLunga(v.data)}${v.tipo ? " · " + esc(v.tipo) : ""}` }));
  let somma = 0;
  const progressiva = scelti.map((v, i) => ({ t: giorno(v.data), y: (somma += v.valore) / (i + 1) }));
  const nelTempo = scelti.length ? segnaposto((w) => andamento(w, punti, materiaGrafico ? null : progressiva)) : '<p class="muted">Ancora nessun voto.</p>';

  const distribuzione = D.voti.length ? segnaposto((w) => colonne(w, D.distribuzione.map((d) => ({
    label: d.fascia, valori: [d.numero], tip: `<b>${d.fascia === "<4" ? "Sotto il 4" : "Voti tra " + d.fascia + " e " + (d.fascia === "10" ? "10" : (+d.fascia + 1) + " escluso")}</b><br>${plurale(d.numero, "voto", "voti")}`,
  })), ["var(--series-1)"], { titolo: "Distribuzione dei voti" })) : '<p class="muted">Ancora nessun voto.</p>';

  const riga = (etichetta, r) => ({ label: etichetta, segmenti: [{ v: r.media || 0, colore: "var(--series-1)" }], val: `<strong>${media(r.media)}</strong> <span class="muted">(${r.numero})</span>`, tip: `<b>${esc(etichetta)}</b><br>Media ${media(r.media)} su ${plurale(r.numero, "voto", "voti")}` });
  const perTipo = barre(D.voti_per_tipo.map((r) => riga(r.tipo, r)), 10, D.sufficienza);
  const perMese = barre(D.voti_per_mese.map((r) => riga(mese(r.mese), r)), 10, D.sufficienza);
  const perPeriodo = barre(D.voti_per_periodo.filter((r) => r.numero).map((r) => riga(r.periodo, r)), 10, D.sufficienza);
  const grafici = `<div class="grid2">
      ${grafico("Media per materia", temaNothing() ? "Ogni puntino è un punto di media; la linea rossa segna la sufficienza." : "La lineetta verticale segna la sufficienza.", perMateria)}
      <div class="box pad"><div class="controllo"><div><p class="chart-title">Voti nel tempo</p>
        <p class="chart-sub">${materiaGrafico ? "Ogni punto è un voto." : "Ogni punto è un voto; la linea blu è la media progressiva."} La riga grigia più marcata è la sufficienza.</p></div>
        <select id="materia-grafico" aria-label="Materia"><option value="">Tutte le materie</option>${materieConVoti.map((m) => `<option${m === materiaGrafico ? " selected" : ""}>${esc(m)}</option>`).join("")}</select></div>${nelTempo}</div>
      ${grafico("Distribuzione dei voti", "Quanti voti hai preso per ogni fascia.", distribuzione)}
      ${grafico("Scritto, orale e pratico", "Media per tipo di prova (tra parentesi il numero di voti).", perTipo)}
      ${grafico("Media per mese", "Come sono andati i voti mese per mese.", perMese)}
      ${grafico("Media per periodo", "Voti raggruppati per quadrimestre.", perPeriodo)}
    </div>`;

  const fuori = (D.voti_fuori_media || []).map((v) => ({ ...v, fuori: true }));
  const tutti = [...D.voti, ...fuori].sort((a, b) => (a.data < b.data ? 1 : a.data > b.data ? -1 : 0));
  const elenco = `<div class="box"><table><thead><tr><th>Data</th><th>Materia</th><th class="n">Voto</th><th>Tipo</th><th>Prova</th></tr></thead><tbody>
    ${tutti.map((v) => `<tr><td class="when">${dataBreve(v.data)}</td><td>${puntoNuovo(!v.fuori && nuovo("voti", chiaveVoto(v)))}<strong>${esc(v.materia)}</strong><div class="muted">${esc(v.docente)}</div></td>
      <td class="n ${!v.fuori && v.valore < D.sufficienza ? "bad" : ""}"><strong>${esc(v.codice)}</strong>${v.fuori ? '<div><span class="tag">non fa media</span></div>' : ""}</td><td>${esc(v.tipo) || "—"}</td><td class="muted">${esc(v.descrizione)}</td></tr>`).join("")}
    </tbody></table></div>${fuori.length ? '<p class="note">I voti segnati «non fa media» (giudizi senza numero o voti esclusi dal docente) non entrano in medie e grafici.</p>' : ""}`;
  const recenti = tutti.filter((v) => !v.fuori).slice(0, 5);
  const ultimi = recenti.length ? `<div class="box"><ul class="ultimi-voti">${recenti.map((v) => `<li><span class="voto${v.valore < D.sufficienza ? " sotto" : ""}">${esc(v.codice)}</span>
      <div>${puntoNuovo(nuovo("voti", chiaveVoto(v)))}<strong>${esc(v.materia)}</strong><div class="muted">${[v.tipo, dataLunga(v.data)].filter(Boolean).map(esc).join(" · ")}</div></div></li>`).join("")}</ul></div>`
    : '<div class="box"><div class="empty">Ancora nessun voto.</div></div>';

  // Due colonne sul PC (a sinistra cosa fare e le materie, a destra simulatore e ultimi voti), una sola sul telefono.
  return `<div class="cards">
      ${tessera(media(D.media_generale), "media generale")}
      ${tessera(D.voti.length, "voti registrati")}
      ${tessera(insufficienti, "materie sotto il 6", insufficienti ? "bad" : "ok")}
      ${tessera(migliore ? esc(migliore.materia) : "–", migliore ? `materia migliore (${media(migliore.media)})` : "materia migliore")}
    </div>
    <div class="voti-griglia"><div class="voti-colonna">
      ${titolo("Cosa fare adesso")}${azioniVoti()}
      ${titolo("Le tue materie", st.length ? "dalla media più bassa" : "")}${st.length ? `<div class="materie">${st.map(schedaMateria).join("")}</div>` : '<div class="box"><div class="empty">Nessun voto registrato finora.</div></div>'}
    </div><div class="voti-colonna">
      ${titolo("Che voto mi serve?")}${simulatore()}
      ${titolo("Ultimi voti")}${ultimi}
    </div></div>
    <div class="sezioni">
      ${D.consigli.length ? sezione("consigli", "Tutti i consigli", D.consigli.length, listaConsigli(D.consigli)) : ""}
      ${sezione("grafici", "Grafici", 6, grafici)}
      ${tutti.length ? sezione("voti", "Tutti i voti", tutti.length, elenco) : ""}
    </div>`;
}

// Un giorno «pieno»: due verifiche, oppure quattro cose in tutto tra compiti e verifiche.
const giornoPieno = (x) => x.verifiche.length >= 2 || x.verifiche.length + x.compiti.length >= 4;
const maiuscola = (testo) => testo.replace(/^./, (c) => c.toUpperCase());
// Un blocco delle schede a due colonne: sul telefono i blocchi di entrambe le colonne si mettono in fila secondo «ordine».
const blocco = (ordine, html) => (html ? `<div class="blocco" style="order:${ordine}">${html}</div>` : "");

function schedaCarico() {
  const c = D.carico, blu = "var(--series-1)", arancio = "var(--series-2)";
  const impegni = impegniPerGiorno(), nessuno = { verifiche: [], promemoria: [], compiti: [], variazioni: [] };
  const di = (iso) => impegni.get(iso) || nessuno;
  const giorni = Array.from({ length: 14 }, (_, i) => spostaGiorni(D.oggi, i));
  if (!giorni.includes(giornoCarico)) giornoCarico = D.oggi;
  const pieni = giorni.filter((g) => giornoPieno(di(g)));
  const inElenco = D.compiti.length, fattiElenco = D.compiti.filter((x) => fatti.has(x.id)).length;
  const corrente = c.per_settimana.find((s) => s.corrente) || { compiti: 0, verifiche: 0 };
  const questa = corrente.compiti + corrente.verifiche;
  const mediaSett = c.media_compiti_settimana == null ? null : c.media_compiti_settimana + (c.media_verifiche_settimana || 0);
  const scarto = mediaSett == null ? 0 : Math.round(questa - mediaSett);
  const rispetto = mediaSett == null ? "" : `<small class="${scarto > 0 ? "bad" : scarto < 0 ? "ok" : "muted"}">${scarto ? `${scarto > 0 ? "▲" : "▼"} ${Math.abs(scarto)} ${scarto > 0 ? "sopra" : "sotto"} la media` : "come la media"}</small>`;

  const casella = (g) => {
    const x = di(g), d = giorno(g), cose = x.compiti.length + x.verifiche.length;
    const classe = ["giorno-14", g === D.oggi ? "oggi" : "", g === giornoCarico ? "scelto" : "", giornoPieno(x) ? "pieno" : cose ? "con" : ""].filter(Boolean).join(" ");
    const punti = x.compiti.slice(0, 5).map((k) => `<i class="c${fatti.has(k.id) ? " fatto" : ""}"></i>`).join("") + x.verifiche.slice(0, 3).map(() => '<i class="v"></i>').join("");
    return `<button type="button" class="${classe}" data-giorno-carico="${g}" aria-pressed="${g === giornoCarico}"
      aria-label="${esc(`${dataLunga(g)}: ${plurale(x.compiti.length, "compito", "compiti")}, ${plurale(x.verifiche.length, "verifica", "verifiche")}`)}">
      <span>${GIORNI[d.getDay()].slice(0, 3)}</span><b>${d.getDate()}</b><span class="punti-14" aria-hidden="true">${punti}</span></button>`;
  };
  // Una pillola per materia, con «×2» se ce n'è più di una.
  const pillole = (materie, classe) => [...materie.reduce((m, x) => m.set(x, (m.get(x) || 0) + 1), new Map())]
    .map(([m, n]) => `<span class="pillola ${classe}">${esc(m)}${n > 1 ? ` ×${n}` : ""}</span>`).join("");
  const cartaPieno = (g) => {
    const x = di(g), prima = x.verifiche.find((p) => p.materia);
    return `<li><div class="pieno-testa"><strong>${maiuscola(dataLunga(g))}</strong><span class="muted">${quando(g)}</span>
      <span class="tag bad">${[x.verifiche.length ? plurale(x.verifiche.length, "verifica", "verifiche") : "", x.compiti.length ? plurale(x.compiti.length, "compito", "compiti") : ""].filter(Boolean).join(" · ")}</span></div>
      <div class="pillole">${pillole(x.verifiche.map((p) => p.materia || "Verifica"), "v")}${pillole(x.compiti.filter((k) => !fatti.has(k.id)).map((k) => k.materia), "")}${pillole(x.compiti.filter((k) => fatti.has(k.id)).map((k) => k.materia), "fatto")}</div>
      <p class="muted">${prima ? `Consiglio: comincia a preparare ${esc(prima.materia)} già oggi.` : "Consiglio: porta avanti qualche compito nei giorni prima."}</p></li>`;
  };
  const lista = (caricoPer === "docente" ? c.per_docente.map((r) => ({ ...r, nome: r.docente })) : c.per_materia.map((r) => ({ ...r, nome: r.materia })));
  const massimo = Math.max(1, ...lista.map((r) => r.compiti + r.verifiche));
  const provenienza = `<div class="box pad"><div class="segmenti" role="group" aria-label="Raggruppa">
      ${[["materia", "Per materia"], ["docente", "Per docente"]].map(([k, t]) => `<button type="button" class="btn small${caricoPer === k ? "" : " ghost"}" data-carico-per="${k}" aria-pressed="${caricoPer === k}">${t}</button>`).join("")}</div>
    ${lista.length ? `<ul class="provenienza">${(caricoTutte ? lista : lista.slice(0, 5)).map((r) => `<li><div class="prov-testa"><strong>${esc(r.nome)}</strong>
      <span class="muted">${plurale(r.compiti, "compito", "compiti")} · ${plurale(r.verifiche, "verifica", "verifiche")}</span></div>
      <div class="prov-barra" role="img" aria-label="${esc(`${r.nome}: ${r.compiti} compiti e ${r.verifiche} verifiche`)}"><i class="c" style="width:${(r.compiti / massimo) * 100}%"></i><i class="v" style="width:${(r.verifiche / massimo) * 100}%"></i></div></li>`).join("")}</ul>
      ${lista.length > 5 ? `<button type="button" class="link" data-carico-tutte>${caricoTutte ? "Mostra solo le prime 5" : `Mostra tutte (${lista.length}) ›`}</button>` : ""}`
      : '<div class="empty">Ancora niente da contare.</div>'}</div>`;

  const settimane = segnaposto((w) => colonne(w, c.per_settimana.map((s) => ({
    label: dataBreve(s.inizio), valori: [s.compiti, s.verifiche], evid: s.corrente,
    tip: `<b>Settimana del ${dataBreve(s.inizio)}${s.corrente ? " (questa)" : ""}</b><br>${plurale(s.compiti, "compito", "compiti")} · ${plurale(s.verifiche, "verifica", "verifiche")}`,
  })), [blu, arancio], { titolo: "Compiti e verifiche per settimana" }));
  const giorniSettimana = segnaposto((w) => colonne(w, c.per_giorno_settimana.map((g) => ({
    label: g.giorno.slice(0, 3), valori: [g.compiti], tip: `<b>${g.giorno}</b><br>${plurale(g.compiti, "compito", "compiti")} da consegnare`,
  })), [blu], { titolo: "Compiti per giorno di consegna" }));
  const serie = legenda([["Compiti", blu], ["Verifiche", arancio]]);

  // Sul PC: a sinistra i 14 giorni e da dove arriva il lavoro, a destra i giorni pieni e il resto; sul telefono in quest'ordine: 14 giorni, giorni pieni, provenienza, resto.
  return `<div class="cards">
      ${tessera(questa, "compiti e verifiche questa settimana", "", rispetto)}
      ${tessera(mediaSett == null ? "–" : num(Math.round(mediaSett * 10) / 10), "compiti e verifiche a settimana, in media")}
      ${tessera(pieni.length, "giorni pieni nei prossimi 14", pieni.length ? "bad" : "")}
      ${tessera(inElenco ? Math.round((fattiElenco / inElenco) * 100) + "%" : "–", `compiti spuntati (${fattiElenco} su ${inElenco})`, "", inElenco ? barra(fattiElenco / inElenco, "fatti") : "")}
    </div>
    <div class="due-colonne"><div class="colonna">
      ${blocco(1, `${titolo("Prossimi 14 giorni", "tocca un giorno")}<div class="box pad"><div class="quattordici">${giorni.map(casella).join("")}</div>${serie}</div>${giornoScelto(impegni, giornoCarico)}`)}
      ${blocco(3, `${titolo("Da dove arriva il lavoro", "da inizio anno")}${provenienza}`)}
    </div><div class="colonna">
      ${blocco(2, pieni.length ? `${titolo("Giorni pieni in arrivo", plurale(pieni.length, "giorno", "giorni"))}<ul class="pieni">${pieni.map(cartaPieno).join("")}</ul>` : "")}
      ${blocco(4, `<div class="sezioni">
        ${sezione("k-settimane", "Per settimana", "da inizio anno", grafico("Per settimana", "Da inizio anno; in grassetto la settimana in corso.", serie + settimane))}
        ${sezione("k-giorni", "Giorni di consegna", "", grafico("Giorni di consegna", "In quali giorni della settimana cadono più compiti.", giorniSettimana))}
      </div>`)}
    </div></div>`;
}

function schedaAssenze() {
  const a = D.assenze, quota = a.limite_ore ? a.ore_perse / a.limite_ore : 0;
  const livello = quota >= 0.8 ? "bad" : quota >= 0.6 ? "warn" : "ok";
  const nomi = { assenza: "Assenza", ritardo: "Ritardo", uscita: "Uscita anticipata" }, lettere = { assenza: "A", ritardo: "R", uscita: "U" };
  const ore = (e) => (e.ore == null ? "ore non ricavabili" : plurale(e.ore, "ora", "ore"));
  const piene = Math.min(20, Math.round(quota * 20));
  const tacche = barraTacche(Array.from({ length: 20 }, (_, i) => [1, [i < piene ? "si" : "", i >= 16 ? "rossa" : ""].join(" ").trim()]), `${a.ore_perse} ore perse su ${a.limite_ore}`);
  const giorniRimasti = a.ore_al_giorno && a.ore_rimaste > 0 ? Math.floor(a.ore_rimaste / a.ore_al_giorno) : null;
  const previsione = a.previsione == null || !a.ore_perse ? "" : a.previsione <= a.limite_ore
    ? `<p class="previsione ok">Al ritmo di adesso arrivi a fine anno con circa ${a.previsione} ore perse: sotto il limite. ✓</p>`
    : `<p class="previsione bad">Al ritmo di adesso arrivi a fine anno con circa ${a.previsione} ore perse: oltre il limite di ${a.limite_ore}.</p>`;
  const limite = `<div class="box pad limite"><div class="limite-testa"><div>
      <span class="muted">${a.ore_rimaste >= 0 ? "Puoi ancora perdere" : "Hai superato il limite di"}</span>
      <b class="limite-num ${livello}">${grande(plurale(Math.abs(a.ore_rimaste), "ora", "ore"))}</b>
      ${giorniRimasti != null ? `<span class="muted">circa ${plurale(giorniRimasti, "giorno", "giorni")} di scuola</span>` : ""}</div>
      <div class="limite-conto"><b>${a.ore_perse} / ${a.limite_ore}</b><span class="muted">ore perse · ${Math.round(quota * 100)}%</span></div></div>
    ${tacche}<div class="limite-scala"><span>inizio anno</span><span><span class="bad">rosso dall'80%</span> · ${a.limite_ore} h</span></div>
    ${previsione}
    <p class="note">Il limite è il 25% del monte ore annuale, ${a.ore_dall_orario ? `calcolato sulle ${a.ore_settimanali} ore settimanali del tuo orario per 33 settimane` : "stimato in 32 ore per 33 settimane: puoi cambiare la stima in config.py"}. Finora sono state svolte ${a.ore_svolte} ore di lezione${a.percentuale == null ? "" : `: ne hai perse il ${num(a.percentuale)}%`}.
    ${a.eventi_senza_ore ? ` Per ${plurale(a.eventi_senza_ore, "evento", "eventi")} le ore non si possono ricavare dal registro e non sono contate.` : ""}</p></div>`;
  const recenti = a.eventi.slice().reverse();
  const daGiust = recenti.filter((e) => e.da_giustificare);
  const cartaGiust = (e) => `<li><span class="lettera">${lettere[e.tipo]}</span><div><strong>${nomi[e.tipo]} · ${maiuscola(dataLunga(e.data))}</strong>
    <div class="muted">${[esc(e.nota), ore(e)].filter(Boolean).join(" · ")}</div></div></li>`;
  const rigaEvento = (e) => `<li class="${e.tipo}"><span class="lettera" aria-hidden="true">${lettere[e.tipo]}</span><div><strong>${nomi[e.tipo]}</strong>
    <div class="muted">${dataLunga(e.data)} · ${ore(e)}</div></div>${e.da_giustificare ? '<span class="bad">da giustificare</span>' : e.giustificata ? '<span class="ok">giustificata</span>' : ""}</li>`;
  const tabella = `<div class="box"><table><thead><tr><th>Data</th><th>Tipo</th><th class="n">Ore perse</th><th>Stato</th><th>Dettagli</th></tr></thead><tbody>
    ${recenti.map((e) => `<tr><td class="when">${dataLunga(e.data)}</td><td>${nomi[e.tipo]}</td><td class="n">${e.ore == null ? '<span title="Non determinabile dai dati del registro">?</span>' : e.ore}</td>
      <td>${e.da_giustificare ? '<span class="tag bad">da giustificare</span>' : e.giustificata ? "Giustificata" : "—"}</td><td class="muted">${esc(e.nota)}</td></tr>`).join("")}
    </tbody></table></div>`;
  const massimo = Math.max(1, ...a.per_materia.map((r) => r.ore));
  const perMateria = a.per_materia.length ? `<div class="box pad"><ul class="ore-materia">${a.per_materia.map((r) => `<li><span>${esc(r.materia)}</span>
      <div class="prov-barra" role="img" aria-label="${esc(`${r.materia}: ${plurale(r.ore, "ora persa", "ore perse")}`)}"><i class="c" style="width:${(r.ore / massimo) * 100}%"></i></div><b>${r.ore} h</b></li>`).join("")}</ul></div>`
    : '<div class="box"><div class="empty">Nessuna ora persa finora.</div></div>';
  const perMese = a.per_mese.some((m) => m.ore) ? segnaposto((w) => colonne(w, a.per_mese.map((m) => ({ label: mese(m.mese), valori: [m.ore], tip: `<b>${mese(m.mese)}</b><br>${plurale(m.ore, "ora persa", "ore perse")}` })), ["var(--series-1)"], { titolo: "Ore perse per mese" })) : '<p class="muted">Nessuna ora persa finora.</p>';

  // Sul PC: a sinistra limite, numeri e materie; a destra da giustificare, ultimi eventi e il resto. Sul telefono in quest'ordine: limite, numeri, da giustificare, eventi, materie, resto.
  return `<div class="due-colonne assenze"><div class="colonna">
      ${blocco(1, `${titolo("Limite di assenze")}${limite}`)}
      ${blocco(2, `<div class="cards">
        ${tessera(a.ore_perse, "ore di lezione perse")}
        ${tessera(a.giorni_assenza, "giorni di assenza")}
        ${tessera(a.ritardi, "ritardi")}
        ${tessera(a.uscite, "uscite anticipate")}
        ${tessera(a.da_giustificare, "da giustificare", a.da_giustificare ? "bad" : "ok")}
      </div>`)}
      ${blocco(5, `${titolo("Dove hai perso ore")}${perMateria}`)}
    </div><div class="colonna">
      ${blocco(3, daGiust.length ? `${titolo("Da giustificare", daGiust.length)}<ul class="giustificare">${daGiust.map(cartaGiust).join("")}</ul>` : "")}
      ${blocco(4, `${titolo("Ultimi eventi", recenti.length > 4 ? `<button type="button" class="link" data-apri-sezione="as-eventi">tutti (${recenti.length}) ›</button>` : "")}
        ${recenti.length ? `<div class="box"><ul class="eventi-assenze">${recenti.slice(0, 4).map(rigaEvento).join("")}</ul></div>` : '<div class="box"><div class="empty">Nessuna assenza, ritardo o uscita registrati.</div></div>'}`)}
      ${blocco(6, `<div class="sezioni">
        ${sezione("as-mesi", "Ore perse per mese", "", grafico("Per mese", "Ore perse mese per mese.", perMese))}
        ${recenti.length ? sezione("as-eventi", "Tutti gli eventi", recenti.length, tabella) : ""}
      </div>`)}
    </div></div>`;
}

/* ---------- verifiche ---------- */

const verificheFuture = () => D.promemoria.filter((p) => p.verifica && giorniDa(p.data) >= 0);

/* ---------- oggi ---------- */

// Il primo giorno dopo oggi in cui c'è lezione (dall'orario), altrimenti domani saltando la domenica.
function prossimoGiornoDiScuola() {
  const date = [...new Set(lezioniOrario().filter((l) => l.data > D.oggi && l.stato !== "annullata").map((l) => l.data))].sort();
  if (date.length) return date[0];
  let g = spostaGiorni(D.oggi, 1);
  if (giorno(g).getDay() === 0) g = spostaGiorni(g, 1);
  return g;
}

function dettagliLezione(l) {
  return esc([l.aule.length ? "aula " + l.aule.join(", ") : "", l.docenti.join(", ")].filter(Boolean).join(" · "));
}

// Il conto alla rovescia fino a un orario di oggi («−20:00»): lo aggiorna ogni secondo il timer in fondo al file.
function contoGiu(hhmm) {
  const s = Math.max(0, Math.ceil((minuti(hhmm) * 60000 - (Date.now() - new Date().setHours(0, 0, 0, 0))) / 1000));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), due = (n) => String(n).padStart(2, "0");
  return "−" + (h ? `${h}:${due(m)}` : m) + ":" + due(s % 60);
}
const riquadroConto = (hhmm, etichetta) => `<div class="conto-giu"><b data-fine="${hhmm}">${contoGiu(hhmm)}</b><span>${etichetta}</span></div>`;

function riquadroAdesso(lezioni) {
  const adesso = oraDi(new Date());
  const valide = lezioni.filter((l) => l.stato !== "annullata");
  const ora = valide.find((l) => l.inizio <= adesso && adesso < l.fine);
  const dopo = valide.find((l) => l.inizio > adesso && (!ora || l.inizio >= ora.fine));
  const tra = (hhmm) => { const n = minuti(hhmm) - minuti(adesso); return n < 60 ? `tra ${n} min` : `tra ${Math.floor(n / 60)} h ${n % 60 ? (n % 60) + " min" : ""}`.trim(); };
  const quale = (l) => [...new Set(lezioni.map((x) => x.inizio))].sort().indexOf(l.inizio) + 1;
  const dettagli = (l) => `${l.inizio}–${l.fine}${dettagliLezione(l) ? " · " + dettagliLezione(l) : ""}`;
  let corpo;
  if (ora) {
    // Una tacca ogni 5 minuti di lezione: piene quelle passate, a metà quella in corso.
    const durata = Math.max(5, minuti(ora.fine) - minuti(ora.inizio)), passati = minuti(adesso) - minuti(ora.inizio);
    const pezzi = Math.round(durata / 5), pieni = Math.min(pezzi, Math.floor((passati / durata) * pezzi));
    corpo = `<div class="adesso-riga"><div class="adesso-testo"><span class="etichetta">Adesso · ${quale(ora)}ª ora</span><span class="grande">${grande(ora.materia)}</span>
      <span class="muted">${dettagli(ora)}</span></div>${riquadroConto(ora.fine, "alla fine dell'ora")}</div>
      ${barraTacche(Array.from({ length: pezzi }, (_, i) => [1, i < pieni ? "si" : i === pieni ? "ora" : ""]), `Passati ${passati} minuti su ${durata}`)}
      ${dopo ? `<div class="poi"><span class="etichetta">Dopo</span> <strong>${esc(dopo.materia)}</strong> <span class="muted">alle ${dopo.inizio}${dettagliLezione(dopo) ? " · " + dettagliLezione(dopo) : ""}</span></div>` : '<div class="poi muted">È l\'ultima ora di oggi.</div>'}`;
  } else if (dopo) {
    corpo = `<div class="adesso-riga"><div class="adesso-testo"><span class="etichetta">Prossima lezione · ${tra(dopo.inizio)}</span><span class="grande">${grande(dopo.materia)}</span>
      <span class="muted">${dettagli(dopo)}</span></div>${riquadroConto(dopo.inizio, "all'inizio")}</div>`;
  } else {
    const prossimo = prossimoGiornoDiScuola();
    const primo = lezioniOrario().filter((l) => l.data === prossimo && l.stato !== "annullata").sort((a, b) => (a.inizio < b.inizio ? -1 : 1))[0];
    corpo = `<div class="adesso-testo"><span class="etichetta">${valide.length ? "Lezioni finite per oggi" : "Oggi niente lezioni"}</span>
      <span class="grande">${primo ? `${giorniDa(prossimo) === 1 ? "Domani" : dataLunga(prossimo).replace(/^./, (c) => c.toUpperCase())} si entra alle ${primo.inizio}` : "Goditi la pausa"}</span>
      ${primo ? `<span class="muted">prima ora: ${esc(primo.materia)}${dettagliLezione(primo) ? " · " + dettagliLezione(primo) : ""}</span>` : ""}</div>`;
  }
  return `<div class="box pad adesso">${corpo}</div>`;
}

const VARIAZIONI = { supplenza: "supplenze", annullata: "annullate", "cambio aula": "cambi d'aula", spostata: "spostate", aggiuntiva: "aggiuntive" };

// «5 ore · 1 supplenza · 1 annullata»: il riassunto accanto al titolo dell'orario.
function riassuntoGiornata(lezioni) {
  const conti = new Map();
  lezioni.filter((l) => l.variazione).forEach((l) => conti.set(l.stato, (conti.get(l.stato) || 0) + 1));
  return [plurale(new Set(lezioni.map((l) => l.inizio)).size, "ora", "ore"), ...[...conti].map(([s, n]) => `${n} ${n === 1 ? s : VARIAZIONI[s] || s}`)].map(esc).join(" · ");
}

function giornata(lezioni) {
  const adesso = oraDi(new Date());
  return `<div class="box"><ul class="giornata">${lezioni.map((l) => {
    const inCorso = l.inizio <= adesso && adesso < l.fine && l.stato !== "annullata", passata = l.fine <= adesso;
    const classe = [passata ? "passata" : inCorso ? "ora" : "", l.stato === "annullata" ? "annullata" : ""].join(" ");
    const stato = l.variazione ? `<span class="tag${l.nuova || l.stato === "annullata" ? " bad" : ""}">${esc(l.stato)}</span>`
      : inCorso ? `<span class="tag accento">ancora ${minuti(l.fine) - minuti(adesso)}'</span>` : passata ? '<span class="muted fatta">✓ fatta</span>' : "";
    return `<li class="${classe}"><span class="ore">${l.inizio}–${l.fine}</span><div><strong>${esc(l.materia)}</strong>
      <div class="muted">${dettagliLezione(l)}${l.variazione && dettagliVariazione(l) ? " · " + dettagliVariazione(l) : ""}</div></div>${stato}</li>`;
  }).join("")}</ul></div>`;
}

// Un titolo di sezione con, a destra, un riassunto in piccolo.
const titolo = (testo, destra = "") => (destra ? `<h2 class="con-destra">${testo}<span class="h2-destra">${destra}</span></h2>` : `<h2>${testo}</h2>`);

function schedaOggi() {
  const lezioni = lezioniOrario().filter((l) => l.data === D.oggi).sort((a, b) => (a.inizio < b.inizio ? -1 : a.inizio > b.inizio ? 1 : 0));
  const prossimo = prossimoGiornoDiScuola();
  const perOggi = D.compiti.filter((c) => c.consegna === D.oggi && !fatti.has(c.id));
  const perProssimo = D.compiti.filter((c) => c.consegna === prossimo);
  const fattiProssimo = perProssimo.filter((c) => fatti.has(c.id)).length;
  const future = verificheFuture().sort((a, b) => (a.data < b.data ? -1 : 1));
  const verifiche = future.filter((p) => giorniDa(p.data) <= 7);
  const nuoviVoti = D.voti.filter((v) => giorniDa(v.data) >= -3).sort((a, b) => (a.data < b.data ? 1 : -1));
  const conVoto = nuoviVoti.filter((v) => v.valore != null);
  const daFare = D.compiti.filter((c) => giorniDa(c.consegna) >= 0 && !fatti.has(c.id)).length;
  const gg = future.length ? giorniDa(future[0].data) : null;
  const d = giorno(D.oggi);
  const titoloProssimo = giorniDa(prossimo) === 1 ? "Per domani" : `Per ${dataLunga(prossimo)}`;
  // Tre colonne sul PC, una sola sul telefono (in quest'ordine): adesso e orario; compiti; verifiche e voti.
  return `<p class="oggi-data">${GIORNI[d.getDay()]} ${d.getDate()} ${MESI_LUNGHI[d.getMonth()]}</p>
    <div class="cards oggi-numeri">
      ${tessera(daFare, "compiti da fare")}
      ${tessera(verifiche.length, "verifiche nei prossimi 7 giorni")}
      ${tessera(gg == null ? "–" : gg === 0 ? "oggi" : gg === 1 ? "domani" : `${gg} gg`, "alla prossima verifica", gg != null && gg <= 2 ? "bad" : "")}
      ${tessera(media(D.media_generale), "media generale", D.media_generale != null && D.media_generale < D.sufficienza ? "bad" : "")}
    </div>
    <div class="oggi-griglia"><div class="oggi-colonna">
      ${D.orario ? riquadroAdesso(lezioni) : ""}
      ${lezioni.length ? `${titolo("Orario di oggi", riassuntoGiornata(lezioni))}${giornata(lezioni)}` : ""}
    </div><div class="oggi-colonna">
      ${perOggi.length ? `<h2>Da consegnare oggi <span class="tag bad">non spuntati</span></h2>${listaCompiti(perOggi, "")}` : ""}
      ${titolo(titoloProssimo, perProssimo.length ? `${fattiProssimo} di ${perProssimo.length} fatti` : "")}${listaCompiti(perProssimo, "Niente da consegnare.",
        perProssimo.length ? `<div class="box-barra">${barra(fattiProssimo / perProssimo.length, "fatti")}</div>` : "")}
    </div><div class="oggi-colonna">
      ${titolo("Verifiche nei prossimi 7 giorni")}${verifiche.length ? `<div class="box"><ul class="consigli">${verifiche.map((p) => { const n = giorniDa(p.data); return `<li class="${n <= 1 ? "critico" : "attenzione"}">
        <span class="icona conto" aria-hidden="true">${n === 0 ? "<small>oggi</small>" : `<b>${n}</b><small>${n === 1 ? "giorno" : "giorni"}</small>`}</span>
        <div>${puntoNuovo(nuovo("verifiche", chiaveVerifica(p)))}<strong>${esc(p.materia)}</strong> <span class="muted">· ${dataLunga(p.data)}${p.orario ? " · " + esc(p.orario) : ""} · ${quando(p.data)}</span><div class="muted">${esc(p.testo)}</div></div></li>`; }).join("")}</ul></div>`
        : '<div class="box"><div class="empty">Nessuna verifica in vista.</div></div>'}
      ${nuoviVoti.length ? `${titolo("Voti degli ultimi giorni", conVoto.length > 1 ? "media " + num(Math.round((conVoto.reduce((t, v) => t + v.valore, 0) / conVoto.length) * 10) / 10) : "")}
        <div class="cards oggi-voti">${nuoviVoti.map((v) => tessera(esc(v.codice), `${puntoNuovo(nuovo("voti", chiaveVoto(v)))}${esc(v.materia)} · ${dataBreve(v.data)}`, v.valore < D.sufficienza ? "bad" : "ok",
          v.valore == null ? "" : barra(v.valore / 10, v.valore < D.sufficienza ? "basso" : "alto"))).join("")}</div>` : ""}
    </div></div>`;
}

/* ---------- ricerca nei compiti ---------- */

function evidenzia(testo, termini) {
  const car = [...String(testo ?? "")];
  const norm = car.map((c) => piega(c)[0] || c).join("");
  const segnati = new Array(car.length).fill(false);
  termini.forEach((t) => { for (let i = norm.indexOf(t); i >= 0; i = norm.indexOf(t, i + 1)) segnati.fill(true, i, i + t.length); });
  let html = "";
  car.forEach((c, i) => {
    if (segnati[i] && !segnati[i - 1]) html += "<mark>";
    html += esc(c);
    if (segnati[i] && !segnati[i + 1]) html += "</mark>";
  });
  return html;
}

function risultatiRicerca() {
  const termini = piega(ricerca).split(/\s+/).filter(Boolean);
  if (!termini.length) return "";
  const tutti = (D.compiti_anno && D.compiti_anno.length ? D.compiti_anno : D.compiti)
    .filter((c) => { const t = piega(`${c.materia} ${c.testo} ${c.docente}`); return termini.every((x) => t.includes(x)); })
    .sort((a, b) => (a.consegna < b.consegna ? 1 : a.consegna > b.consegna ? -1 : 0));
  const MAX = 80;
  if (!tutti.length) return `<div class="box"><div class="empty">Nessun compito contiene «${esc(ricerca.trim())}».</div></div>`;
  return `<p class="sub" style="margin:0 0 8px">${plurale(tutti.length, "compito trovato", "compiti trovati")}${tutti.length > MAX ? `, mostro i ${MAX} più recenti` : ""}</p>
    <div class="box"><ul class="todo">${tutti.slice(0, MAX).map((c) => `<li class="${fatti.has(c.id) ? "fatto" : ""}"><label>
      <input type="checkbox" data-id="${c.id}" ${fatti.has(c.id) ? "checked" : ""}>
      <span><span class="muted quando-ricerca">${dataLunga(c.consegna)} · ${quando(c.consegna)}</span><strong>${evidenzia(c.materia, termini)}</strong> — ${evidenzia(c.testo, termini)}</span></label></li>`).join("")}</ul></div>`;
}

function aggiornaRicerca() {
  const risultati = $("#risultati-ricerca"), normali = $("#compiti-normali");
  if (!risultati || !normali) return;
  risultati.innerHTML = risultatiRicerca();
  normali.hidden = Boolean(ricerca.trim());
}

/* ---------- testo per Google Calendar ---------- */

const chiaveCalendario = () => `calendario-${(P && P.attivo) || ""}`;
function giaCopiati() { try { return new Set(JSON.parse(localStorage.getItem(chiaveCalendario()) || "[]")); } catch { return new Set(); } }

const calOpz = { verifiche: true, compiti: true, nuovi: true };
let calendarioAperto = false;
let vociMostrate = []; // le voci che sono ora nel riquadro di testo

// Le voci da mettere in calendario: [chiave, data, riga di testo], in ordine di data.
function vociCalendario() {
  const voci = [];
  if (calOpz.verifiche) verificheFuture().forEach((p) => {
    const aula = aulaPromemoria(p);
    voci.push([`v|${p.data}|${p.materia}|${p.testo}`, p.data, `- Verifica di ${p.materia || "?"} — ${dataCompleta(p.data)}${p.orario ? ", " + p.orario : " (tutto il giorno)"}${aula ? ", " + aula.replace(/^Aula/, "aula") : ""}. Dettagli: ${p.testo}`]);
  });
  if (calOpz.compiti) D.compiti.filter((c) => giorniDa(c.consegna) >= 0 && !fatti.has(c.id)).forEach((c) => {
    voci.push([`c|${c.id}`, c.consegna, `- Compito di ${c.materia} — da consegnare ${dataCompleta(c.consegna)} (tutto il giorno): ${c.testo}`]);
  });
  const solo = calOpz.nuovi ? giaCopiati() : new Set();
  return voci.filter(([k]) => !solo.has(k)).sort((a, b) => (a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0));
}

function testoCalendario(voci) {
  if (!voci.length) return "Niente di nuovo da aggiungere al calendario.";
  return `Aggiungi al mio Google Calendar questi impegni di scuola. Crea un evento per ogni riga: se c'è un orario usalo, altrimenti fai un evento di tutto il giorno. Metti la materia nel titolo e il resto nella descrizione.\n\n${voci.map((v) => v[2]).join("\n")}`;
}

function riquadroCalendario() {
  vociMostrate = vociCalendario();
  const opzione = (k, nome) => `<label><input type="checkbox" data-cal="${k}" ${calOpz[k] ? "checked" : ""}> ${nome}</label>`;
  return `<details class="sezione calendario" id="calendario"${calendarioAperto ? " open" : ""}><summary>Copia nel calendario di Google</summary><div class="sezione-corpo">
    <p class="note">Copia il testo e incollalo nell'assistente di Google Calendar (o in Gemini): crea lui gli eventi. Con «Solo le novità» non ti ritrovi doppioni.</p>
    <div class="opzioni">${opzione("verifiche", "Verifiche")}${opzione("compiti", "Compiti")}${opzione("nuovi", "Solo le novità")}</div>
    <textarea id="cal-testo" readonly aria-label="Testo per il calendario">${esc(testoCalendario(vociMostrate))}</textarea>
    <div class="segmenti" style="margin-top:10px"><button type="button" class="btn small" id="cal-copia">Copia</button>
      <button type="button" class="btn ghost small" id="cal-azzera">Dimentica cosa ho già copiato</button></div></div></details>`;
}

function aggiornaCalendario() {
  vociMostrate = vociCalendario();
  if ($("#cal-testo")) $("#cal-testo").value = testoCalendario(vociMostrate);
}

async function copiaCalendario() {
  const area = $("#cal-testo");
  if (!vociMostrate.length) { avviso("Niente di nuovo da copiare: togli «Solo le novità» per ricopiare tutto."); return; }
  try { await navigator.clipboard.writeText(area.value); } catch { area.select(); document.execCommand("copy"); }
  // Il testo resta nel riquadro (se l'incolla non riesce si ricopia), ma la prossima volta queste voci non ricompaiono.
  try { localStorage.setItem(chiaveCalendario(), JSON.stringify([...new Set([...giaCopiati(), ...vociMostrate.map((v) => v[0])])].slice(-500))); } catch {}
  const b = $("#cal-copia");
  b.textContent = "Copiato ✓";
  setTimeout(() => { if ($("#cal-copia")) $("#cal-copia").textContent = "Copia"; }, 2000);
}

const CONTENUTO = { oggi: schedaOggi, agenda: schedaAgenda, compiti: schedaCompiti, orario: schedaOrario, voti: schedaVoti, carico: schedaCarico, assenze: schedaAssenze };

/* ---------- disegno e interazione ---------- */

function mostra() {
  document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === scheda));
  SCHEDE.forEach((s) => { $(`#tab-${s}`).hidden = s !== scheda; });
  if (!D || D.vuoto) return;
  contatoriSchede();
  if ($("#ultra-zero")) $("#ultra-zero").textContent = sloganUltra(); // una spunta può azzerare gli arretrati
  const attivo = document.activeElement, chiave = attivo && (attivo.dataset.id ? `[data-id="${attivo.dataset.id}"]` : attivo.id ? `#${attivo.id}` : "");
  const pannello = $(`#tab-${scheda}`);
  daDisegnare = [];
  const scartate = Object.values(D.scartate || {}).reduce((a, b) => a + b, 0);
  pannello.innerHTML = CONTENUTO[scheda]() + (scartate ? `<p class="note">${plurale(scartate, "voce del registro aveva", "voci del registro avevano")} un formato inatteso e non ${scartate === 1 ? "è stata considerata" : "sono state considerate"}.</p>` : "");
  disegna(pannello);
  pannello.querySelectorAll("[data-ultimo]").forEach((el) => { el.scrollLeft = el.scrollWidth; }); // la mappa parte dai giorni più recenti
  if (chiave && pannello.querySelector(chiave)) pannello.querySelector(chiave).focus();
}

function applica(dati) {
  D = dati;
  fatti = new Set(Object.keys(dati.stato.fatti));
  if (D.vuoto) {
    impostaTitolo(D.profilo ? D.profilo.nome : "Zaino");
    $("#aggiornato").textContent = "Nessun dato ancora scaricato.";
    SCHEDE.forEach((s) => { $(`#tab-${s}`).innerHTML = ""; });
    return;
  }
  caricaVisti();
  impostaTitolo("Zaino", D.studente ? "di " + D.studente : "");
  const t = new Date(D.scaricato);
  $("#aggiornato").textContent = `${D.classe ? "Classe " + D.classe + " · " : ""}aggiornato ${quando(D.scaricato) === "oggi" ? "oggi" : "il " + dataBreve(D.scaricato)} alle ${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}`;
  mostra();
}

const datiVecchi = () => !D || D.vuoto || (Date.now() - new Date(D.scaricato)) / 60000 > MINUTI_VALIDITA;

async function aggiorna() {
  const bottone = $("#aggiorna");
  if (bottone.disabled) return; // un aggiornamento è già in corso
  bottone.disabled = true;
  // Col tema «Nothing» al posto della scritta tre puntini fanno da scanner (style.css); il testo resta per i lettori di schermo.
  bottone.innerHTML = '<span class="scan" aria-hidden="true"><i></i><i></i><i></i></span><span class="testo-scan">Aggiorno…</span>';
  $("#apri-profili").disabled = true; // niente cambio di profilo a metà download
  const profilo = P && P.attivo;
  try {
    const dati = await api("/api/aggiorna", {});
    if (P && P.attivo === profilo) { applica(dati); avviso(dati.avviso || ""); }
  } catch (errore) {
    avviso(`Aggiornamento non riuscito: ${errore.message}${D && !D.vuoto ? " Stai vedendo gli ultimi dati salvati." : ""}`, true);
  }
  bottone.disabled = false;
  $("#apri-profili").disabled = false;
  bottone.textContent = "Aggiorna";
  sincronizza();
}

/* ---------- profili ---------- */

let P = null; // {profili, attivo, ultimo, registri, android, versione}
let S = null; // stato della sincronizzazione PC ↔ telefono; null = non disponibile
let panoramica = null; // carte della panoramica; null = si vede l'elenco dei profili
let modulo = null; // profilo in creazione o modifica; null = elenco dei profili
let scuoleTrovate = null;

function schermo(profili) {
  $("#profili").hidden = !profili;
  $("#app").hidden = profili;
  $("#aggiorna").hidden = profili;
  $("#apri-profili").hidden = profili || !P;
  if (profili) {
    impostaTitolo("Zaino");
    $("#aggiornato").textContent = P && P.profili.length ? "Scegli con quale profilo entrare." : "Per iniziare crea il tuo profilo.";
    disegnaProfili();
  }
}

function nuovoModulo(profilo) {
  const u = (profilo && profilo.untis) || {};
  scuoleTrovate = null;
  return { id: profilo ? profilo.id : null, registro: profilo ? profilo.registro : "", nome: profilo ? profilo.nome : "", scuola: profilo ? profilo.scuola : "",
    utente: profilo ? profilo.utente : "", studente: (profilo && profilo.studente) || "", password: "", untisServer: u.server || "", untisScuola: u.scuola || "", untisClasse: u.classe || "", cerca: "" };
}

// Copia nel modulo ciò che è stato scritto finora, così ridisegnare la pagina non cancella nulla.
function leggiModulo() {
  const f = $("#modulo-profilo");
  if (!f || !modulo) return;
  ["nome", "scuola", "utente", "studente", "password", "untisClasse", "cerca"].forEach((c) => { if (f.elements[c]) modulo[c] = f.elements[c].value; });
  const scelto = f.querySelector('input[name="registro"]:checked');
  if (scelto) modulo.registro = scelto.value;
}

const interruttoreVista = () => `<div class="segmenti" style="margin-top:16px"><button type="button" class="btn small${panoramica ? " ghost" : ""}" data-vista="profili">Profili</button>
  <button type="button" class="btn small${panoramica ? "" : " ghost"}" data-vista="panoramica">Panoramica</button></div>`;

function vistaPanoramica() {
  const carta = (c) => {
    if (c.vuoto) return `<div class="profilo"><span class="tag">${esc(P.registri[c.registro] || c.registro)}</span><h3>${esc(c.nome)}</h3>
      <p class="muted">Nessun dato ancora scaricato.</p><button type="button" class="btn small" data-entra="${c.id}">Apri</button></div>`;
    const oggi = new Date().toISOString().slice(0, 10), t = new Date(c.scaricato);
    const elenco = (titolo, voci, riga) => voci.length ? `<p><strong>${titolo}</strong></p><ul>${voci.map((v) => `<li>${riga(v)}</li>`).join("")}</ul>` : "";
    const quandoIso = (iso) => { const n = Math.round((giorno(iso) - giorno(oggi)) / 864e5); return n === 0 ? "oggi" : n === 1 ? "domani" : dataBreve(iso); };
    return `<div class="profilo"><span class="tag">${esc(c.classe || (P.registri[c.registro] || ""))}</span>
      <h3>${esc(c.studente || c.nome)}</h3>
      <p>Media generale: <strong>${media(c.media_generale)}</strong>${c.insufficienti.length ? ` <span class="tag bad">${plurale(c.insufficienti.length, "insufficienza", "insufficienze")}</span>` : ""}</p>
      ${c.insufficienti.length ? `<p class="muted">${c.insufficienti.map((i) => `${esc(i.materia)} ${media(i.media)}`).join(" · ")}</p>` : ""}
      ${elenco("Verifiche in arrivo", c.verifiche, (v) => `${quandoIso(v.data)} · ${esc(v.materia)}`)}
      ${elenco("Compiti da fare", c.compiti, (v) => `${quandoIso(v.consegna)} · ${esc(v.materia)}`)}
      ${elenco("Ultimi voti", c.ultimi_voti, (v) => `${num(v.valore)} · ${esc(v.materia)} <span class="muted">(${dataBreve(v.data)})</span>`)}
      <p class="muted">Aggiornato ${dataBreve(c.scaricato)} alle ${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}</p>
      <button type="button" class="btn small" data-entra="${c.id}">Apri il registro</button></div>`;
  };
  return `${interruttoreVista()}<div class="profili">${panoramica.map(carta).join("")}</div>`;
}

async function mostraVista(nome) {
  try {
    panoramica = nome === "panoramica" ? (await api("/api/panoramica")).profili : null;
    try { localStorage.setItem("vista", nome); } catch {}
  } catch (errore) { avviso(errore.message, true); }
  disegnaProfili();
}

/* ---------- aggiornamenti ---------- */

let A = null; // {disponibile, versione, nuova: {versione, pagina}, installabile, exe, automatico, controllato, errore}
let installando = null; // la versione che si sta installando

// «Più tardi» rimanda l'avviso di quella versione fino a domani.
const chiaveRimandato = () => `aggiornamento-rimandato-${A.nuova.versione}`;
function rimandato() {
  try { return localStorage.getItem(chiaveRimandato()) === new Date().toISOString().slice(0, 10); } catch { return false; }
}

function bottoneAggiorna(piccolo) {
  if (installando) return `<button type="button" class="btn${piccolo ? " small" : ""}" disabled>Aggiorno a ${esc(installando)}…</button>`;
  return A.installabile
    ? `<button type="button" class="btn${piccolo ? " small" : ""}" data-aggiornamento="installa">Aggiorna ora</button>`
    : `<a class="btn${piccolo ? " small" : ""}" href="${esc(A.nuova.pagina)}" target="_blank" rel="noopener">Scarica dalla pagina delle Release</a>`;
}

// L'avviso in alto: compare solo se c'è una versione nuova; non scarica niente finché non lo chiedi.
function disegnaAvvisoAggiornamento() {
  const el = $("#aggiornamento");
  const mostra = A && A.disponibile && A.nuova && (installando || !rimandato());
  el.hidden = !mostra;
  if (!mostra) return;
  el.innerHTML = installando
    ? `<span>Scarico e installo Zaino ${esc(installando)}: tra qualche secondo l'app si riapre da sola.</span>`
    : `<span>È disponibile <strong>Zaino ${esc(A.nuova.versione)}</strong> (hai la ${esc(A.versione)}). <a href="${esc(A.nuova.pagina)}" target="_blank" rel="noopener">Cosa cambia</a></span>
      ${bottoneAggiorna(true)}<button type="button" class="btn ghost small" data-aggiornamento="dopo">Più tardi</button>`;
}

function riquadroAggiornamenti() {
  if (!A || !A.disponibile) return "";
  const quando = A.controllato ? `Ultimo controllo: ${oraBreve(A.controllato)}.` : "Non ancora controllato.";
  const stato = A.nuova ? `<p>È disponibile <strong>Zaino ${esc(A.nuova.versione)}</strong>. <a href="${esc(A.nuova.pagina)}" target="_blank" rel="noopener">Cosa cambia</a></p>`
    : `<p>Hai l'ultima versione: <strong>Zaino ${esc(A.versione)}</strong>.</p>`;
  return `<div class="box pad modulo"><h2>Aggiornamenti</h2>${stato}
    <p class="muted">${A.errore ? esc(A.errore) : quando}${A.nuova && !A.exe ? " Scarica la versione nuova e mettila al posto di questa cartella: profili e dati restano." : ""}</p>
    <label class="interruttore"><input type="checkbox" data-aggiornamento="automatico"${A.automatico ? " checked" : ""}> Controlla da solo una volta al giorno (chiede sempre prima di scaricare)</label>
    <div class="segmenti">${A.nuova ? bottoneAggiorna(true) : ""}<button type="button" class="btn ghost small" data-aggiornamento="controlla">Controlla ora</button></div></div>`;
}

function ridisegnaAggiornamenti() {
  disegnaAvvisoAggiornamento();
  if (!$("#profili").hidden) { leggiModulo(); disegnaProfili(); }
}

async function comandoAggiornamento(azione, el) {
  if (azione === "dopo") {
    try { localStorage.setItem(chiaveRimandato(), new Date().toISOString().slice(0, 10)); } catch {}
    return disegnaAvvisoAggiornamento();
  }
  if (azione === "controlla") { el.disabled = true; el.textContent = "Controllo…"; }
  try {
    if (azione === "installa") {
      installando = A.nuova.versione;
      ridisegnaAggiornamenti();
      await api("/api/aggiornamenti", { azione });
      return attendiVersioneNuova();
    }
    A = await api("/api/aggiornamenti", azione === "automatico" ? { azione, attivo: el.checked } : { azione });
    avviso(azione === "controlla" && !A.errore && !A.nuova ? `Hai già l'ultima versione (${A.versione}).` : "");
  } catch (errore) {
    installando = null;
    avviso(errore.message, true);
  }
  ridisegnaAggiornamenti();
}

// L'app vecchia si chiude e parte quella nuova: appena risponde, la pagina si ricarica.
async function attendiVersioneNuova() {
  for (let i = 0; i < 60; i++) {
    await new Promise((fatto) => setTimeout(fatto, 1500));
    try {
      const stato = await api("/api/aggiornamenti");
      if (stato.versione === installando) { location.reload(); return; }
    } catch {}
  }
  installando = null;
  avviso("L'aggiornamento non è ripartito da solo: chiudi la finestra di Zaino e riaprilo.", true);
  ridisegnaAggiornamenti();
}

/* ---------- sincronizzazione PC ↔ telefono ---------- */

const oraBreve = (iso) => { const t = new Date(iso); return `${dataBreve(iso)} alle ${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}`; };

function riquadroSync() {
  if (!S || !S.disponibile) return "";
  const ultima = S.ultima ? `Ultima sincronizzazione: ${oraBreve(S.ultima)}.` : "Non ancora sincronizzato.";
  let corpo;
  if (S.ruolo === "pc") {
    corpo = S.attiva
      ? `<p>Codice di abbinamento: <strong class="codice">${esc(S.codice)}</strong></p>
        <p class="muted">Scrivilo una volta nell'app sul telefono. Da lì in poi i due si allineano da soli quando sono sullo stesso Wi‑Fi e questa app è aperta.</p>
        <p class="muted">${S.in_ascolto ? ultima : "Per iniziare ad ascoltare il telefono chiudi e riapri l'app."}${S.indirizzo ? ` Indirizzo di questo PC: <strong>${esc(S.indirizzo)}</strong>.` : ""}</p>
        <p class="note">Chi conosce il codice e si trova sulla tua rete può leggere i tuoi dati: non condividerlo. Se Windows chiede il permesso per Python, consentilo sulle reti private.</p>
        <div class="segmenti"><button type="button" class="btn ghost small" data-sync="disattiva">Disattiva</button></div>`
      : `<p class="muted">Tiene uguali profili, password, dati scaricati e compiti spuntati tra questo PC e l'app Android, quando sono sullo stesso Wi‑Fi. Niente passa da Internet.</p>
        <div class="segmenti"><button type="button" class="btn small" data-sync="attiva">Attiva</button></div>`;
  } else {
    corpo = S.attiva
      ? `<p>${esc(S.esito || ultima)}</p><p class="muted">${ultima}${S.pc ? ` PC: ${esc(S.pc)}.` : ""}</p>
        <div class="segmenti"><button type="button" class="btn small" data-sync="ora">Sincronizza ora</button>
          <button type="button" class="btn ghost small" data-sync="disattiva">Scollega</button></div>`
      : `<p class="muted">Porta qui profili, password, dati e compiti spuntati del PC, e li tiene uguali quando siete sullo stesso Wi‑Fi. Sul PC apri Profili → Sincronizzazione → Attiva e copia qui il codice.</p>
        <label>Codice di abbinamento<input id="sync-codice" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="ABCDE-FGHIJ-KLMNO-PQRST"></label>
        <label>Indirizzo del PC (facoltativo: serve solo se non viene trovato da solo)<input id="sync-indirizzo" inputmode="decimal" autocomplete="off" placeholder="Es. 192.168.1.20"></label>
        <div class="segmenti"><button type="button" class="btn small" data-sync="abbina">Abbina e sincronizza</button></div>`;
  }
  return `<div class="box pad modulo"><h2>Sincronizzazione con ${S.ruolo === "pc" ? "il telefono" : "il PC"}</h2>${corpo}</div>`;
}

// Rilegge tutto dal server dopo che una sincronizzazione ha cambiato i dati.
async function ricarica() {
  P = await api("/api/profili");
  if (!$("#app").hidden) {
    if (P.attivo) return applica(await api("/api/dati"));
    D = null; modulo = null; panoramica = null; // il profilo aperto è stato eliminato dall'altro dispositivo
    return schermo(true);
  }
  if (panoramica) panoramica = (await api("/api/panoramica")).profili;
  leggiModulo();
  if (modulo && !modulo.id && !modulo.nome && !modulo.utente && P.profili.length) modulo = null; // il modulo vuoto del primo avvio non serve più
  disegnaProfili();
}

function ridisegnaSync() {
  if ($("#profili").hidden) return;
  // Chi sta scrivendo il codice non deve vederselo cancellare da un ridisegno.
  if (document.activeElement && ["sync-codice", "sync-indirizzo"].includes(document.activeElement.id)) return;
  leggiModulo();
  disegnaProfili();
}

// Il telefono cerca il PC e scambia i dati; se il PC non c'è non succede nulla.
async function sincronizza() {
  if (!P || !P.android || !S || !S.attiva) return;
  try {
    S = await api("/api/sincronizzazione", { azione: "ora" });
    if (S.cambiato) await ricarica(); else ridisegnaSync();
  } catch {}
}

// Il PC si accorge che il telefono ha portato novità.
async function controllaSync() {
  if (!P || P.android || !S || !S.attiva || document.hidden) return;
  try {
    const nuovo = await api("/api/sincronizzazione"), cambiato = nuovo.revisione !== S.revisione, diverso = nuovo.ultima !== S.ultima;
    S = nuovo;
    if (cambiato) await ricarica(); else if (diverso) ridisegnaSync();
  } catch {}
}

async function comandoSync(azione) {
  const corpo = { azione };
  if (azione === "abbina") { corpo.codice = $("#sync-codice").value; corpo.indirizzo = $("#sync-indirizzo").value; }
  if (azione === "disattiva" && !confirm(S.ruolo === "pc" ? "Disattivare la sincronizzazione? Il telefono andrà abbinato di nuovo, con un altro codice." : "Scollegare questo telefono dal PC? I dati già arrivati restano.")) return;
  const bottone = document.querySelector(`[data-sync="${azione}"]`);
  if (bottone) { bottone.disabled = true; if (azione !== "disattiva") bottone.textContent = azione === "attiva" ? "Attivo…" : "Cerco il PC…"; }
  try {
    S = await api("/api/sincronizzazione", corpo);
    avviso(S.trovato === false || S.errore ? S.esito : "", true);
    if (S.cambiato) await ricarica(); else { leggiModulo(); disegnaProfili(); }
  } catch (errore) {
    avviso(errore.message, true);
    if (bottone) { bottone.disabled = false; bottone.textContent = { attiva: "Attiva", abbina: "Abbina e sincronizza", ora: "Sincronizza ora" }[azione] || bottone.textContent; }
  }
}

function disegnaProfili() {
  const el = $("#profili");
  if (!P) { el.innerHTML = ""; return; }
  if (!modulo && !P.profili.length) modulo = nuovoModulo(null);
  $("#aggiornato").textContent = modulo ? (P.profili.length ? "Compila i dati del profilo." : "Per iniziare crea il tuo profilo.") : "Scegli con quale profilo entrare.";
  if (!modulo && panoramica) { el.innerHTML = vistaPanoramica(); return; }
  if (!modulo) {
    el.innerHTML = `${P.profili.length > 1 ? interruttoreVista() : ""}<div class="profili">${P.profili.map((p) => `<div class="profilo">
        <span class="tag">${esc(P.registri[p.registro] || p.registro)}</span>
        <h3>${esc(p.nome)}</h3>
        <p class="muted">${esc(p.utente)}${p.untis ? ` · orario ${esc(p.untis.classe)}` : ""}</p>
        <div class="segmenti"><button type="button" class="btn small" data-entra="${p.id}">Entra</button>
          <button type="button" class="btn ghost small" data-modifica="${p.id}">Modifica</button>
          <button type="button" class="btn ghost small" data-elimina="${p.id}">Elimina</button></div></div>`).join("")}
      <button type="button" class="profilo nuovo" data-nuovo="1">+ Nuovo profilo</button></div>${riquadroSync()}${riquadroAggiornamenti()}${firma()}`;
    return;
  }
  const m = modulo, registro = (valore, nome, nota) => `<label class="scelta${m.registro === valore ? " attiva" : ""}"><input type="radio" name="registro" value="${valore}" ${m.registro === valore ? "checked" : ""} required>
    <span><strong>${nome}</strong><small>${nota}</small></span></label>`;
  const campo = (nome, etichetta, extra = "") => `<label>${etichetta}<input name="${nome}" value="${esc(m[nome])}" ${extra}></label>`;
  el.innerHTML = `<form id="modulo-profilo" class="box pad modulo" autocomplete="off">
      <h2>${m.id ? "Modifica profilo" : "Nuovo profilo"}</h2>
      <fieldset><legend>1. Che registro usa la tua scuola?</legend>
        <div class="scelte">${registro("argo", "Argo didUP", "portaleargo.it")}${registro("nuvola", "Nuvola", "nuvola.madisoft.it · studenti e tutori")}${registro("classeviva", "ClasseViva", "Spaggiari · sperimentale")}</div></fieldset>
      <fieldset><legend>2. Dati di accesso al registro</legend>
        ${campo("nome", "Nome del profilo", 'required maxlength="40" placeholder="Es. Mario"')}
        ${m.registro === "argo" ? campo("scuola", "Codice scuola", 'required placeholder="Lo stesso che scrivi su didUP"') : ""}
        ${campo("utente", "Nome utente", m.registro === "classeviva" ? 'required placeholder="Codice tipo S1234567X oppure email"' : "required")}
        ${sceltaStudente(m)}
        <label>Password<input name="password" type="password" value="${esc(m.password)}" ${m.id ? 'placeholder="Lascia vuoto per non cambiarla"' : "required"} autocomplete="new-password"></label>
        ${m.registro === "classeviva" ? '<p class="note">ClasseViva è appena arrivato e non è ancora stato provato su molti account: se qualcosa non torna, segnalalo nelle issue del progetto su GitHub.</p>' : ""}
        <p class="note">${P.android ? "Tutto resta su questo telefono: la password è cifrata e viene inviata solo al registro scelto, a nessun altro server." : "Tutto resta su questo computer: la password sta nel portachiavi del sistema (su Windows il Gestione credenziali) e viene inviata solo al registro scelto, a nessun altro server."}</p></fieldset>
      <fieldset><legend>3. Orario WebUntis <span class="muted">(facoltativo)</span></legend>
        ${m.untisServer ? `<p>Scuola: <strong>${esc(m.untisScuola)}</strong> <span class="muted">(${esc(m.untisServer)})</span> <button type="button" class="btn ghost small" data-togli-untis="1">Togli</button></p>
          ${campo("untisClasse", "Classe, come compare su WebUntis", 'placeholder="Es. 3A"')}`
        : `<div class="riga">${campo("cerca", "Cerca la scuola per nome", 'placeholder="Almeno 3 lettere"')}<button type="button" class="btn ghost" id="cerca-untis">Cerca</button></div>
          ${scuoleTrovate === null ? "" : scuoleTrovate.length ? `<ul class="scuole">${scuoleTrovate.map((s, i) => `<li><button type="button" data-scuola-untis="${i}"><strong>${esc(s.nome)}</strong><span class="muted">${esc(s.indirizzo || "")}</span></button></li>`).join("")}</ul>`
            : '<p class="muted">Nessuna scuola trovata (oppure troppe: scrivi un nome più preciso).</p>'}`}</fieldset>
      <div class="segmenti"><button class="btn" type="submit">${m.id ? "Salva" : "Salva ed entra"}</button>
        ${P.profili.length ? '<button class="btn ghost" type="button" id="annulla-profilo">Annulla</button>' : ""}</div>
    </form>${P.profili.length ? "" : riquadroSync() + riquadroAggiornamenti() + firma()}`;
}

// ClasseViva, account con più studenti (per esempio un genitore con due figli): l'elenco arriva dopo il primo «Aggiorna».
function sceltaStudente(m) {
  const studenti = (m.registro === "classeviva" && m.id && P.studenti && P.studenti[m.id]) || [];
  if (studenti.length < 2) return "";
  const scelto = studenti.some((s) => s.ident === m.studente) ? m.studente : studenti[0].ident;
  return `<label>Studente da mostrare<select name="studente">${studenti.map((s) =>
    `<option value="${esc(s.ident)}"${s.ident === scelto ? " selected" : ""}>${esc(s.name || s.ident)}</option>`).join("")}</select></label>`;
}

async function entra(id) {
  avviso("");
  try {
    P = await api("/api/profili/attiva", { id });
    applica(await api("/api/dati"));
  } catch (errore) {
    avviso(errore.message, true);
    return;
  }
  simulati = []; simVoto = null; settimanaOrario = 0; oraOrario = null; materiaGrafico = ""; meseAgenda = 0; giornoAgenda = null; settimanaCompitiScelta = 0; giornoCompiti = null; giornoCarico = null; caricoPer = "materia"; caricoTutte = false;
  schermo(false);
  mostra();
  await sincronizza(); // se il PC ha dati più freschi, sul telefono non serve riscaricarli
  if (P.attivo === id && datiVecchi()) aggiorna();
}

function firma() {
  return `<p class="muted versione">Zaino ${esc(P.versione || "")} · 100% locale: i dati restano su questo dispositivo.</p>`;
}

async function apriProfili() {
  segnaVisti(scheda);
  try { P = await api("/api/profili/attiva", { id: null }); } catch (errore) { avviso(errore.message, true); return; }
  D = null; modulo = null; panoramica = null;
  avviso("");
  schermo(true);
  if (P.profili.length > 1) { try { if (localStorage.getItem("vista") === "panoramica") await mostraVista("panoramica"); } catch {} }
}

async function salvaProfilo() {
  leggiModulo();
  const m = modulo, untis = m.untisServer ? { server: m.untisServer, scuola: m.untisScuola, classe: m.untisClasse } : null;
  try {
    const esito = await api("/api/profili", { id: m.id, profilo: { nome: m.nome, registro: m.registro, scuola: m.scuola, utente: m.utente, studente: m.studente, password: m.password, untis } });
    P = esito; modulo = null; avviso("");
    if (m.id) disegnaProfili(); else await entra(esito.salvato);
  } catch (errore) {
    avviso(errore.message, true);
  }
}

async function eliminaProfilo(id) {
  const p = P.profili.find((x) => x.id === id);
  if (!p || !confirm(`Eliminare il profilo «${p.nome}»?\nVengono cancellati credenziali, dati scaricati e compiti spuntati di questo profilo.`)) return;
  try { P = await api("/api/profili/elimina", { id }); disegnaProfili(); } catch (errore) { avviso(errore.message, true); }
}

async function cercaScuole() {
  leggiModulo();
  if (modulo.cerca.trim().length < 3) { avviso("Scrivi almeno 3 lettere del nome della scuola.", true); return; }
  try {
    scuoleTrovate = (await api("/api/untis/scuole?q=" + encodeURIComponent(modulo.cerca.trim()))).scuole;
    avviso("");
  } catch (errore) { avviso(errore.message, true); }
  disegnaProfili();
}

document.addEventListener("submit", (e) => { if (e.target.id === "modulo-profilo") { e.preventDefault(); salvaProfilo(); } });
document.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.name === "cerca") { e.preventDefault(); cercaScuole(); } });

let attesaSync;

async function spunta(id, fatto) {
  fatto ? fatti.add(id) : fatti.delete(id);
  mostra();
  try {
    await api("/api/stato", { id, fatto });
    clearTimeout(attesaSync);
    attesaSync = setTimeout(sincronizza, 3000);
  } catch (errore) {
    fatto ? fatti.delete(id) : fatti.add(id);
    mostra();
    avviso(`Non sono riuscito a salvare la spunta: ${errore.message}`, true);
  }
}

document.addEventListener("change", (e) => {
  const el = e.target;
  if (el.dataset.id) spunta(el.dataset.id, el.checked);
  else if (el.id === "nascondi") { nascondiFatti = el.checked; mostra(); }
  else if (el.id === "materia-grafico") { materiaGrafico = el.value; mostra(); }
  else if (el.id === "sim-voto") { const v = parseFloat(el.value.replace(",", ".")); if (v >= 1 && v <= 10) { simVoto = v; mostra(); } }
  else if (el.name === "registro") { leggiModulo(); disegnaProfili(); }
  else if (el.dataset.cal) { calOpz[el.dataset.cal] = el.checked; aggiornaCalendario(); }
  else if (el.dataset.aggiornamento === "automatico") comandoAggiornamento("automatico", el);
  else if (el.id === "tema") {
    temaScelto = applicaTema(el.value);
    try { localStorage.setItem("tema", temaScelto); } catch {}
    impostaTitolo(...titoloAttuale);
    if (!$("#app").hidden) mostra(); // le scritte a punti del tema «Nothing» vanno messe o tolte
    comunicaTema();
  }
});

document.addEventListener("input", (e) => {
  if (e.target.id === "cerca-compiti") { ricerca = e.target.value; aggiornaRicerca(); }
});
document.addEventListener("toggle", (e) => {
  if (e.target.id === "calendario") calendarioAperto = e.target.open;
  const nome = e.target.dataset && e.target.dataset.sezione;
  if (!nome || sezioniAperte.has(nome) === e.target.open) return; // anche il ridisegno con «open» fa scattare l'evento
  if (e.target.open) sezioniAperte.add(nome); else sezioniAperte.delete(nome);
  if (e.target.open && e.target.querySelector("[data-svg]")) mostra(); // da chiusi i grafici erano stati disegnati senza larghezza
}, true);

document.addEventListener("click", (e) => {
  const el = e.target.closest("button");
  if (!el) return;
  if (el.dataset.tab) {
    if (el.dataset.tab !== scheda) segnaVisti(scheda); // le novità della scheda che lasci ora le hai viste
    scheda = el.dataset.tab;
    try { localStorage.setItem("scheda", scheda); } catch {}
    mostra();
  }
  else if (el.id === "aggiorna") aggiorna();
  else if (el.dataset.settimana) { settimanaOrario = +el.dataset.settimana; oraOrario = null; mostra(); }
  else if (el.dataset.cella) { oraOrario = el.dataset.cella; mostra(); }
  else if (el.dataset.dividi !== undefined) dividiOra(el.dataset.dividi, el.dataset.materia);
  else if (el.dataset.aggiungiOra) aggiungiOra(+el.dataset.aggiungiOra);
  else if (el.dataset.togliOra) { leggiEditorOrario(); editorOrario.splice(+el.dataset.togliOra, 1); mostra(); }
  else if (el.dataset.copiaGiorno) { const [da, a] = el.dataset.copiaGiorno.split("|").map(Number); copiaGiorno(da, a); }
  else if (el.dataset.orarioAzione === "apri") apriEditorOrario();
  else if (el.dataset.orarioAzione === "annulla") { editorOrario = null; avviso(""); mostra(); }
  else if (el.dataset.orarioAzione === "salva") { leggiEditorOrario(); salvaOrario(editorOrario.filter((o) => o.materia)); }
  else if (el.dataset.orarioAzione === "cancella") { if (confirm("Cancellare tutto l'orario scritto a mano?")) salvaOrario([]); }
  else if (el.dataset.sim) {
    const daFuori = !el.closest("#simulatore"); // dalle schede o da «Cosa fare»: si scende fino al simulatore
    simMateria = el.dataset.sim; simVoto = null; mostra();
    if (daFuori) $("#simulatore")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  else if (el.dataset.giorno) { giornoAgenda = el.dataset.giorno; mostra(); }
  else if (el.dataset.giornoCarico) { giornoCarico = el.dataset.giornoCarico; mostra(); }
  else if (el.dataset.caricoPer) { caricoPer = el.dataset.caricoPer; mostra(); }
  else if (el.hasAttribute("data-carico-tutte")) { caricoTutte = !caricoTutte; mostra(); }
  else if (el.dataset.apriSezione) {
    sezioniAperte.add(el.dataset.apriSezione); mostra();
    document.querySelector(`[data-sezione="${el.dataset.apriSezione}"]`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  else if (el.dataset.giornoCompiti) { giornoCompiti = el.dataset.giornoCompiti; mostra(); }
  else if (el.dataset.settCompiti) { settimanaCompitiScelta = +el.dataset.settCompiti ? settimanaCompitiScelta + +el.dataset.settCompiti : 0; giornoCompiti = null; mostra(); }
  else if (el.dataset.mese) {
    meseAgenda = +el.dataset.mese ? meseAgenda + +el.dataset.mese : 0;
    if (!meseAgenda) giornoAgenda = D.oggi;
    mostra();
  }
  else if (el.dataset.simVoto) { simVoto = +el.dataset.simVoto; mostra(); }
  else if (el.id === "sim-aggiungi") { if (simVoto != null) { simulati.push({ materia: simMateria, voto: simVoto }); simVoto = null; mostra(); } }
  else if (el.id === "sim-azzera") { simulati = []; simVoto = null; mostra(); }
  else if (el.dataset.togli) { simulati.splice(+el.dataset.togli, 1); mostra(); }
  else if (el.id === "apri-profili") apriProfili();
  else if (el.dataset.sync) comandoSync(el.dataset.sync);
  else if (el.dataset.aggiornamento && el.dataset.aggiornamento !== "automatico") comandoAggiornamento(el.dataset.aggiornamento, el);
  else if (el.dataset.vista) mostraVista(el.dataset.vista);
  else if (el.dataset.entra) entra(el.dataset.entra);
  else if (el.dataset.nuovo) { modulo = nuovoModulo(null); avviso(""); disegnaProfili(); }
  else if (el.dataset.modifica) { modulo = nuovoModulo(P.profili.find((p) => p.id === el.dataset.modifica)); avviso(""); disegnaProfili(); }
  else if (el.dataset.elimina) eliminaProfilo(el.dataset.elimina);
  else if (el.id === "annulla-profilo") { modulo = null; avviso(""); disegnaProfili(); }
  else if (el.id === "cerca-untis") cercaScuole();
  else if (el.id === "cal-copia") copiaCalendario();
  else if (el.id === "cal-azzera") { try { localStorage.removeItem(chiaveCalendario()); } catch {} aggiornaCalendario(); }
  else if (el.dataset.scuolaUntis) {
    leggiModulo();
    const s = scuoleTrovate[+el.dataset.scuolaUntis];
    modulo.untisServer = s.server; modulo.untisScuola = s.scuola; scuoleTrovate = null;
    disegnaProfili();
  }
  else if (el.dataset.togliUntis) { leggiModulo(); modulo.untisServer = modulo.untisScuola = modulo.untisClasse = ""; disegnaProfili(); }
});

const etichetta = $("#tip");
document.addEventListener("mousemove", (e) => {
  const el = e.target.closest ? e.target.closest("[data-tip]") : null;
  if (!el) { etichetta.hidden = true; return; }
  etichetta.innerHTML = el.dataset.tip;
  etichetta.hidden = false;
  const r = etichetta.getBoundingClientRect();
  etichetta.style.left = Math.max(8, Math.min(window.innerWidth - r.width - 8, e.clientX + 14)) + "px";
  etichetta.style.top = (e.clientY + 18 + r.height > window.innerHeight ? e.clientY - r.height - 10 : e.clientY + 18) + "px";
});

let ritardo;
window.addEventListener("resize", () => { clearTimeout(ritardo); ritardo = setTimeout(mostra, 150); });

// Sul telefono i widget si vestono come l'app (tema «Ultra»: lattina bianca; gli altri: stile Nothing).
function comunicaTema() {
  if (P && P.android) api("/api/tema", { tema: temaScelto }).catch(() => {});
}

// La scheda «Oggi» segue l'orologio: ogni minuto si ridisegna (lezione in corso, ore passate).
setInterval(() => {
  if (scheda === "oggi" && D && !D.vuoto && !document.hidden && !$("#app").hidden) mostra();
}, 60000);

// Il conto alla rovescia del riquadro «Adesso» scorre ogni secondo; a zero la scheda si ridisegna (inizia l'ora dopo).
setInterval(() => {
  if (scheda !== "oggi" || !D || D.vuoto || $("#app").hidden) return; // nelle altre schede il riquadro resta nascosto e fermo
  document.querySelectorAll("#tab-oggi [data-fine]").forEach((el) => {
    el.textContent = contoGiu(el.dataset.fine);
    if (el.textContent === "−0:00" && !document.hidden) mostra();
  });
}, 1000);

(async function avvio() {
  $("#tema").innerHTML = Object.entries(TEMI).map(([k, nome]) => `<option value="${k}"${k === temaScelto ? " selected" : ""}>${nome}</option>`).join("");
  try { const salvata = localStorage.getItem("scheda"); if (SCHEDE.includes(salvata)) scheda = salvata; } catch {}
  try {
    P = await api("/api/profili");
  } catch (errore) {
    avviso(`Impossibile leggere i profili: ${errore.message}`, true);
    return;
  }
  try { S = await api("/api/sincronizzazione"); } catch {}
  // Il controllo degli aggiornamenti non deve rallentare l'apertura: arriva quando arriva.
  api("/api/aggiornamenti").then((stato) => { A = stato; ridisegnaAggiornamenti(); }).catch(() => {});
  comunicaTema(); // il tema può essere stato scelto prima che i widget lo sapessero leggere
  // Con un solo profilo si entra direttamente; con più profili (o nessuno) si sceglie.
  const unico = P.profili.length === 1 ? P.profili[0].id : null;
  if (P.attivo || unico) await entra(P.attivo || unico);
  else {
    schermo(true);
    try { if (P.profili.length > 1 && localStorage.getItem("vista") === "panoramica") await mostraVista("panoramica"); } catch {}
    sincronizza();
  }
  setInterval(controllaSync, 20000);
})();

// Se la pagina resta aperta per ore o giorni, al ritorno i dati vengono riscaricati da soli.
document.addEventListener("visibilitychange", async () => {
  if (document.hidden) { segnaVisti(scheda); return; }
  await sincronizza();
  controllaSync();
  if (D && P && P.attivo && datiVecchi()) aggiorna();
});
