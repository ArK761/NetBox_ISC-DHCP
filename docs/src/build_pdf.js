// Builds docs/NAVOD_SK.pdf and docs/MANUAL_EN.pdf from the HTML sources (Playwright/Chromium).
// Usage: node docs/src/build_pdf.js <version>
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
(async () => {
  const version = process.argv[2] || 'dev', src = __dirname, out = path.join(__dirname, '..');
  const b = await chromium.launch();
  for (const [file, pdf] of [['manual_sk.html', 'NAVOD_SK.pdf'], ['manual_en.html', 'MANUAL_EN.pdf']]) {
    const tmp = path.join(src, '.build_' + file);
    fs.writeFileSync(tmp, fs.readFileSync(path.join(src, file), 'utf8').replace('{{VERSION}}', version));
    const p = await b.newPage();
    await p.goto('file://' + tmp, { waitUntil: 'load' });
    await p.evaluate((title) => {  // table of contents from the h2 headings (always current)
      const m = document.querySelector('.meta'); if (!m) return;
      const d = document.createElement('div'); d.className = 'toc';
      d.innerHTML = '<b>' + title + '</b><ol>' + [...document.querySelectorAll('h2')].map(h => '<li>' + h.textContent.replace(/^\d+\.\s*/, '') + '</li>').join('') + '</ol>';
      m.after(d);
    }, file.includes('_sk') ? 'Obsah' : 'Contents');
    await p.pdf({ path: path.join(out, pdf), format: 'A4', printBackground: true,
      displayHeaderFooter: true, headerTemplate: '<span></span>',
      footerTemplate: '<div style="font-size:8px;width:100%;text-align:center;color:#64748b">NetBox ISC DHCP ' + version + ' – <span class="pageNumber"></span>/<span class="totalPages"></span></div>',
      margin: { top: '16mm', bottom: '16mm', left: '14mm', right: '14mm' } });
    fs.unlinkSync(tmp); fs.mkdirSync(path.join(out, '..', 'netbox_isc_dhcp', 'manual'), { recursive: true }); fs.copyFileSync(path.join(out, pdf), path.join(out, '..', 'netbox_isc_dhcp', 'manual', pdf)); console.log('built', pdf);
  }
  await b.close();
})();
