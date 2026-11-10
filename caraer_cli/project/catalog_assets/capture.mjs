import { access } from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { chromium } from 'playwright';
import sharp from 'sharp';
import { publicAsset } from './public-assets.mjs';

export const CAPTURE_VERSION = 'catalog-webp-1';
export const WIDTH = 1440;
export const HEIGHT = 900;
let installing;
let active = false;
const require = createRequire(import.meta.url);

async function prepareBrowser() {
  if (process.env.CARAER_CHROMIUM_PATH) return;
  try { await access(chromium.executablePath()); }
  catch {
    installing ??= promisify(execFile)(process.execPath,
      [join(dirname(require.resolve('playwright/package.json')), 'cli.js'), 'install', 'chromium'], { timeout: 180000 })
      .finally(() => { installing = undefined; });
    await installing;
  }
}

/** Capture a known local catalog route or already-rendered HTML, never a remote navigation URL. */
export async function captureCatalog({ url, html, assets = {}, installBrowser = false }) {
  if (active) throw new Error('Image export is busy. Try again shortly.');
  active = true;
  let browser;
  let deadline;
  try {
    if (installBrowser) await prepareBrowser();
    browser = await chromium.launch({
      executablePath: process.env.CARAER_CHROMIUM_PATH || chromium.executablePath(),
      chromiumSandbox: process.env.CARAER_CHROMIUM_SANDBOX !== 'false', timeout: 15000,
    });
    deadline = setTimeout(() => browser.close().catch(() => {}), 60000);
    const context = await browser.newContext({ viewport: { width: WIDTH, height: HEIGHT },
      deviceScaleFactor: 1, reducedMotion: 'reduce', serviceWorkers: 'block' });
    const origin = url ? new URL(url).origin : 'https://catalog.invalid';
    const failures = [];
    await context.route('**/*', async route => {
      try {
        const request = route.request();
        const target = new URL(request.url());
        if (request.method() !== 'GET') return await route.abort();
        if (target.pathname === '/caraer/asset' && target.searchParams.has('src')) {
          return await route.fulfill(await publicAsset(new URL(target.searchParams.get('src'))));
        }
        if (target.origin === origin) {
          if (html !== undefined) {
            if (target.pathname === '/') return await route.fulfill({ contentType: 'text/html', body: html });
            const path = decodeURIComponent(target.pathname.slice(1));
            const asset = assets['public/' + path] ?? assets[path];
            if (!asset) throw new Error('Missing package asset');
            const types = { svg:'image/svg+xml', png:'image/png', jpg:'image/jpeg', jpeg:'image/jpeg',
              webp:'image/webp', gif:'image/gif', avif:'image/avif', woff:'font/woff', woff2:'font/woff2', ttf:'font/ttf', otf:'font/otf' };
            return await route.fulfill({ contentType: types[path.split('.').pop()] || 'application/octet-stream', body: Buffer.from(asset, 'base64') });
          }
          if (target.pathname.startsWith('/api/') || target.pathname.startsWith('/control/')) return await route.abort();
          return await route.continue();
        }
        if (request.isNavigationRequest()) return await route.abort();
        await route.fulfill(await publicAsset(target));
      } catch { failures.push(route.request().resourceType()); await route.abort(); }
    });
    await context.routeWebSocket('**/*', socket => socket.close());
    const page = await context.newPage();
    page.setDefaultTimeout(20000);
    page.on('pageerror', () => failures.push('script'));
    page.on('response', response => {
      if (response.status() >= 400 && ['image', 'font', 'stylesheet'].includes(response.request().resourceType())) {
        failures.push(response.request().resourceType());
      }
    });
    await page.goto(url || origin + '/', { waitUntil: 'load', timeout: 30000 });
    if (await page.locator('[data-caraer-module-error], .caraer-module-error').count()) throw new Error('The module could not render.');
    await page.addStyleTag({ content: '*,*::before,*::after{transition:none!important;caret-color:transparent!important}' });
    await page.evaluate(async () => {
      document.querySelectorAll('video,audio').forEach(media => { media.pause(); media.autoplay = false; });
      for (const image of document.images) image.loading = 'eager';
      // Trigger visible islands and reveal observers throughout a tall module before freezing it.
      const height = document.documentElement.scrollHeight;
      if (height > 16384) throw new Error('The example is too tall to export.');
      for (let y = 0; y < height; y += 900) {
        window.scrollTo(0, y);
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      }
      window.scrollTo(0, 0);
      await document.fonts.ready;
      await Promise.all([...document.images].map(image => image.decode()));
      if ([...document.fonts].some(font => font.status === 'error')) throw new Error('A company font failed to load.');
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    });
    await page.waitForFunction(() => !document.querySelector('astro-island[ssr][client="load"]'), null, { timeout: 15000 }).catch(() => {
      throw new Error('The module did not finish initializing.');
    });
    await page.evaluate(() => {
      for (const animation of document.getAnimations()) {
        try {
          if (Number.isFinite(animation.effect?.getComputedTiming().endTime)) {
            animation.effect.updateTiming({ fill: 'both' });
            animation.finish();
          } else animation.pause();
          animation.commitStyles();
          animation.cancel();
        } catch { animation.pause(); }
      }
    });
    if (failures.some(type => ['image', 'font', 'stylesheet', 'script'].includes(type))) throw Object.assign(new Error('A preview image, font or script could not load.'), { resources: [...new Set(failures)] });
    const height = await page.evaluate(() => {
      const root = document.querySelector('[data-catalog-module]');
      return root ? Math.ceil(root.getBoundingClientRect().top + Math.max(root.scrollHeight, root.getBoundingClientRect().height))
        : Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
    });
    if (height < 1) throw new Error('The module example is empty.');
    if (height > 16384) throw new Error('The example is too tall to export (maximum 16384px).');
    const png = await page.screenshot({ type: 'png', fullPage: true, omitBackground: true, animations: 'allow', timeout: 15000 });
    const captured = await sharp(png).metadata();
    const full = await sharp(png).extract({ left: 0, top: 0, width: WIDTH, height: Math.min(height, captured.height) }).webp({ lossless: true }).toBuffer();
    const metadata = await sharp(full).metadata();
    const thumbnails = {};
    for (const width of [320, 640]) {
      thumbnails[width] = await sharp(full).resize({ width, height: Math.round(width * 10 / 16),
        fit: metadata.height / metadata.width < 10 / 16 ? 'contain' : 'cover', position: 'top',
        background: { r: 255, g: 255, b: 255, alpha: 0 } }).webp({ quality: 85 }).toBuffer();
    }
    return { full, thumbnails, width: metadata.width, height: metadata.height };
  } finally {
    clearTimeout(deadline);
    try { await browser?.close(); } finally { active = false; }
  }
}
