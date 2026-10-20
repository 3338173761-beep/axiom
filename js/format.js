/* Axiom Web — 格式识别（扩展名 + 文件头魔数 + 627 全格式表） */
"use strict";

const AxiomFormats = (function () {

  // ---- 627 全格式表（由调研自动生成，format-data.js 注入） ----
  const EXT_TABLE = (typeof window !== "undefined" && window.AXIOM_FORMAT_TABLE) || {};
  const AMBIGUOUS = (typeof window !== "undefined" && window.AXIOM_AMBIGUOUS) || [];

  // 已有完整引擎的格式（直接路由到现有引擎）
  const KNOWN_ENGINE = { rpyc: "rpycdec", rpymc: "rpycdec", rpa: "rpa", pyc: "pyc", pyo: "pyc",
    dex: "dex", apk: "apk", aab: "apk", xapk: "apk", jar: "java", class: "java",
    exe: "dotnet", dll: "dotnet", so: "dotnet", elf: "dotnet", o: "dotnet", bin: "dotnet", wasm: "dotnet", msi: "dotnet", sys: "dotnet",
    "7z": "sevenz", rar: "rar",
    // 综合归档引擎（tar 家族 / 单文件压缩 / 编码 / 旧式归档）
    tar: "archive", tgz: "archive", tbz2: "archive", txz: "archive", tzst: "archive",
    zip: "archive", gz: "archive", bz2: "archive", xz: "archive", lzma: "archive",
    zst: "archive", br: "archive", lz4: "archive", uue: "archive",
    ar: "archive", cpio: "archive", deb: "archive",
    // 文档引擎（zip 容器 → 文本提取 → 可翻译；doc/dot OLE → 启发式文本提取）
    doc: "doc", dot: "doc",
    docx: "doc", docm: "doc", dotx: "doc", dotm: "doc",
    xlsx: "doc", xlsm: "doc", xltx: "doc", xltm: "doc",
    pptx: "doc", pptm: "doc", potx: "doc",
    odt: "doc", ott: "doc", odm: "doc", ods: "doc", ots: "doc", odp: "doc", otp: "doc",
    epub: "doc", rtf: "doc",
    // 歌声工程引擎（歌词块提取 → 可翻译）
    ust: "voice", uproject: "voice", ufdata: "voice",
    vsqx: "voice", vsq: "voice", vpr: "voice",
    svp: "voice", s5p: "voice",
    dv: "voice", dva: "voice", dvpp: "voice",
    ccs: "voice", ccsi: "voice",
    mid: "voice", midi: "voice", smf: "voice" };

  // 纯文本类格式 → text 引擎（浏览器直读 + AI 语境翻译）：
  // 调研分级"翻译"的 125 个 + 常见纯文本/脚本/工程文件
  const TEXT_EXTS = new Set();
  (function buildTextExts() {
    for (const ext in EXT_TABLE) {
      if (EXT_TABLE[ext].lvl === "翻译") TEXT_EXTS.add(ext);
    }
    // 补充常见纯文本/标记/脚本/配置/歌词/字幕（部分在"解析/解包"级但可直接读文本）
    const more = ["txt", "log", "md", "csv", "tsv", "json", "xml", "ini", "conf", "cfg", "yaml", "yml",
      "srt", "sub", "lrc", "ass", "ssa", "vtt", "html", "htm", "xhtml", "css", "js", "mjs", "ts",
      "py", "rpy", "java", "c", "h", "cpp", "hpp", "cs", "go", "rs", "php", "rb", "pl", "sh", "bat",
      "cmd", "ps1", "lua", "sql", "toml", "properties", "env", "gitignore", "dockerfile", "makefile",
      "tex", "latex", "texinfo", "man", "info", "pod", "rtf", "csv", "tsv", "nfo", "diz", "readme",
      "html", "htm", "xhtml", "svg", "graphql", "gql", "proto", "kt", "kts", "swift", "m", "mm",
      "scala", "clj", "ex", "exs", "erl", "hrl", "hs", "ml", "lisp", "cl", "scm", "r", "jl", "dart",
      "vue", "jsx", "tsx", "svelte", "astro", "ipynb", "tpl", "twig", "j2", "jinja", "mustache", "hbs",
      "njk", "ejs", "pug", "haml", "slim", "styl", "less", "scss", "sass", "coffee", "groovy", "gradle",
      "vb", "vbs", "frm", "bas", "pas", "dpr", "lpr", "f90", "f95", "f03", "f", "for", "ada", "adb",
      "ads", "m4", "cmake", "ninja", "mk", "am", "ac", "spec", "service", "timer", "desktop", "ini",
      "reg", "inf", "pub", "asc", "sig", "pem", "key", "crt", "cer", "der", "pfx", "p12", "csr",
      "xml", "dtd", "xsl", "xslt", "wsdl", "rdf", "ttl", "nt", "jsonld", "geojson", "kml", "gpx", "osm",
      "ipynb", "nix", "flake", "lock", "po", "pot", "mo", "gmo", "diff", "patch", "rej", "orig", "bak",
      "tmp", "swp", "swo", "old", "new", "orig", "rej", "diff", "patch", "changelog", "changes", "news",
      "authors", "copying", "license", "todo", "notes", "readme", "contributing", "security",
      // 歌声合成 / 音乐工程（文本型：可直接读取 + 翻译歌词）
      "ust", "ustx", "vsq", "vsqx", "vpr", "s5p", "svp", "ccs", "ccst", "acep", "ace", "ds", "dspx",
      "ufdata", "musicxml", "mxl", "ly", "lily", "lilypond", "abc", "tja", "f2n", "osu"];
    for (const e of more) TEXT_EXTS.add(e);
  })();

  // ---- 魔数表 ----
  const MAGIC = {
    rpyc: [[0x78, 0x01], [0x78, 0x5e], [0x78, 0x9c], [0x78, 0xda]],   // zlib 头（Ren'Py 8 编译脚本）
    rpa: [[0x52, 0x45, 0x4e, 0x50, 0x59, 0x20, 0x52, 0x50, 0x41]],   // "RENPY RPA"
    dex: [[0x64, 0x65, 0x78, 0x0a, 0x30, 0x33, 0x35]],               // "dex\n035"
    class: [[0xca, 0xfe, 0xba, 0xbe]],                               // Java class
    zip: [[0x50, 0x4b, 0x03, 0x04]],                                 // zip（apk/jar/docx 等容器）
    "7z": [[0x37, 0x7a, 0xbc, 0xaf, 0x27, 0x1c]],                     // 7z
    rar: [[0x52, 0x61, 0x72, 0x21, 0x1a, 0x07]],                     // "Rar!\x1a\x07"（RAR4/RAR5）
    gz: [[0x1f, 0x8b]],                                              // gzip
    bz2: [[0x42, 0x5a, 0x68]],                                       // "BZh"
    xz: [[0xfd, 0x37, 0x7a, 0x58, 0x5a, 0x00]],                       // xz
    zst: [[0x28, 0xb5, 0x2f, 0xfd]],                                  // zstd
    lz4: [[0x04, 0x22, 0x4d, 0x18]],                                  // lz4 frame
    ar: [[0x21, 0x3c, 0x61, 0x72, 0x63, 0x68, 0x3e, 0x0a]],           // "!<arch>\n"
    cpio: [[0x30, 0x37, 0x30, 0x37, 0x30, 0x31], [0x30, 0x37, 0x30, 0x37, 0x30, 0x32]], // newc/odc
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
      desc: "未识别的文件类型。当前版本已支持 Ren'Py / Python / Java / 二进制 / 全格式识别。",
      icon: "？",
    },
    text: {
      id: "text", label: "纯文本 / 脚本", ext: "txt 等", engine: "text",
      canTranslate: true,
      badge: { ch: "T", color: "#34d399" },
      desc: "纯文本 / 脚本 / 标记 / 歌词 / 字幕文件。浏览器内直读并支持 AI 语境翻译。",
      icon: "≋",
    },
    generic: {
      id: "generic", label: "已识别格式", ext: "? ", engine: "none",
      canTranslate: false,
      badge: { ch: "◇", color: "#f59e0b" },
      desc: "格式已识别（来自 627 格式库）。浏览器端可显示元数据；完整解析视格式复杂度逐步接入。",
      icon: "◇",
    },
  };

  // 由 627 表动态构建元数据
  function metaFromTable(ext) {
    const t = EXT_TABLE[ext];
    if (!t) return null;
    const lvl = t.lvl || "";
    let id, engine, canTranslate;
    if (KNOWN_ENGINE[ext]) {
      id = ext; engine = KNOWN_ENGINE[ext];
      canTranslate = (engine === "doc" || engine === "voice" || engine === "rpycdec" || engine === "text");
    }
    else if (TEXT_EXTS.has(ext)) { id = "text"; engine = "text"; canTranslate = true; }
    else { id = "generic"; engine = "none"; canTranslate = false; }
    const lvlHint = KNOWN_ENGINE[ext] ? (lvl === "翻译" ? "浏览器内可直接阅读并 AI 翻译。" : "浏览器内支持解析/反编译。") :
      lvl === "不可行/需重" ? "该格式在浏览器内暂不可行（需专用内核/解码库），完整能力将在 Windows/Android 端提供。" :
      lvl === "仅识别" ? "浏览器内仅识别元数据，完整解析将在 Windows/Android 端提供。" :
      lvl === "反编译" ? "浏览器内支持反编译。" :
      lvl === "解析/解包" ? "浏览器内支持结构解析/解包（逐步接入）。" :
      lvl === "翻译" ? "浏览器内可直接阅读并 AI 翻译。" : "";
    return {
      id, label: t.label || ext, ext: "." + ext, engine,
      canTranslate,
      badge: { ch: (t.cat || "?").slice(0, 1), color: lvl === "翻译" ? "#34d399" : lvl === "反编译" ? "#22d3ee" : lvl === "解析/解包" ? "#60a5fa" : "#f59e0b" },
      desc: (t.desc || "") + " " + lvlHint,
      icon: id === "text" ? "≋" : "◇",
      fmtCat: t.cat, fmtLvl: lvl, fmtPri: t.pri, fmtSrc: t.src, fmtPath: t.path,
    };
  }

  // ---- 识别 ----
  async function identify(file) {
    const size = file.size;
    const head = new Uint8Array(await file.slice(0, 16).arrayBuffer());
    const ext = (file.name.split(".").pop() || "").toLowerCase();
    const hex = Array.from(head.slice(0, 8)).map(b => b.toString(16).padStart(2, "0")).join(" ").toUpperCase();

    let id = null;
    let tableHit = null;

    // 魔数优先
    if (startsWith(head, MAGIC.dex[0])) id = "dex";
    else if (startsWith(head, MAGIC.class[0])) id = "jar";           // class 归入 jar 组
    else if (startsWith(head, MAGIC.rpa[0])) id = "rpa";
    else if (startsWith(head, MAGIC["7z"][0])) id = "7z";
    else if (startsWith(head, MAGIC.rar[0])) id = "rar";
    else if (startsWith(head, MAGIC.gz[0])) id = "gz";
    else if (startsWith(head, MAGIC.bz2[0])) id = "bz2";
    else if (startsWith(head, MAGIC.xz[0])) id = "xz";
    else if (startsWith(head, MAGIC.zst[0])) id = "zst";
    else if (startsWith(head, MAGIC.lz4[0])) id = "lz4";
    else if (startsWith(head, MAGIC.ar[0])) id = "ar";
    else if (MAGIC.cpio.some(m => startsWith(head, m))) id = "cpio";
    else if (startsWith(head, MAGIC.elf[0])) id = "binary";
    else if (startsWith(head, MAGIC.pe[0])) id = "binary";
    else if (startsWith(head, MAGIC.zip[0])) {
      // zip 容器分流：apk/jar/docx/xlsx/普通 zip → 各自引擎
      if (ext === "apk" || ext === "aab" || ext === "xapk") id = "apk";
      else if (ext === "jar" || ext === "class") id = "jar";
      else if (KNOWN_ENGINE[ext]) id = ext;                          // docx 等 zip 容器走已挂引擎
      else id = "zip";                                               // 普通 zip → 归档引擎
    }
    else if (MAGIC.rpyc.some(m => startsWith(head, m))) id = "rpyc";
    else if (ext === "pyc" || ext === "pyo") id = "pyc";

    // 魔数命中后：若扩展名在 627 表内，补 tableHit 供元数据使用
    if (id && !tableHit && EXT_TABLE[ext]) tableHit = EXT_TABLE[ext];

    // 627 全格式表（扩展名）
    if (!id && EXT_TABLE[ext]) {
      tableHit = EXT_TABLE[ext];
      if (KNOWN_ENGINE[ext]) id = ext;
      else if (TEXT_EXTS.has(ext)) id = "text";
      else id = "generic";
    }

    // 文本内容兜底（UTF-8 可解码的纯文本）
    if (!id) {
      const probe = await file.slice(0, 2048).text().catch(() => null);
      if (probe != null && !probe.includes("\uFFFD")) {
        const t = probe.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, "").trim();
        if (t.length >= 4 && t.length <= 2048) id = "text";
      }
    }

    // 扩展名兜底
    if (!id) {
      if (ext === "rpyc" || ext === "rpymc") id = "rpyc";
      else if (ext === "rpa") id = "rpa";
      else if (ext === "pyc" || ext === "pyo") id = "pyc";
      else if (ext === "dex") id = "dex";
      else if (ext === "apk" || ext === "aab" || ext === "xapk") id = "apk";
      else if (ext === "jar" || ext === "class") id = "jar";
      else if (ext === "7z") id = "7z";
      else if (ext === "rar") id = "rar";
      else if (KNOWN_ENGINE[ext] && KNOWN_ENGINE[ext] === "archive") id = ext;
      else if (ext === "exe" || ext === "dll" || ext === "so" || ext === "elf" || ext === "o" || ext === "bin") id = "binary";
      else id = "unknown";
    }

    // 元数据：表命中 → 动态构建；否则静态 META
    const meta = tableHit ? metaFromTable(ext) : META[id];
    return Object.assign({}, meta, {
      ext: ext || "(无扩展名)",
      size,
      headHex: hex,
      magicNote: id === "pyc" ? "Python 字节码（magic 0x" + Array.from(head.slice(0, 4)).map(b => b.toString(16).padStart(2, "0")).join("") + "）" : "",
      fmtTable: tableHit || null,
    });
  }

  function list() { return Object.values(META); }
  function tableCount() { return Object.keys(EXT_TABLE).length; }

  return { identify, list, tableCount, MAGIC };
})();
