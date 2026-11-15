// Resident textlint server for ja_quality_guard.py (Stop hook).
// WHY: a cold `textlint` run loads the kuromoji dictionary and takes 20-40 s on
// this machine (measured 2026-11-15: 39.9 s / 20.5 s / 35.4 s; kuromoji alone
// 15.3 s). A Stop hook cannot wait that long on every answer, so the linter is
// loaded once and kept in memory; each check is then an HTTP POST.
// Usage: node ja_textlint_server.js <toolsDir> <port>
//   toolsDir: folder holding node_modules/ (textlint + rules) and .textlintrc.json
// Listens on 127.0.0.1 only. Exits after IDLE_MS without requests.
// Deployed from claude-governance/templates/hooks/ -- edit there, not here.
const path = require("path");
const http = require("http");
const toolsDir = process.argv[2];
const port = parseInt(process.argv[3] || "47613", 10);
const IDLE_MS = 3 * 60 * 60 * 1000;
module.paths.unshift(path.join(toolsDir, "node_modules"));
const { createLinter, loadTextlintrc } = require(path.join(toolsDir, "node_modules", "textlint"));
let linter = null;
let last = Date.now();
(async () => {
  const descriptor = await loadTextlintrc({
    configFilePath: path.join(toolsDir, ".textlintrc.json"),
    node_modulesDir: path.join(toolsDir, "node_modules"),
  });
  linter = createLinter({ descriptor });
  // warm the tokenizer so the first real request is fast
  await linter.lintText("これはテストです。", "warm.md");
  const srv = http.createServer((req, res) => {
    last = Date.now();
    if (req.method === "GET") { res.end(JSON.stringify({ ok: true, pid: process.pid })); return; }
    let body = "";
    req.setEncoding("utf8");
    req.on("data", (c) => { body += c; });
    req.on("end", async () => {
      try {
        const r = await linter.lintText(body, "answer.md");
        res.setHeader("Content-Type", "application/json; charset=utf-8");
        res.end(JSON.stringify(r.messages.map((m) => ({ rule: m.ruleId, line: m.line, col: m.column, msg: m.message }))));
      } catch (e) {
        res.statusCode = 500; res.end(String(e));
      }
    });
  });
  srv.listen(port, "127.0.0.1");
  setInterval(() => { if (Date.now() - last > IDLE_MS) process.exit(0); }, 60 * 1000);
})().catch((e) => { console.error(e); process.exit(1); });
