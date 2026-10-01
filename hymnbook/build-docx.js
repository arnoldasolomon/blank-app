// Builds editable Word versions of the hymns: one song per page, with a
// blank notation band above every lyric line.
//
//   node hymnbook/build-docx.js
//
// Writes next to this script:
//   entrance-hymns-staff.docx  — empty 5-line music staff on every line
//   entrance-hymns-lined.docx  — a plain writing line (tonic sol-fa, notes)
//
// Chords sit on tab stops placed over the word they belong to. The stop
// positions come from measuring the lyric text in Liberation Sans, which
// has the same character widths as Arial (the font the document uses).

const fs = require('fs');
const path = require('path');
const {
  AlignmentType,
  BorderStyle,
  Document,
  Footer,
  HeightRule,
  LineRuleType,
  Packer,
  PageNumber,
  Paragraph,
  Table,
  TableCell,
  TableRow,
  TabStopType,
  TextRun,
  WidthType,
} = require('docx');
const { section, songs } = require('./songs');

let chromium;
try {
  ({ chromium } = require('playwright'));
} catch {
  ({ chromium } = require('/opt/node22/lib/node_modules/playwright'));
}

const FONT = 'Arial';
const LYRIC_PT = 12;
const CHORD_PT = 10;
const MIN_CHORD_GAP_PT = 3;

// A4 in twips (1pt = 20 twips, 1mm ≈ 56.7 twips)
const mm = (v) => Math.round(v * 56.7);
const PAGE = { width: 11906, height: 16838 };
const MARGIN = { top: mm(12), bottom: mm(14), left: mm(15), right: mm(15) };
const TEXT_WIDTH = PAGE.width - MARGIN.left - MARGIN.right;

const RULE = { style: BorderStyle.SINGLE, size: 4, color: '8A8A8A' };
const NONE = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' };
const GREY = '666666';

// Same inline-chord format as build.js: "[G]Come on [C]and"
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

// Chord x-positions in points: each chord starts where its lyric text
// starts, pushed right if it would run into the previous chord.
function chordStops(segs, measure) {
  const stops = [];
  let prefix = '';
  let minX = 0;
  for (const { chord, text } of segs) {
    if (chord) {
      const x = Math.max(measure(prefix, LYRIC_PT, false), minX);
      stops.push({ chord, x });
      minX = x + measure(chord, CHORD_PT, true) + MIN_CHORD_GAP_PT;
    }
    prefix += text;
  }
  return stops;
}

function chordParagraph(stops) {
  const runs = [];
  const tabStops = [];
  for (const { chord, x } of stops) {
    const pos = Math.round(x * 20);
    if (pos > 0) {
      tabStops.push({ type: TabStopType.LEFT, position: pos });
      runs.push(new TextRun({ text: '\t', font: FONT, size: CHORD_PT * 2 }));
    }
    runs.push(new TextRun({ text: chord, font: FONT, size: CHORD_PT * 2, bold: true }));
  }
  if (!runs.length) runs.push(new TextRun({ text: '', font: FONT, size: CHORD_PT * 2 }));
  return new Paragraph({
    children: runs,
    tabStops,
    keepNext: true,
    keepLines: true,
    spacing: { before: 0, after: 40 },
  });
}

// Tiny empty paragraph used inside the staff table cells.
const spacerPara = () =>
  new Paragraph({
    keepNext: true,
    spacing: { before: 0, after: 0, line: 20, lineRule: LineRuleType.EXACT },
    children: [new TextRun({ text: '', size: 2 })],
  });

// Five lines, 2mm apart: 4 rows with top, bottom and between-row borders.
function staffTable() {
  const rowHeight = mm(2);
  return new Table({
    width: { size: TEXT_WIDTH, type: WidthType.DXA },
    columnWidths: [TEXT_WIDTH],
    borders: {
      top: RULE,
      bottom: RULE,
      insideHorizontal: RULE,
      left: NONE,
      right: NONE,
      insideVertical: NONE,
    },
    rows: [0, 1, 2, 3].map(
      () =>
        new TableRow({
          height: { value: rowHeight, rule: HeightRule.EXACT },
          cantSplit: true,
          children: [
            new TableCell({
              width: { size: TEXT_WIDTH, type: WidthType.DXA },
              margins: { top: 0, bottom: 0, left: 0, right: 0 },
              children: [spacerPara()],
            }),
          ],
        })
    ),
  });
}

// One writing line: an empty paragraph with a bottom border.
function writingLine() {
  return new Paragraph({
    keepNext: true,
    spacing: { before: 0, after: 0, line: mm(8), lineRule: LineRuleType.EXACT },
    border: { bottom: { ...RULE, space: 1 } },
    children: [new TextRun({ text: '', size: 2 })],
  });
}

// keepNext holds a verse together on one page (Word breaks it anyway if
// the verse is longer than a page).
function lyricParagraph(segs, spaceBefore, keepNext) {
  return new Paragraph({
    keepNext,
    children: [
      new TextRun({
        text: segs.map((s) => s.text).join('').trimEnd(),
        font: FONT,
        size: LYRIC_PT * 2,
      }),
    ],
    spacing: { before: spaceBefore, after: 140 },
  });
}

function songBlocks(song, variant, measure, first) {
  const blocks = [
    new Paragraph({
      pageBreakBefore: !first,
      keepNext: true,
      spacing: { after: 20 },
      children: [
        new TextRun({ text: section.toUpperCase(), font: FONT, size: 17, color: GREY }),
      ],
    }),
    new Paragraph({
      keepNext: true,
      spacing: { after: 80 },
      border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: '111111', space: 3 } },
      children: [
        new TextRun({ text: `${song.number}. `, font: FONT, size: 36, bold: true, color: GREY }),
        new TextRun({ text: song.title, font: FONT, size: 36, bold: true }),
      ],
    }),
  ];

  for (const part of song.parts) {
    blocks.push(
      new Paragraph({
        keepNext: true,
        spacing: { before: 140, after: 20 },
        children: [
          new TextRun({ text: part.label.toUpperCase(), font: FONT, size: 17, bold: true, color: GREY }),
        ],
      })
    );
    part.lines.forEach((line, i) => {
      const segs = parseLine(line);
      const keepNext = i < part.lines.length - 1;
      blocks.push(chordParagraph(chordStops(segs, measure)));
      if (variant === 'staff') {
        blocks.push(staffTable());
        blocks.push(lyricParagraph(segs, 80, keepNext));
      } else {
        blocks.push(writingLine());
        blocks.push(lyricParagraph(segs, 20, keepNext));
      }
    });
  }
  return blocks;
}

function buildDoc(variant, measure) {
  const children = songs.flatMap((song, i) => songBlocks(song, variant, measure, i === 0));
  return new Document({
    title: section,
    styles: { default: { document: { run: { font: FONT, size: LYRIC_PT * 2 } } } },
    sections: [
      {
        properties: { page: { size: PAGE, margin: MARGIN } },
        footers: {
          default: new Footer({
            children: [
              new Paragraph({
                alignment: AlignmentType.CENTER,
                children: [
                  new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 16, color: GREY }),
                ],
              }),
            ],
          }),
        },
        children,
      },
    ],
  });
}

// Measure every string we need in one browser session, then look them up.
async function makeMeasurer() {
  const wanted = new Set();
  for (const song of songs)
    for (const part of song.parts)
      for (const line of part.lines) {
        let prefix = '';
        for (const { chord, text } of parseLine(line)) {
          wanted.add(`L|${prefix}`);
          if (chord) wanted.add(`C|${chord}`);
          prefix += text;
        }
      }

  const browser = await chromium.launch();
  const page = await browser.newPage();
  const widths = await page.evaluate(
    ({ keys, lyricPt, chordPt }) => {
      const ctx = document.createElement('canvas').getContext('2d');
      const out = {};
      for (const key of keys) {
        const [kind, text] = [key.slice(0, 1), key.slice(2)];
        ctx.font =
          kind === 'C'
            ? `bold ${chordPt}pt "Liberation Sans"`
            : `${lyricPt}pt "Liberation Sans"`;
        out[key] = ctx.measureText(text).width * 0.75; // px -> pt
      }
      return out;
    },
    { keys: [...wanted], lyricPt: LYRIC_PT, chordPt: CHORD_PT }
  );
  await browser.close();

  return (text, pt, bold) => {
    const key = `${bold ? 'C' : 'L'}|${text}`;
    if (!(key in widths)) throw new Error(`unmeasured text: ${key}`);
    return widths[key];
  };
}

(async () => {
  const measure = await makeMeasurer();
  for (const variant of ['staff', 'lined']) {
    const out = path.join(__dirname, `entrance-hymns-${variant}.docx`);
    fs.writeFileSync(out, await Packer.toBuffer(buildDoc(variant, measure)));
    console.log('wrote', path.relative(process.cwd(), out));
  }
})();
