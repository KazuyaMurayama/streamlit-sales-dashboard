// Mermaid ブロックを headless Chromium で実レンダリングし、GitHub の操作パネルを
// 模した矩形との交差を検出する。mermaid_overlay_check.py から呼ばれる。
//
// 入力(stdin JSON): {"blocks":[{"id":"...","code":"..."}], "viewports":[{"name":"mobile","width":367}, ...],
//                    "panel":{...}, "preview_dir": "/path or null"}
// 出力(stdout JSON): {"results":[{"id","viewport","svg_w","svg_h","scale","elements":[...],"hits":[...],"error":null}]}
//
// パネル寸法(CSS px)は 2026-09-05 のスマホ実スクリーンショット1枚からの実測値
// （mermaid_overlay_check.py の PANEL 定数）。GitHub 側の実装値ではない。
"use strict";
const path = require("path");
const fs = require("fs");
const { execSync } = require("child_process");
const crypto = require("crypto");
const os = require("os");

// Playwright の解決順: 環境変数 → 通常解決 → npm のグローバル root
function loadPlaywright() {
  const cands = [process.env.PW_MODULE, "playwright"];
  try { cands.push(path.join(execSync("npm root -g", { stdio: ["ignore", "pipe", "ignore"] }).toString().trim(), "playwright")); } catch (e) {}
  for (const c of cands) { if (!c) continue; try { return require(c); } catch (e) {} }
  throw new Error("playwright が見つからない。`npm i -g playwright && npx playwright install chromium` を実行するか PW_MODULE で場所を指定すること");
}
const { chromium } = loadPlaywright();

// mermaid.min.js の解決順: 環境変数 → 同ディレクトリ → vendor/ → cwd の _meta/vendor → ~/.cache（jsdelivr から取得・sha256 固定）
const MERMAID_VERSION = "11.4.1";
const MERMAID_SHA256 = "a43bc1afd446f9c4cc66ac5dd45d02e8d65e26fc5344ec0ef787f88d6ddb6f9e"; // 2026-09-05 取得時に実測
const MERMAID_URL = `https://cdn.jsdelivr.net/npm/mermaid@${MERMAID_VERSION}/dist/mermaid.min.js`;
function sha256File(p) { return crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex"); }
function resolveMermaid() {
  const cands = [process.env.MERMAID_JS, path.join(__dirname, "mermaid.min.js"), path.join(__dirname, "vendor", "mermaid.min.js"),
    path.join(process.cwd(), "_meta", "vendor", "mermaid.min.js")];
  for (const c of cands) if (c && fs.existsSync(c)) return c;
  const cache = path.join(os.homedir(), ".cache", "mermaid", `mermaid-${MERMAID_VERSION}.min.js`);
  if (fs.existsSync(cache) && sha256File(cache) === MERMAID_SHA256) return cache;
  fs.mkdirSync(path.dirname(cache), { recursive: true });
  execSync(`curl -sSL --retry 2 -o "${cache}" "${MERMAID_URL}"`, { stdio: "ignore" });
  const got = sha256File(cache);
  if (got !== MERMAID_SHA256) { fs.unlinkSync(cache); throw new Error(`mermaid.min.js の sha256 不一致 (${got})`); }
  return cache;
}
const MERMAID_JS = resolveMermaid();

function readStdin() {
  return new Promise((res) => {
    let d = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (c) => (d += c));
    process.stdin.on("end", () => res(d));
  });
}

function pageHtml(width, panel) {
  // GitHub の表示を模す: コンテナ幅 = viewport、SVG は max-width:100% で縮小、
  // パネルはコンテナの右上・右下に絶対配置（固定 CSS px）。
  return `<!doctype html><html><head><meta charset="utf-8">
<style>
 html,body{margin:0;padding:0;background:#fff}
 #wrap{position:relative;width:${width}px;padding:${panel.container_pad}px;box-sizing:border-box}
 #wrap svg{max-width:100%;height:auto;display:block}
 .ov{position:absolute;background:rgba(220,0,0,.28);border:2px solid #c00;box-sizing:border-box;pointer-events:none}
 #tr{top:${panel.tr.top}px;right:${panel.tr.right}px;width:${panel.tr.w}px;height:${panel.tr.h}px}
 #br{bottom:${panel.br.bottom}px;right:${panel.br.right}px;width:${panel.br.w}px;height:${panel.br.h}px}
 .hit rect,.hit polygon,.hit circle,.hit path{stroke:#c00!important;stroke-width:3px!important}
</style></head><body><div id="wrap"><div id="svg"></div><div class="ov" id="tr"></div><div class="ov" id="br"></div></div>
</body></html>`;
}

async function main() {
  const inp = JSON.parse(await readStdin());
  const out = { results: [] };
  const browser = await chromium.launch();
  try {
    if (inp.export_dir) {
      // 画像書き出しモード: パネルなし・自然サイズ・2倍解像度で SVG 要素だけを PNG 化
      const page = await browser.newPage({ viewport: { width: 2400, height: 1600 }, deviceScaleFactor: 2 });
      await page.setContent(pageHtml(2400, inp.panel), { waitUntil: "load" });
      await page.addScriptTag({ path: MERMAID_JS });
      await page.evaluate(() => { window.mermaid.initialize({ startOnLoad: false, securityLevel: "loose" });
        document.querySelectorAll(".ov").forEach((e) => e.remove());
        const w = document.getElementById("wrap"); w.style.width = "auto"; w.style.display = "inline-block"; w.style.padding = "12px"; });
      for (const b of inp.blocks) {
        const r = { id: b.id, mode: "export", error: null };
        try {
          const dims = await page.evaluate(async (code) => {
            const host = document.getElementById("svg"); host.innerHTML = "";
            const { svg } = await window.mermaid.render("x" + Math.random().toString(36).slice(2), code);
            host.innerHTML = svg;
            const s = host.querySelector("svg"); s.style.maxWidth = "none"; s.style.width = s.viewBox.baseVal.width + "px";
            return { svg_w: s.viewBox.baseVal.width, svg_h: s.viewBox.baseVal.height };
          }, b.code);
          const f = path.join(inp.export_dir, `${b.out || b.id}.png`);
          await page.locator("#wrap").screenshot({ path: f, omitBackground: false });
          Object.assign(r, dims, { png: f });
        } catch (e) { r.error = String(e && e.message ? e.message : e).split("\n")[0]; }
        out.results.push(r);
      }
      await page.close();
      await browser.close();
      process.stdout.write(JSON.stringify(out));
      return;
    }
    for (const vp of inp.viewports) {
      const page = await browser.newPage({ viewport: { width: Math.max(vp.width, 320), height: 900 }, deviceScaleFactor: 2 });
      await page.setContent(pageHtml(vp.width, inp.panel), { waitUntil: "load" });
      await page.addScriptTag({ path: MERMAID_JS }); // about:blank からは file:// を読めないためインライン注入
      await page.evaluate(() => window.mermaid.initialize({ startOnLoad: false, securityLevel: "loose" }));
      for (const b of inp.blocks) {
        const r = { id: b.id, viewport: vp.name, svg_w: null, svg_h: null, disp_w: null, disp_h: null, scale: null, elements: [], hits: [], error: null };
        try {
          const data = await page.evaluate(async (code) => {
            const host = document.getElementById("svg");
            host.innerHTML = "";
            const { svg } = await window.mermaid.render("m" + Math.random().toString(36).slice(2), code);
            host.innerHTML = svg;
            const s = host.querySelector("svg");
            const vb = s.viewBox && s.viewBox.baseVal;
            const svg_w = vb && vb.width ? vb.width : s.getBBox().width;
            const svg_h = vb && vb.height ? vb.height : s.getBBox().height;
            const sr = s.getBoundingClientRect();
            const rectOf = (el) => { const r = el.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; };
            const inter = (a, b) => !(a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y);
            const panels = { tr: rectOf(document.getElementById("tr")), br: rectOf(document.getElementById("br")) };
            const elements = [];
            const push = (kind, el, label) => {
              const txt = (label || "").replace(/\s+/g, " ").trim();
              const cls = (el.getAttribute("class") || "");
              // 空ラベル or spacer クラスは「見えなくてよい」要素として除外
              if (!txt || /\bspacer\b/.test(cls)) return;
              const r = rectOf(el);
              if (r.w === 0 || r.h === 0) return;
              const hit = [];
              for (const k of Object.keys(panels)) if (inter(r, panels[k])) hit.push(k);
              if (hit.length) el.classList.add("hit");
              elements.push({ kind, id: el.id || null, label: txt.slice(0, 40), x: +(r.x - sr.left).toFixed(1), y: +(r.y - sr.top).toFixed(1), w: +r.w.toFixed(1), h: +r.h.toFixed(1), hit });
            };
            s.querySelectorAll("g.node").forEach((n) => push("node", n, n.textContent));
            s.querySelectorAll("g.edgeLabel").forEach((n) => push("edgeLabel", n, n.textContent));
            s.querySelectorAll("g.cluster").forEach((n) => {
              const lab = n.querySelector(".cluster-label");
              if (lab) push("clusterLabel", lab, lab.textContent);
            });
            return { svg_w, svg_h, disp_w: sr.width, disp_h: sr.height, elements };
          }, b.code);
          Object.assign(r, data);
          r.scale = data.svg_w ? +(data.disp_w / data.svg_w).toFixed(3) : null;
          r.hits = data.elements.filter((e) => e.hit.length);
          if (inp.preview_dir) {
            const f = path.join(inp.preview_dir, `${b.id}__${vp.name}.png`);
            await page.locator("#wrap").screenshot({ path: f });
            r.preview = f;
          }
        } catch (e) {
          r.error = String(e && e.message ? e.message : e).split("\n")[0];
        }
        out.results.push(r);
      }
      await page.close();
    }
  } finally {
    await browser.close();
  }
  process.stdout.write(JSON.stringify(out));
}
main().catch((e) => { process.stdout.write(JSON.stringify({ results: [], fatal: String(e && e.stack || e) })); process.exit(0); });
