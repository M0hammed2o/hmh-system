'use strict';
const { chromium } = require('./node_modules/playwright-core');
const path = require('path');
const fs = require('fs');
const http = require('http');

const BASE_URL = process.env.SCREENSHOT_BASE_URL || 'http://localhost:5173';
const EMAIL    = process.env.SCREENSHOT_EMAIL;
const PASSWORD = process.env.SCREENSHOT_PASSWORD;
const OUT_DIR  = path.join(__dirname, 'output');

if (!EMAIL || !PASSWORD) {
  console.error('Error: SCREENSHOT_EMAIL and SCREENSHOT_PASSWORD must be set.');
  console.error('Copy .env.example to .env and fill in the values, then run with:');
  console.error('  node -r dotenv/config capture_analytics.js');
  process.exit(1);
}

const TABS = [
  { label: 'Overview',         file: 'analytics_overview.png' },
  { label: 'Suppliers',        file: 'analytics_suppliers.png' },
  { label: 'Spend Analysis',   file: 'analytics_spend.png' },
  { label: 'Projects',         file: 'analytics_projects.png' },
  { label: 'Price History',    file: 'analytics_prices.png' },
  { label: 'Quote Comparison', file: 'analytics_quotes.png' },
  { label: 'Savings',          file: 'analytics_savings.png' },
  { label: 'Reports',          file: 'analytics_reports.png' },
];

function getToken() {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({ email: EMAIL, password: PASSWORD });
    const apiUrl = new URL('/api/v1/auth/login', BASE_URL.replace(':5173', ':8000'));
    const req = http.request({
      hostname: apiUrl.hostname,
      port: parseInt(apiUrl.port) || 8000,
      path: apiUrl.pathname,
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
    }, res => {
      let data = '';
      res.on('data', d => data += d);
      res.on('end', () => {
        try {
          const json = JSON.parse(data);
          if (!json.access_token) { reject(new Error('Login failed: no access_token in response')); return; }
          resolve(json.access_token);
        } catch (e) { reject(new Error('Login response parse error: ' + e.message)); }
      });
    });
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

(async () => {
  if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });

  console.log('Authenticating…');
  const token = await getToken();
  console.log('JWT obtained (not logged).');

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await context.newPage();

  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });
  await page.evaluate(t => { localStorage.setItem('hmh_access_token', t); }, token);

  await page.goto(BASE_URL + '/procurement-analytics', { waitUntil: 'networkidle', timeout: 20000 });
  await page.waitForTimeout(3000);

  for (const tab of TABS) {
    try {
      const tabBtn = page.locator(`button:has-text("${tab.label}")`).first();
      const exists = await tabBtn.count();
      if (exists > 0) {
        await tabBtn.click();
        await page.waitForTimeout(2000);
      } else {
        console.log(`  Tab not found: ${tab.label}`);
      }
    } catch (e) {
      console.log(`  Tab error for ${tab.label}: ${e.message}`);
    }

    const file = path.join(OUT_DIR, tab.file);
    await page.screenshot({ path: file, fullPage: false });
    const size = fs.statSync(file).size;
    console.log(`Saved: ${tab.file} (${size} bytes) — ${tab.label}`);
  }

  await browser.close();
  console.log('\nDone. Screenshots in: ' + OUT_DIR);
})().catch(e => { console.error('Fatal:', e.message); process.exit(1); });
