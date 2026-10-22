/* Axiom Web — 语境翻译模块（DeepSeek API）
 * 从反编译源码提取文本段 → 按语境翻译（非机翻）→ 回填生成翻译版源码。
 * API Key 在界面填写，保存在 localStorage（仅本机）。
 */
"use strict";

const AxiomTranslate = (function () {

  const KEY_STORE = "axiom.deepseek.key";
  const API_URL = "https://api.deepseek.com/v1/chat/completions";
  const MODEL = "deepseek-chat";

  function getApiKey() { return localStorage.getItem(KEY_STORE) || ""; }
  function setApiKey(k) { localStorage.setItem(KEY_STORE, (k || "").trim()); }

  // ---------- DeepSeek 调用 ----------
  async function callDeepSeek(messages, onLog) {
    const key = getApiKey();
    if (!key) throw new Error("未配置 DeepSeek API Key");
    const resp = await fetch(API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + key
      },
      body: JSON.stringify({
        model: MODEL,
        messages: messages,
        temperature: 0.3,
        max_tokens: 4096,
        stream: false
      })
    });
    if (!resp.ok) {
      let detail = "";
      try { detail = (await resp.json()).error?.message || ""; } catch (e) {}
      throw new Error("DeepSeek 返回 " + resp.status + (detail ? "：" + detail : ""));
    }
    const data = await resp.json();
    return data.choices?.[0]?.message?.content || "";
  }

  // ---------- 文本段翻译（分批，带语境；同语言=用户对现有译文不满意→二次润色重译） ----------
  const LANG_NAMES = { zh: "中文", en: "英文", ja: "日文" };

  async function translateSegments(segs, from, to, onLog) {
    const results = new Array(segs.length).fill(null);
    const BATCH = 12;
    // 同语言（或源为自动时目标语言）：视为"重译润色"，不是原样返回
    const sameLang = from !== "auto" && from === to;
    const targetName = LANG_NAMES[to] || to || "中文";
    const sourceName = from === "auto" ? "原文" : (LANG_NAMES[from] || from);
    for (let i = 0; i < segs.length; i += BATCH) {
      const batch = segs.slice(i, i + BATCH);
      const lines = batch.map((s, j) => `#${i + j + 1} ${s.text}`).join("\n");
      let sys;
      if (sameLang) {
        sys = "你是一名专业的游戏本地化译者。用户对现有【" + targetName + "】译文不满意，要求你把以下文本重新翻译成更优质的" + targetName + "（重译+润色，而不是原样返回）：" +
          "要求：1) 深入理解语境后重译，表达更自然、地道、流畅，明显优于原翻译；" +
          "2) 保留人名、地名、专有名词与发音标记原文；" +
          "3) 保留 [xx]、{xx}、{{xx}}、[[xx]] 等插值标签与占位符原样；" +
          "4) 严格按输入编号输出，每行一条译文，格式“#编号 译文”，不要输出其他内容。";
      } else {
        sys = "你是一名专业的游戏本地化译者。任务：将游戏脚本中的对话/文本从" + sourceName + "翻译成" + targetName + "。" +
          "要求：1) 按角色语气与上下文语境翻译，译文自然，不是逐字机翻；" +
          "2) 保留人名、地名、专有名词原文不译；" +
          "3) 保留 [xx]、{xx}、{{xx}}、[[xx]] 等插值标签与占位符原样；" +
          "4) 严格按输入编号输出，每行一条译文，格式“#编号 译文”，不要输出其他内容。";
      }
      const prompt = `原文段：\n${lines}`;
      onLog && onLog(`翻译批次 ${Math.floor(i / BATCH) + 1}/${Math.ceil(segs.length / BATCH)}（${batch.length} 段）${sameLang ? " · 二次润色模式" : ""}…`);
      let out;
      try {
        out = await callDeepSeek([
          { role: "system", content: sys },
          { role: "user", content: prompt }
        ], onLog);
      } catch (e) {
        onLog && onLog("翻译失败：" + e.message);
        throw e;
      }
      // Parse "#N text". A translation may legally wrap onto several lines, so a
      // line without its own "#N" prefix continues the previous index. The old
      // regex /#(\d+)\s+(.+)/g dropped every continuation line silently.
      let lastIdx = -1;
      for (const rawLine of String(out).split(/\r?\n/)) {
        const m = /^#\s*(\d+)\s(.*)$/.exec(rawLine);
        if (m) {
          const idx = parseInt(m[1], 10) - 1;
          if (idx >= i && idx < i + batch.length) { results[idx] = m[2]; lastIdx = idx; }
          else { lastIdx = -1; }
        } else if (lastIdx >= 0 && rawLine.trim() !== "") {
          results[lastIdx] += "\n" + rawLine;
        }
      }
    }
    // Anything the model failed to return must be reported, never dropped quietly:
    // a half-translated script file used to look like a finished job.
    const missing = [];
    for (let k = 0; k < segs.length; k++) { if (results[k] == null) missing.push(k + 1); }
    results.missing = missing;
    return results;
  }

  // Rebuild a string literal from translated text, preserving the original quote
  // style. Backslash must be escaped first, then the active quote, then line
  // breaks. The previous code escaped only '"' regardless of the quote in use, so
  // an apostrophe in a single-quoted literal (e.g. "don't") produced broken
  // source, and a newline in the translation broke the literal outright.
  function toLiteral(text, quote) {
    let s = String(text).replace(/\\/g, "\\\\").replace(/\r/g, "");
    s = s.replace(/\n/g, "\\n");
    s = quote === "'" ? s.replace(/'/g, "\\'") : s.replace(/"/g, '\\"');
    return quote + s + quote;
  }

  // ---------- 回填：生成翻译版源码 ----------
  function buildTranslatedSource(src, segs, translations) {
    // 从后往前替换，避免偏移错乱
    let out = src;
    const edits = [];
    for (let i = 0; i < segs.length; i++) {
      const t = translations[i];
      if (t == null) continue;
      const seg = segs[i];
      if (seg.plain) {
        // 纯文本段（text 引擎）：直接替换整行，不加引号
        edits.push({ start: seg.start, end: seg.start + seg.raw.length, text: String(t).replace(/\r/g, "") });
        continue;
      }
      // 保留原始引号风格（rpyc 等源码段）
      const quote = seg.raw.startsWith('"') ? '"' : "'";
      edits.push({ start: seg.start, end: seg.start + seg.raw.length, text: toLiteral(t, quote) });
    }
    edits.sort((a, b) => b.start - a.start);
    for (const e of edits) {
      out = out.slice(0, e.start) + e.text + out.slice(e.end);
    }
    return out;
  }

  return { getApiKey, setApiKey, translateSegments, buildTranslatedSource };
})();
