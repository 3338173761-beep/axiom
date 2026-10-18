/* Axiom Web — 格式识别（扩展名 + 文件头魔数） */
"use strict";

const AxiomFormats = (function () {

  // ---- 魔数表 ----
  const MAGIC = {
    rpyc: [[0x78, 0x01], [0x78, 0x5e], [0x78, 0x9c], [0x78, 0xda]],   // zlib 头（Ren'Py 8 编译脚本）
    rpa: [[0x52, 0x45, 0x4e, 0x50, 0x59, 0x20, 0x52, 0x50, 0x41]],   // "RENPY RPA"
    dex: [[0x64, 0x65, 0x78, 0x0a, 0x30, 0x33, 0x35]],               // "dex\n035"
    class: [[0xca, 0xfe, 0xba, 0xbe]],                               // Java class
    zip: [[0x50, 0x4b, 0x03, 0x04]],                                 // zip（apk/jar）
    pe: [[0x4d, 0x5a]],                                             // MZ（exe/dll）
    elf: [[0x7f, 0x45, 0x4c, 0x46]],                                 // ELF
  };
  // Python 字节码版本魔数（magic 低 2 字节）
  const PYC_MAGIC = { 0x0d0a0d0a: "py3 (3.x)", 0x610d0d0a: "3.12", 0xab0d0d0a: "3.13", 0xa70d0d0a: "3.11", 0x6f0d0d0a: "3.8+" };

  function startsWith(bytes, magic) {
    if (bytes.length < magic.length) return false;
    for (let i = 0; i < magic.length; i++) if (bytes[i] !== magic[i]) return false;
    return true;
  }

  // ---- 格式元数据（含 UI 徽章） ----
  const META = {
    rpyc: {
      id: "rpyc", label: "Ren'Py 编译脚本", ext: ".rpyc / .rpymc", engine: "rpycdec",
      canTranslate: true,
      badge: { ch: "R", color: "#22d3ee" },
      desc: "Ren'Py 视觉小说引擎的编译脚本，内含剧情与角色对话。rpycdec 可还原为 .rpy 源码。",
      icon: "▣",
    },
    rpa: {
      id: "rpa", label: "Ren'Py 资源归档", ext: ".rpa", engine: "rpa",
      canTranslate: false,
      badge: { ch: "A", color: "#60a5fa" },
      desc: "Ren'Py 游戏的资源打包（脚本/图片/音频）。可解包出内部文件清单。",
      icon: "▤",
    },
    pyc: {
      id: "pyc", label: "Python 字节码", ext: ".pyc / .pyo", engine: "pyc",
      canTranslate: false,
      badge: { ch: "P", color: "#34d399" },
      desc: "Python 编译后的字节码文件，uncompyle6 可反编译为可读 Python 源码。",
      icon: "◈",
    },
    dex: {
      id: "dex", label: "Android DEX", ext: ".dex", engine: "dex",
      canTranslate: false,
      badge: { ch: "D", color: "#a78bfa" },
      desc: "Android 可执行字节码。浏览器内由自研 Dalvik 反汇编器还原为 smali 汇编。",
      icon: "⬒",
    },
    apk: {
      id: "apk", label: "Android 安装包", ext: ".apk / .aab / .xapk", engine: "apk",
      canTranslate: false,
      badge: { ch: "K", color: "#fbbf24" },
      desc: "Android 应用安装包（zip 容器）。浏览器内解包 + 解析清单 + classes.dex 反汇编为 smali。",
      icon: "▣",
    },
    jar: {
      id: "jar", label: "Java 归档 / Class", ext: ".jar / .class", engine: "java",
      canTranslate: false,
      badge: { ch: "J", color: "#f87171" },
      desc: "Java 字节码归档。浏览器内由自研引擎解析常量池/字段/方法并反汇编 JVM 字节码。",
      icon: "▧",
    },
    binary: {
      id: "binary", label: "原生二进制", ext: ".exe / .dll / .so / ELF", engine: "dotnet",
      canTranslate: false,
      badge: { ch: "B", color: "#94a3b8" },
      desc: "PE/ELF/Mach-O 可执行文件。.NET 程序集走 dnfile+dncil（CIL），原生二进制走 capstone 汇编。",
      icon: "▮",
    },
    unknown: {
      id: "unknown", label: "未知格式", ext: "?", engine: "none",
      canTranslate: false,
      badge: { ch: "?", color: "#94a3b8" },
      desc: "未识别的文件类型。当前版本已支持 Ren'Py / Python / Java 系，更多格式持续接入。",
      icon: "？",
    },
  };

  // ---- 识别 ----
  async function identify(file) {
    const size = file.size;
    const head = new Uint8Array(await file.slice(0, 16).arrayBuffer());
    const ext = (file.name.split(".").pop() || "").toLowerCase();
    const hex = Array.from(head.slice(0, 8)).map(b => b.toString(16).padStart(2, "0")).join(" ").toUpperCase();

    let id = null;

    // 魔数优先
    if (startsWith(head, MAGIC.dex[0])) id = "dex";
    else if (startsWith(head, MAGIC.class[0])) id = "jar";           // class 归入 jar 组
    else if (startsWith(head, MAGIC.rpa[0])) id = "rpa";
    else if (startsWith(head, MAGIC.elf[0])) id = "binary";
    else if (startsWith(head, MAGIC.pe[0])) id = "binary";
    else if (startsWith(head, MAGIC.zip[0])) {
      if (ext === "apk" || ext === "aab" || ext === "xapk") id = "apk";
      else id = "jar";
    }
    else if (MAGIC.rpyc.some(m => startsWith(head, m))) id = "rpyc";
    else if (ext === "pyc" || ext === "pyo") id = "pyc";

    // 扩展名兜底
    if (!id) {
      if (ext === "rpyc" || ext === "rpymc") id = "rpyc";
      else if (ext === "rpa") id = "rpa";
      else if (ext === "pyc" || ext === "pyo") id = "pyc";
      else if (ext === "dex") id = "dex";
      else if (ext === "apk" || ext === "aab" || ext === "xapk") id = "apk";
      else if (ext === "jar" || ext === "class") id = "jar";
      else if (ext === "exe" || ext === "dll" || ext === "so" || ext === "elf" || ext === "o" || ext === "bin") id = "binary";
      else id = "unknown";
    }

    const meta = META[id];
    return Object.assign({}, meta, {
      ext: ext || "(无扩展名)",
      size,
      headHex: hex,
      magicNote: id === "pyc" ? "Python 字节码（magic 0x" + Array.from(head.slice(0, 4)).map(b => b.toString(16).padStart(2, "0")).join("") + "）" : "",
    });
  }

  function list() { return Object.values(META); }

  return { identify, list, MAGIC };
})();
