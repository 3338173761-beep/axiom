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

  // ---------- 文本段翻译（分批，带语境） ----------
  async function translateSegments(segs, from, to, onLog) {
    const results = new Array(segs.length).fill(null);
    const BATCH = 12;
    for (let i = 0; i < segs.length; i += BATCH) {
      const batch = segs.slice(i, i + BATCH);
      const lines = batch.map((s, j) => `#${i + j + 1} ${s.text}`).join("\n");
      const sys = [
        "你是一名专业的游戏本地化译者。任务：将 Ren'Py 游戏脚本中的对话/文本从",
        from === "en" ? "英文" : "中文",
        "翻译成",
        to === "en" ? "英文" : "中文",
        "。",
        "要求：1) 按角色语气与上下文语境翻译，译文自然，不是逐字机翻；",
        "2) 保留人名、地名、专有名词原文不译；",
        "3) 保留 [xx]、{xx}、{{xx}}、[[xx]] 等插值标签与占位符原样；",
        "4) 严格按输入编号输出，每行一条译文，格式“#编号 译文”，不要输出其他内容。"
      ].join("");
      const prompt = `原文段：\n${lines}`;
      onLog && onLog(`翻译批次 ${Math.floor(i / BATCH) + 1}/${Math.ceil(segs.length / BATCH)}（${batch.length} 段）…`);
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
      // 解析 "#编号 译文"
      const re = /#(\d+)\s+(.+)/g;
      let m;
      while ((m = re.exec(out)) !== null) {
        const idx = parseInt(m[1], 10) - 1;
        if (idx >= i && idx < i + BATCH) results[idx] = m[2].trim();
      }
    }
    return results;
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
      // 保留原始引号风格
      const quote = seg.raw.startsWith('"') ? '"' : "'";
      edits.push({ start: seg.start, end: seg.start + seg.raw.length, text: quote + t.replace(/"/g, '\\"') + quote });
    }
    edits.sort((a, b) => b.start - a.start);
    for (const e of edits) {
      out = out.slice(0, e.start) + e.text + out.slice(e.end);
    }
    return out;
  }

  return { getApiKey, setApiKey, translateSegments, buildTranslatedSource };
})();
