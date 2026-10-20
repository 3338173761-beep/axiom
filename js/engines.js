/* Axiom Web — 引擎适配层（多格式版）
 * 统一引擎接口：每个格式一个适配器，注册进 registry。
 * 全部引擎在浏览器内跑：Pyodide（WASM Python）+ 纯 Python 引擎脚本（E:\Axiom\web\py\ 注入 FS），用户零安装。
 * 已实现：
 *   rpycdec（rpyc/rpymc/rpa/save）、uncompyle6（pyc）
 *   dexparser-free 自研 Dalvik 反汇编器（dex/apk 内 classes.dex → smali）
 *   自研 Java class/jar 解析器 + JVM 字节码反汇编（javap 风格）
 *   dnfile+dncil（.NET dll/exe → CIL IL）
 *   capstone（PE/ELF/Mach-O 原生二进制 → 汇编；.NET 自动分流）
 */
"use strict";

const AxiomEngines = (function () {

  const PYODIDE_VERSION = "v0.28.0";
  const PYODIDE_CDN = `https://cdn.jsdelivr.net/pyodide/${PYODIDE_VERSION}/full/pyodide.js`;
  const PYODIDE_CDN_BACKUP = `https://pyodide-cdn2.iodide.io/${PYODIDE_VERSION}/full/pyodide.js`;
  // 仓库根动态计算：本地根部署("/") 与 GitHub Pages 子路径("/axiom/") 都兼容
  const REPO_BASE = location.pathname.replace(/\/[^\/]*$/, "/");
  const WHEELS_BASE = REPO_BASE + "test/wheels";
  const PY_BASE = REPO_BASE + "py/";

  const registry = {};
  let pyodide = null;
  let pyodideLoadPromise = null;
  let statusListeners = [];

  function setStatus(state, msg) {
    statusListeners.forEach(fn => { try { fn(state, msg); } catch (e) {} });
  }
  function onStatus(fn) { statusListeners.push(fn); }

  // ---------- Pyodide 加载 ----------
  async function loadPyodideRuntime() {
    if (pyodide) return pyodide;
    if (pyodideLoadPromise) return pyodideLoadPromise;
    pyodideLoadPromise = (async () => {
      setStatus("busy", "正在加载 Python 运行时（Pyodide/WASM，约 10MB）…");
      if (!window.loadPyodide) {
        const urls = [PYODIDE_CDN, PYODIDE_CDN_BACKUP];
        let lastErr = null;
        let cdnBase = null;
        for (const u of urls) {
          try {
            await new Promise((res, rej) => {
              const s = document.createElement("script");
              s.src = u; s.onload = res; s.onerror = () => rej(new Error("加载失败 " + u));
              document.head.appendChild(s);
            });
            cdnBase = u.slice(0, u.lastIndexOf("/") + 1);
            break;
          } catch (e) { lastErr = e; }
        }
        if (!window.loadPyodide) throw lastErr || new Error("无法加载 Pyodide");
        pyodide = await window.loadPyodide({ indexURL: cdnBase });
      } else {
        pyodide = await window.loadPyodide({ indexURL: `https://cdn.jsdelivr.net/pyodide/${PYODIDE_VERSION}/full/` });
      }
      setStatus("ready", "Python 运行时已就绪");
      return pyodide;
    })();
    return pyodideLoadPromise;
  }

  // ---------- 包安装 ----------
  async function ensurePackage(pkgName) {
    const p = await loadPyodideRuntime();
    const probe = `import importlib; importlib.import_module(${JSON.stringify(pkgName.split(":")[0])})`;
    try { await p.runPythonAsync(probe); return p; }
    catch (e) {
      setStatus("busy", `正在安装 ${pkgName} 引擎…`);
      await p.loadPackage("micropip");
      const micropip = p.pyimport("micropip");
      await micropip.install(pkgName.split(":")[1] || pkgName);
      setStatus("ready", `${pkgName} 引擎已就绪`);
      return p;
    }
  }

  // 安装本地 wheel 列表（同一次调用，避免重复解析依赖）
  async function ensureLocalWheels(wheelFiles) {
    const p = await loadPyodideRuntime();
    const missing = [];
    for (const w of wheelFiles) {
      const mod = w.mod;
      const probe = `import importlib; importlib.import_module(${JSON.stringify(mod)})`;
      try { await p.runPythonAsync(probe); }
      catch (e) { missing.push(w.file); }
    }
    if (missing.length === 0) return p;
    setStatus("busy", `正在安装引擎依赖（${missing.length} 个本地 wheel）…`);
    await p.loadPackage("micropip");
    const micropip = p.pyimport("micropip");
    const urls = missing.map(f => `${WHEELS_BASE}/${f}`);
    await micropip.install(urls);
    setStatus("ready", "引擎依赖已就绪");
    return p;
  }

  // 注入引擎脚本（fetch 本地 py/*.py → FS /axiom/py/）
  async function loadEngineScripts(p, scriptNames) {
    const pycode = [];
    for (const name of scriptNames) {
      try {
        p.FS.mkdir("/axiom"); p.FS.mkdir("/axiom/py");
      } catch (e) {}
      try { p.FS.mkdir("/axiom/py"); } catch (e) {}
      const resp = await fetch(`${PY_BASE}${name}.py`);
      if (!resp.ok) throw new Error(`引擎脚本 py/${name}.py 加载失败 (HTTP ${resp.status})`);
      const text = await resp.text();
      p.FS.writeFile(`/axiom/py/${name}.py`, text);
      pycode.push(`sys.path.insert(0, "/axiom/py")`);
    }
    await p.runPythonAsync(`
import sys
${pycode.join("\n")}
`);
    return p;
  }

  async function writeInput(p, path, file) {
    const bytes = new Uint8Array(await file.arrayBuffer());
    try { p.FS.mkdir("/axiom"); } catch (e) {}
    p.FS.writeFile(path, bytes);
    return bytes.length;
  }

  // ---------- JS 端 PE/.NET 快速检测 ----------
  function detectPeKind(bytes) {
    // 返回 'dotnet' | 'native' | null
    if (bytes.length < 0x40 || bytes[0] !== 0x4D || bytes[1] !== 0x5A) return null;
    const peOff = bytes[0x3C] | (bytes[0x3D] << 8) | (bytes[0x3E] << 16) | (bytes[0x3F] << 24);
    if (peOff + 6 > bytes.length) return null;
    if (bytes[peOff] !== 0x50 || bytes[peOff + 1] !== 0x45) return null;
    const magic = bytes[peOff + 24] | (bytes[peOff + 25] << 8);
    let clrOff;
    if (magic === 0x20B) clrOff = peOff + 24 + 112 + 14 * 8;
    else if (magic === 0x10B) clrOff = peOff + 24 + 96 + 14 * 8;
    else return "native";
    const rva = (bytes[clrOff] | (bytes[clrOff + 1] << 8) | (bytes[clrOff + 2] << 16) | (bytes[clrOff + 3] << 24)) >>> 0;
    const size = (bytes[clrOff + 4] | (bytes[clrOff + 5] << 8) | (bytes[clrOff + 6] << 16) | (bytes[clrOff + 7] << 24)) >>> 0;
    return (rva > 0 && size > 0) ? "dotnet" : "native";
  }

  // =========================================================
  // rpycdec 引擎：rpyc / rpymc / rpa / save
  // =========================================================
  async function rpycDecode(file, onLog) {
    const p = await ensurePackage("rpycdec");
    const n = await writeInput(p, "/axiom/input.rpyc", file);
    onLog && onLog("已写入输入文件（" + (n / 1024).toFixed(1) + " KB）");
    onLog && onLog("开始反编译…");
    const py = `
from rpycdec import decompile as _d
_d("/axiom/input.rpyc")
with open("/axiom/input.rpy", "r", encoding="utf-8") as f:
    text = f.read()
text
`;
    try {
      const result = await p.runPythonAsync(py);
      onLog && onLog("反编译完成");
      return String(result);
    } catch (e) {
      onLog && onLog("反编译失败：" + e.message);
      throw new Error("rpycdec 反编译失败：" + e.message);
    }
  }

  async function rpaExtract(file, onLog) {
    const p = await ensurePackage("rpycdec");
    const n = await writeInput(p, "/axiom/input.rpa", file);
    onLog && onLog("已写入归档（" + (n / 1024).toFixed(1) + " KB）");
    onLog && onLog("开始解包…");
    const py = `
import io, os
from rpycdec import extract_rpa
outdir = "/axiom/rpa_out"
try:
    os.makedirs(outdir)
except Exception:
    pass
with open("/axiom/input.rpa", "rb") as f:
    data = f.read()
extract_rpa(io.BytesIO(data), outdir)
files = []
for root, dirs, names in os.walk(outdir):
    for name in names:
        fp = os.path.join(root, name)
        files.append((os.path.relpath(fp, outdir), os.path.getsize(fp)))
files.sort()
lines = ["共解包出 %d 个文件：" % len(files)]
for rel, size in files[:80]:
    lines.append("- %s (%d bytes)" % (rel, size))
if len(files) > 80:
    lines.append("… 其余 %d 个省略" % (len(files) - 80))
preview = []
for rel, size in files[:8]:
    if rel.endswith((".rpy", ".txt", ".json", ".xml", ".py", ".log", ".csv")):
        try:
            with open(os.path.join(outdir, rel), "r", encoding="utf-8", errors="replace") as f:
                head = f.read(400)
            preview.append("\\n--- %s ---\\n%s" % (rel, head))
        except Exception:
            pass
if preview:
    lines.append("\\n===== 文本预览 =====")
    lines.extend(preview)
"\\n".join(lines)
`;
    try {
      const result = await p.runPythonAsync(py);
      onLog && onLog("解包完成");
      return String(result);
    } catch (e) {
      onLog && onLog("解包失败：" + e.message);
      throw new Error("rpa 解包失败：" + e.message);
    }
  }

  // =========================================================
  // uncompyle6 引擎：pyc
  // =========================================================
  async function pycDecode(file, onLog) {
    const p = await ensurePackage("uncompyle6");
    const n = await writeInput(p, "/axiom/input.pyc", file);
    onLog && onLog("已写入字节码文件（" + (n / 1024).toFixed(1) + " KB）");
    onLog && onLog("开始反编译（uncompyle6）…");
    const py = `
import io
from uncompyle6.main import decompile_file
buf = io.StringIO()
try:
    decompile_file("/axiom/input.pyc", buf)
    text = buf.getvalue()
except Exception as e:
    text = "uncompyle6 失败: %s" % e
text
`;
    try {
      const result = await p.runPythonAsync(py);
      onLog && onLog("反编译完成");
      return String(result);
    } catch (e) {
      onLog && onLog("反编译失败：" + e.message);
      throw new Error("pyc 反编译失败：" + e.message);
    }
  }

  // =========================================================
  // DEX 引擎：classes.dex → smali（自研 Dalvik 反汇编器）
  // =========================================================
  async function dexDecode(file, onLog) {
    const p = await loadEngineScripts(await loadPyodideRuntime(), ["dalvik_smali"]);
    const n = await writeInput(p, "/axiom/input.dex", file);
    onLog && onLog("已写入 DEX（" + (n / 1024).toFixed(1) + " KB）");
    onLog && onLog("开始反汇编（自研 Dalvik 引擎）…");
    const py = `
import sys
sys.path.insert(0, "/axiom/py")
import dalvik_smali
with open("/axiom/input.dex", "rb") as f:
    data = f.read()
dalvik_smali.decompile_dex(data)
`;
    try {
      const result = await p.runPythonAsync(py);
      onLog && onLog("反汇编完成");
      return String(result);
    } catch (e) {
      onLog && onLog("反汇编失败：" + e.message);
      throw new Error("DEX 反汇编失败：" + e.message);
    }
  }

  // =========================================================
  // APK 引擎：解包 + 清单 + classes.dex smali
  // =========================================================
  async function apkDecode(file, onLog) {
    const p = await loadEngineScripts(await loadPyodideRuntime(), ["apk_tool", "dalvik_smali"]);
    const n = await writeInput(p, "/axiom/input.apk", file);
    onLog && onLog("已写入 APK（" + (n / 1024).toFixed(1) + " KB）");
    onLog && onLog("开始解析…");
    // 尝试装 apkInspector（清单解析，可选）
    try {
      await ensureLocalWheels([{ file: "asn1crypto-1.5.1-py2.py3-none-any.whl", mod: "asn1crypto" },
                               { file: "apkinspector-1.3.7-py3-none-any.whl", mod: "apk_inspector" }]);
    } catch (e) { onLog && onLog("apkInspector 不可用（清单解析降级）：" + e.message); }
    const py = `
import sys
sys.path.insert(0, "/axiom/py")
import apk_tool
with open("/axiom/input.apk", "rb") as f:
    data = f.read()
apk_tool.decompile_apk(data, "input.apk")
`;
    try {
      const result = await p.runPythonAsync(py);
      onLog && onLog("解析完成");
      return String(result);
    } catch (e) {
      onLog && onLog("解析失败：" + e.message);
      throw new Error("APK 解析失败：" + e.message);
    }
  }

  // =========================================================
  // Java 引擎：class / jar → 结构 + JVM 字节码（自研）
  // =========================================================
  async function javaDecode(file, onLog) {
    const p = await loadEngineScripts(await loadPyodideRuntime(), ["java_class"]);
    const lower = file.name.toLowerCase();
    const path = lower.endsWith(".jar") ? "/axiom/input.jar" : "/axiom/input.class";
    const n = await writeInput(p, path, file);
    onLog && onLog("已写入 " + (lower.endsWith(".jar") ? "JAR" : "CLASS") + "（" + (n / 1024).toFixed(1) + " KB）");
    onLog && onLog("开始解析（自研 Java 引擎）…");
    const isJar = lower.endsWith(".jar");
    const py = `
import sys
sys.path.insert(0, "/axiom/py")
import java_class
with open(${JSON.stringify(path)}, "rb") as f:
    data = f.read()
if ${isJar ? "True" : "False"}:
    out = java_class.decompile_java(data, ${JSON.stringify(file.name)})
else:
    out = java_class.decompile_java_class(data, ${JSON.stringify(file.name)})
out
`;
    try {
      const result = await p.runPythonAsync(py);
      onLog && onLog("解析完成");
      return String(result);
    } catch (e) {
      onLog && onLog("解析失败：" + e.message);
      throw new Error("Java 解析失败：" + e.message);
    }
  }

  // =========================================================
  // .NET 引擎：dll/exe(.NET) → CIL（dnfile + dncil）
  // =========================================================
  async function dotnetDecode(file, onLog) {
    const p = await ensureLocalWheels([
      { file: "pefile-2024.8.26-py3-none-any.whl", mod: "pefile" },
      { file: "dnfile-0.18.0-py3-none-any.whl", mod: "dnfile" },
      { file: "dncil-1.0.2-py3-none-any.whl", mod: "dncil" }
    ]);
    await loadEngineScripts(p, ["dotnet_il"]);
    const n = await writeInput(p, "/axiom/input.dll", file);
    onLog && onLog("已写入程序集（" + (n / 1024).toFixed(1) + " KB）");
    onLog && onLog("开始反汇编（dnfile + dncil）…");
    const py = `
import sys, os, tempfile
sys.path.insert(0, "/axiom/py")
import dotnet_il
with open("/axiom/input.dll", "rb") as f:
    data = f.read()
dotnet_il.decompile_dotnet(data, ${JSON.stringify(file.name)})
`;
    try {
      const result = await p.runPythonAsync(py);
      onLog && onLog("反汇编完成");
      return String(result);
    } catch (e) {
      onLog && onLog("反汇编失败：" + e.message);
      throw new Error(".NET 反汇编失败：" + e.message);
    }
  }

  // =========================================================
  // 原生二进制引擎：PE/ELF/Mach-O → 汇编（capstone）
  // =========================================================
  async function binDecode(file, onLog) {
    const p = await loadPyodideRuntime();
    // 说明：capstone 无 Pyodide wheel，浏览器内由 bin_disasm.py 内部自动回退到自研 x86 解码器；
    // 本地/桌面端（有 capstone）时自动使用 capstone，输出更完整。
    setStatus("busy", "正在加载二进制反汇编引擎…");
    await loadEngineScripts(p, ["bin_disasm", "x86_disasm"]);
    const n = await writeInput(p, "/axiom/input.bin", file);
    onLog && onLog("已写入二进制（" + (n / 1024).toFixed(1) + " KB）");
    onLog && onLog("开始反汇编（capstone 优先 / 自研回退）…");
    const py = `
import sys
sys.path.insert(0, "/axiom/py")
import bin_disasm
with open("/axiom/input.bin", "rb") as f:
    data = f.read()
bin_disasm.decompile_binary(data, ${JSON.stringify(file.name)})
`;
    try {
      const result = await p.runPythonAsync(py);
      onLog && onLog("反汇编完成");
      return String(result);
    } catch (e) {
      onLog && onLog("反汇编失败：" + e.message);
      throw new Error("二进制反汇编失败：" + e.message);
    }
  }

  // PE 分流：.NET → dotnet 引擎；原生 → bin 引擎
  async function peDecode(file, onLog) {
    const bytes = new Uint8Array(await file.arrayBuffer());
    const kind = detectPeKind(bytes);
    onLog && onLog("检测到 " + (kind === "dotnet" ? ".NET CLR 程序集" : "原生 PE 二进制"));
    if (kind === "dotnet") return dotnetDecode(file, onLog);
    return binDecode(file, onLog);
  }

  // ---------- 注册 ----------
  function register(id, engine) { registry[id] = engine; }
  function get(id) { return registry[id] || null; }

  // ---------- 内置引擎 ----------
  register("rpycdec", {
    id: "rpycdec",
    label: "rpycdec（浏览器内 WASM）",
    canTranslate: true,
    formats: ["rpyc", "rpymc", "save"],
    decompile: rpycDecode,
    extractTextFromSource: function (src) {
      const segs = [];
      const re = /"((?:[^"\\]|\\.)*)"/g;
      let m;
      while ((m = re.exec(src)) !== null) {
        const text = m[1].replace(/\\(.)/g, "$1");
        if (text.trim().length > 0) segs.push({ raw: m[0], text, start: m.index });
      }
      return segs;
    }
  });

  register("rpa", {
    id: "rpa",
    label: "rpycdec.extract_rpa（浏览器内 WASM）",
    canTranslate: false,
    formats: ["rpa"],
    decompile: rpaExtract
  });

  register("pyc", {
    id: "pyc",
    label: "uncompyle6（浏览器内 WASM）",
    canTranslate: false,
    formats: ["pyc"],
    decompile: pycDecode
  });

  register("dex", {
    id: "dex",
    label: "自研 Dalvik 反汇编器（浏览器内）",
    canTranslate: false,
    formats: ["dex"],
    decompile: dexDecode
  });

  register("apk", {
    id: "apk",
    label: "APK 解析（解包+清单+DEX→smali，浏览器内）",
    canTranslate: false,
    formats: ["apk", "aab", "xapk"],
    decompile: apkDecode
  });

  register("java", {
    id: "java",
    label: "自研 Java 引擎（class/jar 结构+JVM 字节码，浏览器内）",
    canTranslate: false,
    formats: ["class", "jar"],
    decompile: javaDecode
  });

  register("dotnet", {
    id: "dotnet",
    label: "dnfile+dncil（.NET → CIL，浏览器内）",
    canTranslate: false,
    formats: ["dll", "exe"],
    decompile: peDecode
  });

  register("bin", {
    id: "bin",
    label: "capstone（PE/ELF/Mach-O 原生二进制 → 汇编，浏览器内）",
    canTranslate: false,
    formats: ["exe", "dll", "so", "elf", "bin", "o"],
    decompile: binDecode
  });

  // =========================================================
  // RAR 引擎：node-unrar-js WASM（官方 UnRAR C++ 编译）
  // 资源：test/unrar/（index.esm.js + js/unrar.js + js/unrar.wasm）
  // =========================================================
  let rarModulePromise = null;
  async function loadRarModule() {
    if (rarModulePromise) return rarModulePromise;
    rarModulePromise = (async () => {
      setStatus("busy", "正在加载 RAR 解压引擎（UnRAR WASM，约 200KB）…");
      const base = REPO_BASE + "test/unrar/";
      const wasmResp = await fetch(base + "js/unrar.wasm");
      if (!wasmResp.ok) throw new Error("unrar.wasm 加载失败 (HTTP " + wasmResp.status + ")");
      const wasmBinary = await wasmResp.arrayBuffer();
      const mod = await import(base + "index.esm.js");
      setStatus("ready", "RAR 引擎已就绪");
      return { wasmBinary, mod };
    })();
    return rarModulePromise;
  }

  async function rarDecode(file, onLog) {
    const { wasmBinary, mod } = await loadRarModule();
    const n = file.size;
    onLog && onLog("已读取 RAR（" + (n / 1024).toFixed(1) + " KB）");
    onLog && onLog("开始解包（官方 UnRAR WASM）…");
    try {
      const data = await file.arrayBuffer();
      const extractor = await mod.createExtractorFromData({ wasmBinary, data });
      const list = extractor.getFileList();
      const headers = [...list.fileHeaders];
      const lines = ["RAR 解包完成：共 " + headers.length + " 个文件（" + file.name + "）"];
      for (const h of headers) {
        lines.push("- " + (h.name || "(无名)") + " (" + h.unpSize + " B, " + (h.method || "") + ")" + (h.flags && h.flags.directory ? " [目录]" : ""));
      }
      const extracted = extractor.extract();
      const files = [...extracted.files];
      lines.push("", "===== 文本预览 =====");
      let shown = 0;
      for (const f of files) {
        if (!f.extraction) continue;
        if (f.fileHeader && f.fileHeader.flags && f.fileHeader.flags.directory) continue;
        if (shown >= 8) break;
        const name = f.fileHeader.name || "file";
        // 仅预览可读文本
        if (/\.(txt|md|json|xml|ini|log|cfg|conf|yaml|yml|srt|lrc|ass|ssa|py|js|ts|html|css|csv|po|pot|rpy|ust|vsqx|svp|ps1|sh|bat|cmd)(\.|$)/i.test(name)) {
          const dec = new TextDecoder("utf-8");
          const head = dec.decode(f.extraction.slice(0, 400)).replace(/\n/g, "\\n");
          lines.push("\n--- " + name + " ---\n" + head);
          shown++;
        }
      }
      onLog && onLog("解包完成");
      return lines.join("\n");
    } catch (e) {
      onLog && onLog("解包失败：" + e.message);
      throw new Error("RAR 解包失败：" + e.message);
    }
  }

  // =========================================================
  // 7z 引擎：自研解析器（LZMA/LZMA2/Deflate/BZip2/Copy/ZSTD/BCJ 链式）
  // =========================================================
  async function sevenzDecode(file, onLog) {
    const p = await loadPyodideRuntime();
    setStatus("busy", "正在加载 7z 解压引擎…");
    await loadEngineScripts(p, ["sevenz"]);
    // lzma 模块（LZMA/LZMA2 必需）——Pyodide 里是独立包，需显式加载
    try {
      await p.loadPackage("lzma");
      onLog && onLog("lzma 已就绪（支持 LZMA/LZMA2 方法）");
    } catch (e) {
      onLog && onLog("lzma 不可用（LZMA/LZMA2 压缩的 7z 将降级）：" + e.message);
    }
    // 可选：zstandard（Pyodide 官方包）——ZSTD 压缩的 7z 才需要
    try {
      await p.loadPackage("zstandard");
      onLog && onLog("zstandard 已就绪（支持 ZSTD 方法）");
    } catch (e) {
      onLog && onLog("zstandard 不可用（ZSTD 压缩的 7z 将降级）：" + e.message);
    }
    const n = await writeInput(p, "/axiom/input.7z", file);
    onLog && onLog("已写入 7z（" + (n / 1024).toFixed(1) + " KB）");
    onLog && onLog("开始解包（自研 7z 解析器）…");
    const py = `
import sys
sys.path.insert(0, "/axiom/py")
import sevenz
with open("/axiom/input.7z", "rb") as f:
    data = f.read()
sevenz.decompile_7z(data, ${JSON.stringify(file.name)})
`;
    try {
      const result = await p.runPythonAsync(py);
      onLog && onLog("解包完成");
      return String(result);
    } catch (e) {
      onLog && onLog("解包失败：" + e.message);
      throw new Error("7z 解包失败：" + e.message);
    }
  }

  // =========================================================
  // text 引擎：纯文本/脚本/标记/歌词/字幕 → 浏览器直读 + AI 语境翻译
  // =========================================================
  async function textDecode(file, onLog) {
    onLog && onLog("读取文本内容…");
    const text = await file.text();
    onLog && onLog("读取完成（" + (text.length / 1024).toFixed(1) + " KB）");
    return text;
  }

  function extractTextSegments(src) {
    // 按行提取可翻译段：非空、含字母/汉字、非纯符号数字
    const segs = [];
    const lines = String(src).split("\n");
    let pos = 0;
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const t = line.trim();
      if (t.length >= 2 && /[A-Za-z\u4e00-\u9fff]/.test(t) && !/^[\s\d\W_]+$/.test(t)) {
        segs.push({ raw: line, text: t, start: pos, plain: true });
      }
      pos += line.length + 1;
    }
    return segs;
  }

  register("rar", {
    id: "rar",
    label: "node-unrar-js（官方 UnRAR WASM，浏览器内）",
    canTranslate: false,
    formats: ["rar"],
    decompile: rarDecode
  });

  register("sevenz", {
    id: "sevenz",
    label: "自研 7z 解析器（LZMA/LZMA2/Deflate/BZip2/Copy/ZSTD/BCJ，浏览器内）",
    canTranslate: false,
    formats: ["7z"],
    decompile: sevenzDecode
  });

  register("text", {
    id: "text",
    label: "通用文本引擎（浏览器直读 + AI 语境翻译）",
    canTranslate: true,
    formats: ["txt", "log", "md", "csv", "json", "xml", "srt", "lrc", "ps1", "rpy", "py", "js", "ts", "html", "css"],
    decompile: textDecode,
    extractTextFromSource: extractTextSegments
  });

  return { loadPyodideRuntime, ensurePackage, register, get, ids: () => Object.keys(registry), onStatus };
})();
