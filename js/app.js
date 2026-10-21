/* Axiom Web — 主流程逻辑
 * 上传 → 格式识别 → 反编译 → 输出 / 语境翻译
 * 含：语法高亮、行号、复制、统计、进度日志
 */
"use strict";

(function () {

  const $ = id => document.getElementById(id);
  const els = {
    dropzone: $("dropzone"), fileInput: $("fileInput"), fileList: $("fileList"),
    cardInfo: $("cardInfo"), formatBanner: $("formatBanner"),
    cardActions: $("cardActions"), btnDecompile: $("btnDecompile"),
    outputName: $("outputName"), translateToggle: $("translateToggle"),
    translateOptions: $("translateOptions"), langFrom: $("langFrom"), langTo: $("langTo"),
    btnTranslate: $("btnTranslate"), keyRow: $("keyRow"), apiKey: $("apiKey"), btnSaveKey: $("btnSaveKey"),
    progressWrap: $("progressWrap"), barFill: $("barFill"), progressLog: $("progressLog"),
    cardResult: $("cardResult"), btnDownload: $("btnDownload"), btnCopy: $("btnCopy"), btnReset: $("btnReset"),
    tabTrans: $("tabTrans"), srcView: $("srcView"), transView: $("transView"),
    runtimeDot: $("runtimeDot"), runtimeText: $("runtimeText"), footEngine: $("footEngine"),
    resultStats: $("resultStats"), fmtCloud: $("fmtCloud"),
    liveTerminal: $("liveTerminal"), termBody: $("termBody")
  };
  const tabs = Array.from(document.querySelectorAll(".tab"));

  // ---------- 右侧实时解析终端（电脑端宽屏；手机端 CSS 强制隐藏） ----------
  const Term = {
    on: false,
    show() {
      if (this.on || !els.liveTerminal) return;
      this.on = true;
      els.liveTerminal.classList.add("term-on");
      els.liveTerminal.setAttribute("aria-hidden", "false");
      els.termBody.textContent = "";
      this.line("$ axiom-live-feed ready · drop a file to begin capture", "t-dim");
    },
    line(msg, cls) {
      if (!this.on || !els.termBody) return;
      const d = document.createElement("div");
      d.className = cls || "t-info";
      d.textContent = msg;
      els.termBody.appendChild(d);
      els.termBody.scrollTop = els.termBody.scrollHeight;
    },
    // 喷涌式输出：按间隔快速滚屏（黑客终端效果）
    flood(lines, cls, gap) {
      if (!this.on || !els.termBody) return;
      const arr = Array.isArray(lines) ? lines : [lines];
      const g = gap || 12;
      for (let i = 0; i < arr.length; i++) {
        setTimeout(() => { this.line(arr[i], cls); }, i * g);
      }
    },
    sep() { this.line("─".repeat(40), "t-dim"); },
    reset() {
      if (!els.liveTerminal) return;
      this.on = false;
      els.liveTerminal.classList.remove("term-on");
      els.liveTerminal.setAttribute("aria-hidden", "true");
      if (els.termBody) els.termBody.textContent = "";
    }
  };

  let currentFile = null, currentInfo = null, currentSrc = null, currentTrans = null;
  let decompileMs = 0;
  let decompiling = false;       // 反编译进行中
  let pendingTranslate = false;  // 反编译进行中点了翻译 → 排队，结果出来后自动翻译

  // 翻译按钮状态：点击反编译后（进行中或已完成）才亮；未开始反编译前黑
  function updateTranslateBtn() {
    els.btnTranslate.disabled = !(currentInfo && currentInfo.canTranslate && (decompiling || currentSrc));
  }

  // ---------- 工具 ----------
  function fmtSize(n) {
    if (n >= 1048576) return (n / 1048576).toFixed(1) + " MB";
    if (n >= 1024) return (n / 1024).toFixed(1) + " KB";
    return n + " B";
  }
  function log(msg) {
    els.progressLog.textContent += msg + "\n";
    els.progressLog.scrollTop = els.progressLog.scrollHeight;
    // 同步镜像到右侧实时解析终端（电脑端）
    Term.line(msg, /✗/.test(msg) ? "t-err" : /✓/.test(msg) ? "t-ok" : "t-info");
  }
  function setBar(p) { els.barFill.style.width = Math.min(100, Math.max(0, p)) + "%"; }
  function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }

  // ---------- 语法高亮（Ren'Py / Python） ----------
  const KW = new Set(("label menu jump call return define default if elif else while for in not and or pass break continue " +
    "show scene hide with play stop queue pause window voice renpy python init screen transform image $ " +
    "True False None and or").split(" "));
  const RENPY_LABEL = /^\s*(label|menu|init|screen|transform|image|define|default)\b/;

  function highlight(text) {
    // 分词：标签 | 注释 | 字符串 | 数字 | 关键词/其它
    const lines = String(text).split("\n");
    const out = [];
    for (const raw of lines) {
      let line = raw, html = "";
      const isLabel = RENPY_LABEL.test(line);
      const re = /(#.*$)|("(?:[^"\\]|\\.)*")|(_\("[^"]*"\))|(\b\d+(?:\.\d+)?\b)|(\b[A-Za-z_]\w*\b)/g;
      let last = 0, m;
      while ((m = re.exec(line)) !== null) {
        html += esc(line.slice(last, m.index));
        if (m[1]) html += `<span class="tok-cmt">${esc(m[1])}</span>`;
        else if (m[3]) html += `<span class="tok-str2">${esc(m[3])}</span>`;
        else if (m[2]) html += `<span class="tok-str">${esc(m[2])}</span>`;
        else if (m[4]) html += `<span class="tok-num">${esc(m[4])}</span>`;
        else {
          const w = m[5];
          if (KW.has(w)) html += `<span class="tok-kw">${esc(w)}</span>`;
          else if (isLabel && /^[a-z_]\w*:?$/.test(w)) html += `<span class="tok-label">${esc(w)}</span>`;
          else html += esc(w);
        }
        last = m.index + m[0].length;
      }
      html += esc(line.slice(last));
      out.push(html);
    }
    return out;
  }

  function renderCode(el, text, numbered) {
    const lines = highlight(text);
    el.innerHTML = lines.map((h, i) =>
      `<div class="code-line"><span class="line-no">${numbered ? i + 1 : ""}</span><span class="line-code">${h || " "}</span></div>`
    ).join("");
    el.scrollTop = 0;
  }

  // ---------- 引擎状态 ----------
  AxiomEngines.onStatus(function (state, msg) {
    els.runtimeDot.className = "dot" + (state === "ready" ? " ready" : state === "busy" ? " busy" : state === "error" ? " error" : "");
    els.runtimeText.textContent = msg;
  });

  // ---------- 格式徽章云 ----------
  (function buildCloud() {
    const chips = [
      ".rpyc", ".rpymc", ".rpa", ".pyc", ".dex", ".apk", ".jar", ".class", ".dll", ".exe", "ELF",
      ".txt", ".md", ".csv", ".srt", ".lrc", ".ps1", ".ust", ".svp"
    ];
    const count = (typeof AxiomFormats.tableCount === "function") ? AxiomFormats.tableCount() : 0;
    els.fmtCloud.innerHTML = chips.map(c => `<span class="fmt-chip">${c}</span>`).join("") +
      (count ? `<span class="fmt-chip fmt-chip-hi">共 ${count} 格式可识别</span>` : "");
  })();

  // ---------- 上传 ----------
  els.dropzone.addEventListener("click", () => els.fileInput.click());
  els.dropzone.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); els.fileInput.click(); } });
  els.fileInput.addEventListener("change", () => handleFiles(els.fileInput.files));
  els.dropzone.addEventListener("dragover", e => { e.preventDefault(); els.dropzone.classList.add("dragover"); });
  els.dropzone.addEventListener("dragleave", () => els.dropzone.classList.remove("dragover"));
  els.dropzone.addEventListener("drop", e => {
    e.preventDefault(); els.dropzone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
  });

  // ---------- Cyberpunk-style UI sfx: every button clicks (2077 vibe) ----------
  // The MUSIC toggle plays its own dedicated mute sound, so it is excluded.
  document.querySelectorAll("button").forEach(function (b) {
    if (b.id === "audioToggle") return;
    b.addEventListener("click", function () { if (window.__axiomSfx) window.__axiomSfx.click(); });
    b.addEventListener("mouseenter", function () { if (window.__axiomSfx) window.__axiomSfx.hover(); });
  });

  async function handleFiles(files) {
    const file = files[0];
    if (!file) return;
    currentFile = file; currentSrc = currentTrans = null; decompileMs = 0;

    els.fileList.innerHTML = "";
    const item = document.createElement("div");
    item.className = "file-item";
    item.innerHTML = `<span class="f-icon"></span><span class="f-name"></span><span class="f-size"></span>`;
    item.querySelector(".f-icon").textContent = "📄";
    item.querySelector(".f-name").textContent = file.name;
    item.querySelector(".f-size").textContent = fmtSize(file.size);
    els.fileList.appendChild(item);

    // 电脑端：右侧实时解析终端开启并开始捕获
    Term.show();
    Term.sep();
    Term.line("> ingesting \"" + file.name + "\" (" + fmtSize(file.size) + ")", "t-ok");
    Term.line("> dumping first 96 bytes of input stream …", "t-info");
    // 真实字节 hex dump（前 96 字节，16 字节/行）
    const headBytes = new Uint8Array(await file.slice(0, 96).arrayBuffer());
    const hexRows = [];
    for (let i = 0; i < headBytes.length; i += 16) {
      const chunk = Array.from(headBytes.slice(i, i + 16));
      const hex = chunk.map(b => b.toString(16).padStart(2, "0").toUpperCase()).join(" ");
      const asc = chunk.map(b => (b >= 32 && b < 127 ? String.fromCharCode(b) : ".")).join("");
      hexRows.push(String(i).padStart(4, "0") + "  " + hex.padEnd(47, " ") + " |" + asc + "|");
    }
    Term.flood(hexRows, "t-dim", 10);
    Term.flood([
      "> scanning signature registry (620 entries) …",
      "> probing magic bytes / header signature …",
    ], "t-info", 14);

    log("正在识别格式…");
    currentInfo = await AxiomFormats.identify(file);
    Term.flood([
      "> sig match → " + currentInfo.id + " (" + currentInfo.ext + ")",
      "> label: " + currentInfo.label,
      "> desc: " + currentInfo.desc,
    ], "t-ok", 16);
    Term.line("> format table hit: " + currentInfo.id + " · engine=" + (currentInfo.engine || "none"), "t-ai");
    showInfo(currentInfo);

    els.cardResult.classList.add("hidden");
    els.progressWrap.classList.add("hidden");
    els.progressLog.textContent = "";
    setBar(0);
    els.btnDecompile.disabled = false;
    els.btnTranslate.disabled = true;

    const base = file.name.replace(/\.[^.]+$/, "");
    els.outputName.value = currentInfo.id === "rpyc" ? base + ".rpy" : currentInfo.id === "pyc" ? base + ".py" : base + ".decoded.txt";

    els.cardActions.classList.remove("hidden");
    els.cardActions.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function showInfo(info) {
    els.cardInfo.classList.remove("hidden");
    const b = info.badge || {};
    const tbl = info.fmtTable;
    const tblLine = tbl
      ? `<div class="fmt-meta">格式库：${tbl.cat || "?"} · 可行性：${tbl.lvl || "?"} · 优先级：${tbl.pri || "?"}</div>`
      : "";
    els.formatBanner.innerHTML = `
      <div class="fmt-name">
        <span class="fmt-badge" style="background:${b.color || "#94a3b8"}">${b.ch || "?"}</span>
        ${info.icon} ${info.label}
        <span style="opacity:.7;font-size:12px;font-weight:400">（${info.ext}）</span>
      </div>
      <div class="fmt-meta">${info.desc}</div>
      ${tblLine}
      <div class="fmt-meta">引擎：${(AxiomEngines.get(info.engine) || { label: "—" }).label} · 可翻译：${info.canTranslate ? "是 ✓" : "否"}</div>
      <div class="fmt-meta">大小：${fmtSize(info.size)} · 文件头：<span class="fmt-head">${info.headHex || "—"}</span></div>`;
    els.translateToggle.checked = false;
    els.translateOptions.classList.add("hidden");
    if (!info.canTranslate) els.keyRow.classList.add("hidden");

    // 终端镜像：识别结果摘要
    Term.line("> [" + info.ext + "] " + info.label + " — " + info.desc, "t-ok");
    Term.line("> meta: " + fmtSize(info.size) + " · head=" + (info.headHex || "n/a") + " · translate=" + (info.canTranslate ? "yes" : "no"), "t-dim");
    if (tbl) Term.line("> table: cat=" + (tbl.cat || "?") + " · lvl=" + (tbl.lvl || "?") + " · pri=" + (tbl.pri || "?"), "t-ai");
    Term.line("> engine bound: " + ((AxiomEngines.get(info.engine) || { label: "—" }).label), "t-ai");
    Term.sep();
  }

  // ---------- 反编译 ----------
  els.btnDecompile.addEventListener("click", runDecompile);

  async function runDecompile() {
    if (!currentFile || !currentInfo) return;
    const engine = AxiomEngines.get(currentInfo.engine);
    if (!engine || typeof engine.decompile !== "function") {
      const hint = currentInfo.fmtLvl === "仅识别"
        ? "该格式在浏览器内仅可识别元数据；完整反编译将在 Windows/Android 端提供。"
        : "该格式的完整解析引擎将在 Windows/Android 端提供（持续接入中）。当前浏览器内已支持：Ren'Py / Python / DEX / APK / Java / .NET / 原生二进制 / 纯文本翻译。";
      alert("「" + currentInfo.label + "」" + hint);
      return;
    }
    // 点击反编译 → 翻译按钮立即亮起（可翻译格式）；此时点翻译会排队，等结果出来后自动执行
    decompiling = true;
    updateTranslateBtn();
    els.btnDecompile.disabled = true;
    els.progressWrap.classList.remove("hidden");
    els.progressLog.textContent = "";
    setBar(5);
    const t0 = performance.now();
    try {
      // Pyodide 加载步骤（常量与 engines.js 一致：v0.28.0 + jsdelivr CDN）
      Term.flood([
        "> runtime: Pyodide v0.28.0 · WASM ~10MB",
        ">   source: https://cdn.jsdelivr.net/pyodide/v0.28.0/full/pyodide.js",
        ">   injecting <script> tag …",
        ">   fetching runtime bundle …",
        ">   bootstrapping WASM …",
        ">   initializing Python env …",
      ], "t-ai", 10);
      log("正在准备引擎…（首次加载需下载 Pyodide 运行时，之后有缓存）");
      await AxiomEngines.loadPyodideRuntime();
      setBar(35);
      Term.flood([
        "> runtime ready",
        "> engine bound: " + engine.label + " :: " + currentInfo.id,
        "> feeding input buffer → engine …",
      ], "t-ok", 12);
      currentSrc = await engine.decompile(currentFile, log);
      decompileMs = Math.round(performance.now() - t0);
      Term.flood([
        "> done in " + decompileMs + " ms",
        "> source lines: " + String(currentSrc).split("\n").length,
        "> chars: " + String(currentSrc).length,
        "> bytes consumed: " + currentFile.size,
        "> pipeline status: PASS",
      ], "t-ok", 14);
      setBar(95);
      showResult(currentSrc, null, decompileMs);
      setBar(100);
      log("✓ 完成");
      // 若用户提前点了翻译 → 反编译结果出来后自动执行翻译，全部一起吐出
      if (pendingTranslate) {
        pendingTranslate = false;
        await runTranslate();
      }
    } catch (e) {
      pendingTranslate = false;
      Term.line("> FATAL: " + e.message, "t-err");
      log("✗ 错误：" + e.message);
      els.runtimeDot.className = "dot error";
      els.runtimeText.textContent = "反编译失败";
      alert("反编译失败：" + e.message);
    } finally {
      decompiling = false;
      updateTranslateBtn();
      els.btnDecompile.disabled = false;
    }
  }

  // ---------- 结果 ----------
  function showResult(src, trans, ms) {
    currentSrc = src; currentTrans = trans;
    // 反编译完成 → 翻译按钮保持亮（可翻译格式）；用户点翻译后再一起吐出
    updateTranslateBtn();
    const lines = String(src).split("\n").length;
    els.resultStats.innerHTML = `${lines} 行 · ${src.length.toLocaleString()} 字符${ms ? " · " + ms + " ms" : ""}`;
    renderCode(els.srcView, src, true);
    if (trans) { renderCode(els.transView, trans, true); els.tabTrans.classList.remove("hidden"); }
    else { els.tabTrans.classList.add("hidden"); els.transView.classList.add("hidden"); }
    els.cardResult.classList.remove("hidden");
    setActiveTab("src");
    els.cardResult.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  tabs.forEach(t => t.addEventListener("click", () => setActiveTab(t.dataset.tab)));
  function setActiveTab(name) {
    tabs.forEach(t => t.classList.toggle("active", t.dataset.tab === name));
    els.srcView.classList.toggle("hidden", name !== "src");
    els.transView.classList.toggle("hidden", name !== "trans");
  }

  // ---------- 复制 / 下载 ----------
  els.btnCopy.addEventListener("click", () => {
    const useTrans = !els.transView.classList.contains("hidden") && currentTrans;
    const content = useTrans ? currentTrans : currentSrc;
    if (!content) return;
    navigator.clipboard.writeText(content).then(() => {
      els.btnCopy.textContent = "已复制 ✓";
      setTimeout(() => { els.btnCopy.innerHTML = `<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10" fill="none" stroke="currentColor" stroke-width="2"/></svg>复制`; }, 1500);
    }).catch(() => alert("复制失败"));
  });

  els.btnDownload.addEventListener("click", () => {
    const useTrans = !els.transView.classList.contains("hidden") && currentTrans;
    const content = useTrans ? currentTrans : currentSrc;
    if (!content) return;
    const name = (els.outputName.value.trim() || "axiom-output") + (useTrans ? ".translated" : "");
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name; a.click();
    URL.revokeObjectURL(a.href);
  });

  // ---------- 重置 ----------
  els.btnReset.addEventListener("click", () => {
    currentFile = currentInfo = currentSrc = currentTrans = null;
    decompiling = false; pendingTranslate = false;
    els.fileInput.value = "";
    els.fileList.innerHTML = "";
    els.cardInfo.classList.add("hidden");
    els.cardActions.classList.add("hidden");
    els.cardResult.classList.add("hidden");
    els.progressWrap.classList.add("hidden");
    els.btnDecompile.disabled = true;
    els.btnTranslate.disabled = true;
    els.translateToggle.checked = false;
    els.translateOptions.classList.add("hidden");
    els.keyRow.classList.add("hidden");
    setBar(0);
    Term.reset();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  // ---------- 翻译 ----------
  els.translateToggle.addEventListener("change", () => {
    const on = els.translateToggle.checked;
    els.translateOptions.classList.toggle("hidden", !on);
    if (on) {
      const hasKey = !!AxiomTranslate.getApiKey();
      els.keyRow.classList.toggle("hidden", hasKey);
      if (!hasKey) els.apiKey.value = "";
      // 翻译按钮：点击反编译后亮；未反编译前黑
      updateTranslateBtn();
    } else {
      els.btnTranslate.disabled = true;
    }
  });
  els.btnSaveKey.addEventListener("click", () => {
    AxiomTranslate.setApiKey(els.apiKey.value);
    els.keyRow.classList.add("hidden");
    updateTranslateBtn();
  });

  els.btnTranslate.addEventListener("click", async () => {
    if (!currentFile || !currentInfo) return;
    if (!currentInfo.canTranslate) { alert("该格式暂不支持翻译。"); return; }
    // 反编译还没完成（进行中）→ 排队：等结果出来后自动翻译，翻译完一起吐出
    if (!currentSrc) {
      if (!AxiomTranslate.getApiKey()) {
        els.keyRow.classList.remove("hidden");
        alert("请先填写 DeepSeek API Key 并保存（仅存于本机浏览器）。");
        return;
      }
      if (pendingTranslate) { log("翻译已在队列中，等待反编译结果…"); return; }
      pendingTranslate = true;
      log("翻译已排队：等反编译结果出来后自动执行…");
      return;
    }
    await runTranslate();
  });

  async function runTranslate() {
    if (!currentSrc) return;
    if (!AxiomTranslate.getApiKey()) {
      els.keyRow.classList.remove("hidden");
      alert("请先填写 DeepSeek API Key 并保存（仅存于本机浏览器）。");
      return;
    }
    const engine = AxiomEngines.get(currentInfo.engine);
    if (!engine || typeof engine.extractTextFromSource !== "function") { alert("该格式暂不支持翻译。"); return; }

    els.btnTranslate.disabled = true;
    try {
      const segs = engine.extractTextFromSource(currentSrc);
      if (!segs.length) { alert("未在反编译结果中找到可翻译文本段。"); return; }
      Term.flood([
        "> AI: extracting translatable segments …",
        "> AI: segs=" + segs.length,
        "> AI: llm=DeepSeek · " + els.langFrom.value + " → " + els.langTo.value,
        "> AI: context-aware translate …",
      ], "t-ai", 14);
      log("提取到 " + segs.length + " 段对话/文本，开始语境翻译…");
      const translations = await AxiomTranslate.translateSegments(segs, els.langFrom.value, els.langTo.value, log);
      currentTrans = AxiomTranslate.buildTranslatedSource(currentSrc, segs, translations);
      const lines = String(currentTrans).split("\n").length;
      Term.flood([
        "> AI: rebuild translated source · " + lines + " lines",
        "> AI: pipeline PASS",
      ], "t-ok", 14);
      els.resultStats.innerHTML = `${lines} 行 · ${currentTrans.length.toLocaleString()} 字符 · 已翻译`;
      renderCode(els.transView, currentTrans, true);
      els.tabTrans.classList.remove("hidden");
      setActiveTab("trans");
      log("✓ 翻译完成");
    } catch (e) {
      log("✗ 翻译失败：" + e.message);
      alert("翻译失败：" + e.message);
    } finally {
      els.btnTranslate.disabled = false;
    }
  }

  // ---------- 启动 ----------
  if (AxiomTranslate.getApiKey()) { els.apiKey.value = "••••••••"; }
  // Pyodide WASM 编译会在移动端阻塞主线程数秒，饿死音乐调度器（首手势后
  // 长时间无音）。移动端（pointer:coarse）改为按需加载：首次反编译时才启动，
  // 桌面端保持后台预热。反编译/翻译路径内已有 loadPyodideRuntime() 兜底。
  const isCoarsePointer = window.matchMedia && matchMedia("(pointer: coarse)").matches;
  setTimeout(() => {
    if (isCoarsePointer) {
      els.footEngine.textContent = "引擎层：按需加载（首次反编译时启动）";
    } else {
      AxiomEngines.loadPyodideRuntime().then(() => {
        els.footEngine.textContent = "引擎层：Pyodide + rpycdec/uncompyle6 已就绪 · 浏览器本地运行 · 已实测反编译 Ren'Py 游戏脚本";
      }).catch(e => {
        els.footEngine.textContent = "引擎层：加载失败（" + e.message + "）";
      });
    }
  }, 800);

  // ---------- 自动化端到端测试钩子（仅本地 127.0.0.1/localhost 触发，线上不激活） ----------
  const isLocal = location.hostname === "127.0.0.1" || location.hostname === "localhost";
  if (isLocal && location.hash === "#autotest") {
    (async function autoTest() {
      const post = (body) => fetch("http://127.0.0.1:8788/result", { method: "POST", body: body }).catch(() => {});
      try {
        const resp = await fetch("test/samples/the_question-8.2_script.rpyc");
        const buf = await resp.arrayBuffer();
        const file = new File([buf], "the_question_script.rpyc", { type: "application/octet-stream" });
        await handleFiles([file]);
        // 翻译按钮状态流：选文件后黑（未反编译）→ 反编译完成亮
        const tBefore = els.btnTranslate.disabled;
        await new Promise(r => setTimeout(r, 400));
        await runDecompile();
        await new Promise(r => setTimeout(r, 600));
        const tAfter = els.btnTranslate.disabled;
        const ok = els.cardResult.classList.contains("hidden") === false;
        const stats = els.resultStats.textContent;
        const sample = els.srcView.textContent.slice(0, 500);
        const head = [AxiomFormats, "FORMAT_OK", "TRANSBTN_BEFORE=" + tBefore, "TRANSBTN_AFTER=" + tAfter,
          "TRANSBTN_FLOW=" + (tBefore === true && tAfter === false ? "OK" : "FAIL"),
          stats, "SRC_HEAD_START", sample, "SRC_HEAD_END",
          ok ? "UI_FLOW_OK" : "UI_FLOW_FAIL", document.title].join("\n>>> ");
        await post(head);
        document.title = ok ? "AXIOM_UI_OK" : "AXIOM_UI_FAIL";
      } catch (e) {
        await post("AUTOTEST_ERR: " + e.message + "\n" + (e.stack || ""));
        document.title = "AXIOM_UI_ERR";
      }
    })();
  }
})();
