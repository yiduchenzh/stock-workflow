#!/usr/bin/env node
/**
 * webread.js — 自动读取网页数据（puppeteer-core + 系统 Edge，零浏览器下载）
 *
 * 用法:
 *   node webread.js <url> [选项]
 *
 * 选项:
 *   --out <dir>          输出目录（默认 ./out）
 *   --tag <name>         输出文件名前缀（默认取 host）
 *   --sel <css>          只提取该选择器内的文本
 *   --wait <css|ms>      额外等待：选择器出现，或毫秒数（默认 3000）
 *   --timeout <ms>       导航超时（默认 45000）
 *   --net                抓取页面内部 XHR/fetch 返回的 JSON（财经页核心用法）
 *   --tables             提取 <table> 为二维数组
 *   --links              提取链接
 *   --shot               截图（写到 out/<tag>.png）
 *   --scroll             滚动到底触发懒加载
 *   --visible            显示浏览器窗口（诊断用，默认无头）
 *   --ua <string>        自定义 User-Agent
 *   --max-text <n>       文本最大字符数（默认 20000）
 *   --stdout             把 JSON 结果同时打到 stdout
 *
 * 输出: <out>/<tag>.json（结构化）+ <out>/<tag>.txt（纯文本）
 * 设计: 结果一律落 UTF-8 文件（Windows 控制台中文不可信），stdout 只打摘要。
 */
'use strict';
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

const DEFAULT_UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0';

function parseArgs(argv) {
  const o = {
    url: null, out: 'out', tag: null, sel: null, wait: '3000', timeout: 45000,
    net: false, tables: false, links: false, shot: false, scroll: false,
    visible: false, ua: DEFAULT_UA, maxText: 20000, stdout: false,
  };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    if (a === '--out') o.out = next();
    else if (a === '--tag') o.tag = next();
    else if (a === '--sel') o.sel = next();
    else if (a === '--wait') o.wait = next();
    else if (a === '--timeout') o.timeout = Number(next());
    else if (a === '--net') o.net = true;
    else if (a === '--tables') o.tables = true;
    else if (a === '--links') o.links = true;
    else if (a === '--shot') o.shot = true;
    else if (a === '--scroll') o.scroll = true;
    else if (a === '--visible') o.visible = true;
    else if (a === '--stdout') o.stdout = true;
    else if (a === '--ua') o.ua = next();
    else if (a === '--max-text') o.maxText = Number(next());
    else rest.push(a);
  }
  if (!o.url && rest.length) o.url = rest[0];
  return o;
}

function findBrowser() {
  const cands = [
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  ];
  for (const c of cands) if (fs.existsSync(c)) return c;
  throw new Error('未找到 Edge/Chrome，请检查 executablePath');
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const KEEP_KEY = /(name|code|price|close|open|high|low|vol|amount|change|pct|rate|turnover|pe|pb|market|cap|count|value|title|time|date|status|symbol|url|data|list|result|total|index|sum)/i;
const NUM_RE = /^-?[\d,]+(\.\d+)?%?$/;

/** 从任意 JSON 结构里挑出"像数据表"的数组，压成统一列名 */
function shapePayload(obj) {
  const out = [];
  const seen = new Set();
  const walk = (node, p) => {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) {
      if (node.length >= 2 && node.every((x) => x && typeof x === 'object' && !Array.isArray(x))) {
        const keys = Object.keys(node[0]);
        if (keys.length >= 2 && keys.some((k) => KEEP_KEY.test(k))) {
          const sig = p + '|' + keys.slice(0, 8).join(',') + '|' + node.length;
          if (!seen.has(sig)) {
            seen.add(sig);
            out.push({ path: p, rows: node.length, columns: keys, sample: node.slice(0, 3) });
          }
          return;
        }
      }
      node.slice(0, 40).forEach((v, i) => walk(v, `${p}[${i}]`));
      return;
    }
    for (const k of Object.keys(node)) walk(node[k], p ? `${p}.${k}` : k);
  };
  walk(obj, '');
  return out.slice(0, 12);
}

(async () => {
  const o = parseArgs(process.argv.slice(2));
  if (!o.url) {
    console.error('用法: node webread.js <url> [--sel css] [--net] [--tables] [--shot] [--scroll]');
    process.exit(2);
  }
  const parsed = new URL(o.url);
  const tag = o.tag || parsed.hostname.replace(/[^\w.-]/g, '_');
  fs.mkdirSync(o.out, { recursive: true });
  const result = { url: o.url, fetched_at: new Date().toISOString(), tag, errors: [] };

  const browser = await puppeteer.launch({
    executablePath: findBrowser(),
    headless: !o.visible,
    args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--window-size=1600,1000', '--lang=zh-CN'],
    defaultViewport: { width: 1600, height: 1000 },
  });

  try {
    const page = await browser.newPage();
    await page.setUserAgent(o.ua);
    await page.setExtraHTTPHeaders({ 'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8' });

    const consoleErrs = [];
    page.on('console', (m) => { if (m.type() === 'error') consoleErrs.push(m.text().slice(0, 200)); });
    page.on('pageerror', (e) => consoleErrs.push('PAGEERROR: ' + String(e.message).slice(0, 200)));

    // ── 网络抓包：页面自己调的 JSON 接口（比解析 DOM 干净得多）
    const net = [];
    if (o.net) {
      page.on('response', async (res) => {
        try {
          const ct = (res.headers()['content-type'] || '').toLowerCase();
          const u = res.url();
          if (!/json|javascript\/x-json/.test(ct)) return;
          if (net.length >= 40) return;
          const txt = await res.text();
          if (!txt || txt.length > 4_000_000) return;
          let json = null;
          try { json = JSON.parse(txt); } catch { return; }
          net.push({ url: u, status: res.status(), bytes: txt.length, tables: shapePayload(json), raw: json });
        } catch { /* 忽略单条抓包失败 */ }
      });
    }

    const resp = await page.goto(o.url, { waitUntil: 'domcontentloaded', timeout: o.timeout });
    result.http_status = resp ? resp.status() : null;

    // 等待条件
    if (/^\d+$/.test(String(o.wait))) {
      await sleep(Number(o.wait));
    } else {
      await page.waitForSelector(o.wait, { timeout: 15000 }).catch(() => {});
      await sleep(1200);
    }
    try { await page.waitForNetworkIdle({ idleTime: 1200, timeout: 12000 }); } catch { /* 长连接页面忽略 */ }

    if (o.scroll) {
      await page.evaluate(async () => {
        const step = () => new Promise((r) => setTimeout(r, 350));
        for (let y = 0; y < document.body.scrollHeight && y < 40000; y += 900) {
          window.scrollTo(0, y);
          await step();
        }
        window.scrollTo(0, 0);
      });
      await sleep(1500);
    }

    result.title = await page.title();

    const extract = await page.evaluate((sel) => {
      const clean = (s) => (s || '').replace(/\u00a0/g, ' ').split('\n').map((x) => x.trim()).filter(Boolean).join('\n');
      const root = sel ? document.querySelector(sel) : null;
      const target = root || document.querySelector('main, #app, .content, .container') || document.body;
      const textOf = (el) => (el ? clean(el.innerText) : '');
      const meta = (n) => document.querySelector(`meta[name="${n}"],meta[property="${n}"]`)?.content || null;
      const tables = Array.from(document.querySelectorAll('table')).slice(0, 25).map((t) =>
        Array.from(t.querySelectorAll('tr')).slice(0, 80).map((tr) =>
          Array.from(tr.querySelectorAll('th,td')).map((c) => c.innerText.trim())
        )
      );
      const links = Array.from(document.querySelectorAll('a[href]')).slice(0, 300).map((a) => ({
        text: a.innerText.trim().slice(0, 80), href: a.href,
      })).filter((l) => l.text);
      const ld = Array.from(document.querySelectorAll('script[type="application/ld+json"]')).slice(0, 10)
        .map((s) => { try { return JSON.parse(s.textContent); } catch { return null; } }).filter(Boolean);
      return {
        description: meta('description'), keywords: meta('keywords'),
        text: textOf(target), text_scope: root ? sel : 'auto', tables, links, ld_json: ld,
        page_chars: (document.body.innerText || '').length,
      };
    }, o.sel);

    result.description = extract.description;
    result.keywords = extract.keywords;
    result.text_scope = extract.text_scope;
    result.text_truncated = extract.text.length > o.maxText;
    result.text = extract.text.slice(0, o.maxText);
    result.page_chars = extract.page_chars;
    if (o.tables) result.tables = extract.tables;
    if (o.links) result.links = extract.links;
    if (extract.ld_json.length) result.ld_json = extract.ld_json;
    if (o.net) {
      result.net_json = net.map((n) => ({ url: n.url, status: n.status, bytes: n.bytes, tables: n.tables }));
      result.net_payloads = net; // 完整 payload，供落库/分析
    }
    result.console_errors = [...new Set(consoleErrs)].slice(0, 20);

    if (o.shot) {
      const png = path.join(o.out, `${tag}.png`);
      await page.screenshot({ path: png, fullPage: false });
      result.screenshot = png;
    }
  } catch (e) {
    result.errors.push(String(e && e.message ? e.message : e));
  } finally {
    await browser.close();
  }

  const jsonPath = path.join(o.out, `${tag}.json`);
  const txtPath = path.join(o.out, `${tag}.txt`);
  fs.writeFileSync(jsonPath, JSON.stringify(result, null, 2), 'utf8');
  const head = [
    `URL: ${result.url}`,
    `TITLE: ${result.title || ''}`,
    `HTTP: ${result.http_status}  CHARS: ${result.page_chars}  SCOPE: ${result.text_scope}`,
    `NET_JSON: ${result.net_json ? result.net_json.length : 0}  ERRORS: ${result.errors.length}`,
    '--- TEXT ---',
    result.text || '',
    '--- NET ENDPOINTS ---',
    ...(result.net_json || []).map((n) => `${n.status} ${n.bytes}B ${n.tables.map((t) => t.path + '(' + t.rows + ')').join(',')} :: ${n.url}`),
    '--- CONSOLE ERRORS ---',
    ...(result.console_errors || []),
  ].join('\n');
  fs.writeFileSync(txtPath, head, 'utf8');

  console.log(JSON.stringify({
    ok: result.errors.length === 0, url: result.url, title: result.title,
    http: result.http_status, chars: result.page_chars, text_scope: result.text_scope,
    net_endpoints: (result.net_json || []).length,
    net_tables: (result.net_json || []).reduce((a, n) => a + n.tables.length, 0),
    console_errors: (result.console_errors || []).length,
    json: jsonPath, txt: txtPath, png: result.screenshot || null,
  }));
  if (o.stdout) console.log(JSON.stringify(result));
})().catch((e) => {
  console.error('FATAL ' + (e && e.message ? e.message : e));
  process.exit(1);
});
