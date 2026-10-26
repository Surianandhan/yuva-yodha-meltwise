// Builds the PowerPoint version of the MeltWise deck from the rendered slide images and speaker notes.
// Usage: node make_pptx.js <output.pptx> [build_dir]
const fs = require('fs');
const path = require('path');
const PptxGenJS = require('pptxgenjs');

const build = process.argv[3] || path.join(__dirname, 'build');
const output = process.argv[2];
const notes = JSON.parse(fs.readFileSync(path.join(build, 'notes.json'), 'utf8'));

const pptx = new PptxGenJS();
pptx.layout = 'LAYOUT_WIDE'; // 13.333 x 7.5 in, 16:9
pptx.title = 'MeltWise - Yuva Yodha 2026';
pptx.author = 'Surianandhan Sridhar, Sameera Hussainy Pattan';

notes.forEach((slide, i) => {
  const s = pptx.addSlide();
  const image = path.join(build, `slide_${String(i + 1).padStart(2, '0')}.png`);
  s.addImage({ path: image, x: 0, y: 0, w: 13.333, h: 7.5 });
  if (slide.notes) s.addNotes(slide.notes);
});

pptx.writeFile({ fileName: output }).then((file) => console.log(`Wrote ${file}`));
