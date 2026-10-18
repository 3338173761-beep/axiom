// Axiom 自动化测试结果接收服务器（零依赖，Node 内置 http）
const http = require("http");
const fs = require("fs");
const OUT = "E:\\Axiom\\web\\test\\result.txt";
const server = http.createServer((req, res) => {
  // CORS：允许跨源（8765 页面 → 8788 上报）
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  if (req.method === "OPTIONS") { res.end("ok"); return; }
  if (req.method === "POST" && req.url === "/result") {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      try {
        // 追加模式：每行一条 JSON（便于多 case 汇总）
        fs.appendFileSync(OUT, body + "\n", "utf8");
        res.end("saved");
      } catch (e) {
        res.end("err " + e.message);
      }
    });
  } else if (req.url === "/ping") {
    res.end("pong");
  } else {
    res.end("ok");
  }
});
server.listen(8788, "127.0.0.1", () => console.log("result server on 8788"));
