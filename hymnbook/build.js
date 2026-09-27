// Builds printable A4 PDFs of the hymns: one song per page, with a blank
// notation band above every lyric line.
//
//   node hymnbook/build.js
//
// Writes two versions next to this script:
//   entrance-hymns-staff.pdf  — empty 5-line music staff on every line
//   entrance-hymns-lined.pdf  — a plain writing line (tonic sol-fa, notes)

const fs = require('fs');
const path = require('path');
const { section, songs } = require('./songs');

let chromium;
try {
  ({ chromium } = require('playwright'));
} catch {
  ({ chromium } = require('/opt/node22/lib/node_modules/playwright'));
}

const esc = (s) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

// "[G]Come on [C]and" -> [{chord:'', text:''}, {chord:'G', text:'Come on '}, ...]
function parseLine(line) {
  const segs = [];
  const re = /\[([^\]]+)\]/g;
  let last = 0;
  let chord = '';
  let m;
  while ((m = re.exec(line))) {
    segs.push({ chord, text: line.slice(last, m.index) });
    chord = m[1];
    last = re.lastIndex;
  }
  segs.push({ chord, text: line.slice(last) });
  return segs.filter((s) => s.chord || s.text);
}

function renderLine(line, rules) {
  const segs = parseLine(line)
    .map(
      ({ chord, text }) =>
        `<span class="seg"><span class="ch">${esc(chord)}</span>` +
        `<span class="ly">${esc(text) || ' '}</span></span>`
    )
    .join('');
  const band = rules.map((top) => `<i style="top:${top}"></i>`).join('');
  return `<div class="line"><div class="band">${band}</div>${segs}</div>`;
}

function renderSong(song, rules) {
  const parts = song.parts
    .map(
      (p) =>
        `<section class="part"><h3>${esc(p.label)}</h3>` +
        p.lines.map((l) => renderLine(l, rules)).join('') +
        `</section>`
    )
    .join('');
  return (
    `<article class="song">` +
    `<div class="section">${esc(section)}</div>` +
    `<h2><span class="num">${song.number}.</span> ${esc(song.title)}</h2>` +
    parts +
    `</article>`
  );
}

// Band = the blank space between the chord row and the lyric.
const variants = {
  staff: {
    bandHeight: '11mm',
    // five ruled lines, 2mm apart
    rules: [0, 1, 2, 3, 4].map((i) => `${1.2 + i * 2}mm`),
  },
  lined: {
    bandHeight: '9mm',
    rules: ['7.5mm'],
  },
};

function html(variant) {
  const v = variants[variant];
  return `<!doctype html>
<html><head><meta charset="utf-8"><title>${esc(section)}</title>
<style>
  @page { size: A4; margin: 12mm 15mm 14mm 15mm; }
  :root {
    --chord-h: 4.5mm;
    --band-h: ${v.bandHeight};
    --rule: #8a8a8a;
    --ink: #111;
    --muted: #666;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: "Liberation Sans", Arial, Helvetica, sans-serif;
    color: var(--ink);
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
  .song { break-before: page; }
  .song:first-child { break-before: auto; }
  .section {
    font-size: 9pt; letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--muted); margin-bottom: 1mm;
  }
  h2 {
    font-size: 18pt; margin: 0 0 2mm; padding-bottom: 1.5mm;
    border-bottom: 0.4mm solid var(--ink);
  }
  h2 .num { color: var(--muted); }
  h3 {
    font-size: 9pt; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.06em; color: var(--muted);
    margin: 2.5mm 0 0; break-after: avoid;
  }
  .line {
    position: relative;
    margin-bottom: 1.5mm;
    break-inside: avoid;
    white-space: nowrap;
  }
  .band {
    position: absolute; left: 0; right: 0;
    top: var(--chord-h); height: var(--band-h);
  }
  .band i {
    position: absolute; left: 0; right: 0; height: 0;
    border-top: 0.2mm solid var(--rule);
  }
  .part { break-inside: avoid; }
  .seg {
    display: inline-flex; flex-direction: column;
    vertical-align: top;
  }
  .ch {
    height: var(--chord-h);
    font-weight: 700; font-size: 10.5pt; line-height: var(--chord-h);
    padding-right: 1.5mm;
    margin-bottom: var(--band-h);
  }
  .ly { font-size: 12.5pt; line-height: 5.5mm; white-space: pre; }
</style></head>
<body>${songs.map((s) => renderSong(s, v.rules)).join('')}</body></html>`;
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  for (const variant of Object.keys(variants)) {
    await page.setContent(html(variant), { waitUntil: 'load' });
    const out = path.join(__dirname, `entrance-hymns-${variant}.pdf`);
    await page.pdf({
      path: out,
      format: 'A4',
      printBackground: true,
      preferCSSPageSize: true,
      displayHeaderFooter: true,
      headerTemplate: '<span></span>',
      footerTemplate:
        '<div style="font-size:8pt;color:#666;width:100%;text-align:center;">' +
        '<span class="pageNumber"></span></div>',
    });
    console.log('wrote', path.relative(process.cwd(), out));
  }
  await browser.close();
})();
