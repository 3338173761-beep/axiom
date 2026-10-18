# -*- coding: utf-8 -*-
"""Axiom Windows 桌面端服务
本地全引擎直跑（无 Pyodide，更快更全）+ 黑客终端风实时日志。
用法（cmd 黑窗，实时滚动日志）:
    G:\\python313\\python.exe win_server.py
浏览器打开: http://127.0.0.1:8787/desktop.html
"""
import os, sys, json, base64, time, io, threading, zipfile, struct

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "py"))
sys.path.insert(0, os.path.join(ROOT, "test", "_pycheck"))  # capstone/dnfile/dncil/rpycdec/uncompyle6/androguard...

# ---------------- 黑客终端日志 ----------------
LOG_BUF = []
LOG_LOCK = threading.Lock()
START_TS = time.time()

def log(tag, msg):
    line = "[%s] [%s] %s" % (time.strftime("%H:%M:%S"), tag, msg)
    print(line, flush=True)  # cmd 黑窗实时滚动
    with LOG_LOCK:
        LOG_BUF.append(line)
        if len(LOG_BUF) > 800:
            del LOG_BUF[:len(LOG_BUF) - 800]

def banner():
    art = r"""
  █████╗ ██╗  ██╗██╗ ██████╗ ███╗   ███╗
 ██╔══██╗╚██╗██╔╝██║██╔═══██╗████╗ ████║
 ███████║ ╚███╔╝ ██║██║   ██║██╔████╔██║
 ██╔══██║ ██╔██╗ ██║██║   ██║██║╚██╔╝██║
 ██║  ██║██╔╝ ██╗██║╚██████╔╝██║ ╚═╝ ██║
 ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝     ╚═╝
  多格式自动反编译器 · Windows 桌面端
==================================================
"""
    for line in art.split("\n"):
        log("AXIOM", line)
    log("SYS", "引擎服务已启动  http://127.0.0.1:8787/desktop.html")
    log("SYS", "本地引擎: rpycdec / uncompyle6 / dalvik_smali / java_class / apk_tool / dotnet_il / capstone / 容器引擎")

# ---------------- 引擎实现（本地直跑） ----------------
def engine_rpyc(data, name):
    import rpycdec, tempfile, os, shutil
    if name.lower().endswith(".rpa"):
        return rpycdec.extract_rpa(io.BytesIO(data))
    d = tempfile.mkdtemp()
    try:
        src = os.path.join(d, "input.rpyc")
        with open(src, "wb") as f:
            f.write(data)
        rpycdec.decompile(src, d)
        out = os.path.join(d, "input.rpy")
        if os.path.isfile(out):
            with open(out, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        return "# rpycdec 未产生输出文件"
    finally:
        shutil.rmtree(d, ignore_errors=True)

def engine_pyc(data, name):
    import uncompyle6
    buf = io.StringIO()
    uncompyle6.decompile_buffer(data.decode("latin1"), sys.version_info, buf)
    return buf.getvalue()

def engine_dex(data, name):
    import dalvik_smali
    return dalvik_smali.decompile_dex(data)

def engine_java(data, name):
    import java_class
    if name.lower().endswith(".jar") or name.lower().endswith(".zip"):
        return java_class.decompile_java(data, name)
    return java_class.decompile_java_class(data, name)

def engine_apk(data, name):
    import apk_tool
    return apk_tool.decompile_apk(data, name)

def engine_dotnet(data, name):
    import dotnet_il
    return dotnet_il.decompile_dotnet(data, name)

def engine_bin(data, name):
    import bin_disasm
    return bin_disasm.decompile_binary(data, name)

def engine_zip(data, name):
    """通用容器引擎：zip → 解包 + 内部文件递归识别 + 可解析的内嵌文件解析。"""
    out = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        infos = zf.infolist()
        out.append("# 容器解包 · %s · %d 个条目" % (name, len(infos)))
        for info in infos[:200]:
            sz = info.file_size
            out.append("  %10d  %s" % (sz, info.filename))
            # 内部文件深度解析（小文件 + 常见类型）
            if info.file_size < 300000 and not info.is_dir() and info.filename.lower().endswith((".dex", ".jar", ".class", ".pyc", ".rpyc", ".dll", ".exe", ".so", ".apk")):
                try:
                    inner = zf.read(info.filename)
                    sub = detect_and_run(inner, info.filename)
                    if sub:
                        out.append("")
                        out.append("  ↓ 内嵌 %s 解析:" % info.filename)
                        out.append("  " + sub.replace("\n", "\n  "))
                except Exception as e:
                    out.append("  （内嵌 %s 解析失败: %s）" % (info.filename, e))
    except Exception as e:
        return "# 容器解包失败: %s" % e
    return "\n".join(out)

def engine_text(data, name):
    """文本类：直接读取（UTF-8 优先，退 GBK/ASCII）。"""
    for enc in ("utf-8", "gbk", "latin1"):
        try:
            t = data.decode(enc)
            break
        except Exception:
            continue
    lines = t.splitlines()
    if len(lines) > 400:
        return "# 文本文件 · %s · %d 行（前 400 行）\n\n%s" % (name, len(lines), "\n".join(lines[:400]))
    return "# 文本文件 · %s · %d 行\n\n%s" % (name, len(lines), t)

# ---------------- 格式识别 + 分发 ----------------
def detect(data, name):
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    if data[:2] == b"MZ":
        import bin_disasm
        kind, arch, err = bin_disasm.detect(data)
        if kind == "pe-dotnet":
            return "dotnet", "dnfile+dncil（.NET → CIL）"
        return "bin", "capstone（%s 原生 → 汇编）" % arch
    if data[:4] == b"\x7fELF":
        return "bin", "capstone（ELF 原生 → 汇编）"
    if data[:4] in (b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe"):
        return "bin", "capstone（Mach-O → 汇编）"
    if data[:4] == b"\xca\xfe\xba\xbe":
        return "java", "自研 Java 引擎（class → JVM 字节码）"
    if data[:4] == b"dex\n":
        return "dex", "自研 Dalvik 反汇编器（DEX → smali）"
    if data[:8] == b"RENPY RPA":
        return "rpyc", "rpycdec（RPA → 归档清单）"
    if data[:8] == b"RENPY RPC2" or data[:8] == b"RENPY RPC3":
        return "rpyc", "rpycdec（Ren'Py 8 → rpy 源码）"
    if data[:4] == b"PK\x03\x04":
        if ext in ("apk", "aab", "xapk"):
            return "apk", "APK 解包 + DEX 反汇编"
        if ext in ("jar",):
            return "java", "自研 Java 引擎（jar → JVM 字节码）"
        return "zip", "通用容器引擎（zip → 解包 + 递归识别）"
    if data[:2] in (b"\x78\x01", b"\x78\x5e", b"\x78\x9c", b"\x78\xda"):
        return "rpyc", "rpycdec（Ren'Py → rpy 源码）"
    # 扩展名兜底
    if ext in ("rpyc", "rpymc"):
        return "rpyc", "rpycdec（Ren'Py 脚本 → rpy 源码）"
    if ext in ("rpa",):
        return "rpyc", "rpycdec（RPA → 归档清单）"
    if ext in ("pyc", "pyo"):
        return "pyc", "uncompyle6（Python 字节码 → 源码）"
    if ext == "dex":
        return "dex", "自研 Dalvik 反汇编器（DEX → smali）"
    if ext in ("apk", "aab", "xapk"):
        return "apk", "APK 解包 + DEX 反汇编"
    if ext in ("jar", "class"):
        return "java", "自研 Java 引擎（%s → JVM 字节码）" % ext
    # 文本类兜底
    try:
        data.decode("utf-8")
        if ext in ("txt", "md", "json", "xml", "csv", "ini", "conf", "log", "yml", "yaml", "html", "htm", "css", "js", "py", "java", "cs", "c", "cpp", "h", "sql", "sh", "bat", "ps1"):
            return "text", "文本读取（%s）" % ext
    except Exception:
        pass
    return "bin", "capstone（未知二进制 → 探测架构反汇编）"

ENGINE_FN = {
    "rpyc": engine_rpyc, "pyc": engine_pyc, "dex": engine_dex,
    "java": engine_java, "apk": engine_apk, "dotnet": engine_dotnet,
    "bin": engine_bin, "zip": engine_zip, "text": engine_text,
}

def detect_and_run(data, name, depth=0):
    kind, desc = detect(data, name)
    if kind not in ENGINE_FN:
        return "# 暂无引擎: %s" % name
    try:
        return ENGINE_FN[kind](data, name)
    except Exception as e:
        return "# %s 引擎执行失败: %s" % (kind, e)

# ---------------- HTTP 服务 ----------------
from http.server import HTTPServer, BaseHTTPRequestHandler

MIME = {
    ".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg",
    ".svg": "image/svg+xml", ".json": "application/json; charset=utf-8",
    ".whl": "application/octet-stream", ".rpyc": "application/octet-stream",
    ".dex": "application/octet-stream", ".dll": "application/octet-stream",
    ".exe": "application/octet-stream", ".txt": "text/plain; charset=utf-8",
}

# ---------------- 安卓打包工具链检测（内置下载器前置） ----------------
def toolcheck():
    """检测本机安卓打包环境：Java / keytool / apktool / Android SDK / d8 / apksigner / zipalign"""
    import glob as _glob
    results = []

    def probe(tool, candidates):
        for p in candidates:
            if p and os.path.isfile(p):
                return p
        return None

    # Java
    java = probe("java", [
        r"F:\jdk17\jdk-17.0.20+8\bin\java.exe",
        os.environ.get("JAVA_HOME", "") + r"\bin\java.exe",
    ])
    keytool = probe("keytool", [
        r"F:\jdk17\jdk-17.0.20+8\bin\keytool.exe",
        os.environ.get("JAVA_HOME", "") + r"\bin\keytool.exe",
    ])
    # Android SDK + build-tools
    sdk = r"F:\android-sdk" if os.path.isdir(r"F:\android-sdk") else None
    d8 = aapt = apksigner = zipalign = None
    bt_dirs = []
    if sdk:
        bt = os.path.join(sdk, "build-tools")
        if os.path.isdir(bt):
            bt_dirs = sorted(_glob.glob(os.path.join(bt, "*")), reverse=True)
    for d in bt_dirs:
        if not d8:
            d8 = probe("d8", [os.path.join(d, "d8.bat")])
        if not aapt:
            aapt = probe("aapt", [os.path.join(d, "aapt.exe")])
        if not apksigner:
            apksigner = probe("apksigner", [os.path.join(d, "apksigner.bat")])
        if not zipalign:
            zipalign = probe("zipalign", [os.path.join(d, "zipalign.exe")])
    # apktool（jar 或命令）
    apktool = None
    for p in [r"F:\apktool\apktool.jar", r"E:\apktool\apktool.jar", r"F:\apktool.jar",
              r"E:\Axiom\web\test\apktool.jar"]:
        if os.path.isfile(p):
            apktool = p
            break
    if not apktool:
        import shutil
        if shutil.which("apktool"):
            apktool = "PATH:apktool"

    results.append({"tool": "Java", "ok": bool(java), "path": java or "", "need": "汉化重编译必需"})
    results.append({"tool": "keytool", "ok": bool(keytool), "path": keytool or "", "need": "APK 签名必需"})
    results.append({"tool": "Android SDK", "ok": bool(sdk), "path": sdk or "", "need": "打包环境"})
    results.append({"tool": "d8/dex", "ok": bool(d8), "path": d8 or "", "need": "DEX 重编译"})
    results.append({"tool": "aapt", "ok": bool(aapt), "path": aapt or "", "need": "资源编译"})
    results.append({"tool": "apksigner", "ok": bool(apksigner), "path": apksigner or "", "need": "APK 签名"})
    results.append({"tool": "zipalign", "ok": bool(zipalign), "path": zipalign or "", "need": "APK 对齐"})
    results.append({"tool": "apktool", "ok": bool(apktool), "path": apktool or "", "need": "APK 解包/回包"})
    missing = [r["tool"] for r in results if not r["ok"]]
    ready = all(r["ok"] for r in results if r["need"] in ("APK 解包/回包", "APK 签名", "DEX 重编译"))
    return {"results": results, "missing": missing,
            "ready": ready and not missing,
            "hint": "缺失项由内置下载器自动下载（下一阶段接入）" if missing else "工具链完整"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 关闭默认请求日志（噪音）
        pass

    def do_GET(self):
        import urllib.parse
        path = urllib.parse.urlparse(self.path).path
        # 设备区分：手机访问桌面端页面 → 302 跳回原网页端 index.html
        if path in ("/", "/desktop.html"):
            ua = self.headers.get("User-Agent", "")
            is_mobile = any(k in ua for k in ("Android", "iPhone", "iPad", "iPod", "Mobile", "MQQBrowser", "UCBrowser", "MicroMessenger"))
            if is_mobile or (self.headers.get("X-Mobile", "") == "1"):
                self.send_response(302)
                self.send_header("Location", "/index.html")
                self.end_headers()
                return
        if path == "/log":
            self.send_json({"lines": list(LOG_BUF)})
            return
        if path in ("/", "/desktop.html"):
            path = "/desktop.html"
        if path == "/api/status":
            self.send_json({"up": time.time() - START_TS, "engines": sorted(ENGINE_FN.keys())})
            return
        fpath = os.path.normpath(os.path.join(ROOT, path.lstrip("/")))
        if not fpath.startswith(ROOT):
            self.send_error(403); return
        if os.path.isfile(fpath):
            ext = os.path.splitext(fpath)[1].lower()
            ctype = MIME.get(ext, "application/octet-stream")
            with open(fpath, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/decompile":
            ln = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(ln)
            try:
                req = json.loads(raw.decode("utf-8"))
                name = req.get("name", "input.bin")
                b64 = req.get("b64", "")
                data = base64.b64decode(b64)
            except Exception as e:
                self.send_json({"ok": False, "err": "请求解析失败: %s" % e})
                return
            t0 = time.time()
            log("JOB", "收到文件: %s (%.1f KB) → 识别格式…" % (name, len(data) / 1024))
            kind, desc = detect(data, name)
            log("ENGINE", "选定引擎: %s · %s" % (kind, desc))
            try:
                out = ENGINE_FN[kind](data, name)
                ms = int((time.time() - t0) * 1000)
                log("DONE", "完成 %s → %d 字符 · 耗时 %d ms" % (name, len(str(out)), ms))
                self.send_json({"ok": True, "engine": kind, "desc": desc, "out": str(out), "ms": ms})
            except Exception as e:
                log("FAIL", "%s 引擎异常: %s" % (kind, e))
                self.send_json({"ok": False, "err": str(e), "engine": kind, "desc": desc})
            return
        if self.path == "/scan":
            ln = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(ln)
            try:
                req = json.loads(raw.decode("utf-8"))
                name = req.get("name", "input.dll")
                b64 = req.get("b64", "")
                data = base64.b64decode(b64)
            except Exception as e:
                self.send_json({"ok": False, "err": "请求解析失败: %s" % e})
                return
            t0 = time.time()
            log("JOB", "安全扫描: %s (%.1f KB) → 全量反编译 + 特征检测…" % (name, len(data) / 1024))
            try:
                import scan_engine
                summary, findings, out = scan_engine.scan(data, name)
                report = scan_engine.render_report(summary, findings, name, out)
                ms = int((time.time() - t0) * 1000)
                log("DONE", "扫描完成 %s → 风险等级 %s（评分 %d）· %d ms"
                    % (name, summary["risk_level"], summary["risk_score"], ms))
                self.send_json({"ok": True, "summary": summary, "findings": findings,
                                "report": report, "ms": ms})
            except Exception as e:
                log("FAIL", "扫描异常: %s" % e)
                self.send_json({"ok": False, "err": str(e)})
            return
        self.send_json({"ok": False, "err": "unknown endpoint"})

    def send_json(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

if __name__ == "__main__":
    banner()
    log("SYS", "加载本地引擎库…")
    ok_engines = []
    for k in ENGINE_FN:
        try:
            if k == "rpyc":
                import rpycdec; ok_engines.append("rpycdec")
            elif k == "pyc":
                import uncompyle6; ok_engines.append("uncompyle6")
            elif k == "bin":
                import capstone; ok_engines.append("capstone")
            elif k == "dotnet":
                import dnfile, dncil; ok_engines.append("dnfile+dncil")
            else:
                ok_engines.append(k)
        except Exception as e:
            log("WARN", "引擎 %s 加载失败（可降级）: %s" % (k, e))
    log("SYS", "就绪引擎: " + ", ".join(ok_engines))
    server = HTTPServer(("0.0.0.0", 8787), Handler)
    log("SYS", "监听 0.0.0.0:8787（局域网 http://192.168.1.9:8787/desktop.html）")
    log("SYS", "按 Ctrl+C 停止服务")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("SYS", "服务已停止")
