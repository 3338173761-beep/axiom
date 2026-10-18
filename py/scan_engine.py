# -*- coding: utf-8 -*-
"""Axiom 安全扫描引擎（杀毒软件 Pro Max）
纯本地静态分析：PE/DLL 全量反编译 + 导入表/字符串/隐蔽行为特征扫描。
不联网、不执行代码，只做静态检测，输出风险评分与高危项清单。
设计要点：数字签名的可信 DLL 自动降级，常见动态加载 API 只作提示，
注入组合拳/持久化/回连等组合特征才拉高风险。
"""
import re

# ---------------- 可疑 API 特征库（按行为类别） ----------------
SUSPICIOUS_APIS = {
    "进程注入/远程执行": [
        "CreateRemoteThread", "WriteProcessMemory", "VirtualAllocEx",
        "NtCreateThreadEx", "QueueUserAPC", "SetThreadContext",
        "ZwCreateThreadEx", "RtlCreateUserThread", "OpenProcess",
    ],
    "持久化/自启动": [
        "RegSetValueEx", "RegCreateKeyEx", "RegOpenKeyExW",
        "CreateService", "OpenSCManager", "StartService", "ChangeServiceConfig",
    ],
    "键盘记录/间谍": [
        "GetAsyncKeyState", "GetKeyState", "GetClipboardData",
        "SetWindowsHookExA", "SetWindowsHookExW", "GetForegroundWindow",
        "keybd_event", "SendInput",
    ],
    "网络回连/下载": [
        "InternetOpenA", "InternetOpenW", "InternetConnectA", "HttpSendRequestA",
        "WinHttpConnect", "WinHttpOpen", "URLDownloadToFileA", "URLDownloadToFileW",
    ],
    "恶意载荷执行": [
        "WinExec", "ShellExecuteA", "ShellExecuteW", "CreateProcessA", "CreateProcessW",
    ],
    "进程伪装/篡改": [
        "NtSetInformationProcess", "ZwSetInformationProcess", "NtProtectVirtualMemory",
    ],
}

# 常见于正常 DLL 的动态加载/异常处理 API（仅提示，不计分）
COMMON_APIS = {
    "GetProcAddress", "LoadLibraryA", "LoadLibraryExA", "LoadLibraryW",
    "GetModuleHandle", "IsDebuggerPresent", "SetUnhandledExceptionFilter",
    "VirtualProtect", "VirtualAlloc", "GetProcAddress",
}

# 高风险的"组合拳"（字符串/导入表出现 2 个以上 → 明显恶意）
INJECTION_COMBO = ["CreateRemoteThread", "WriteProcessMemory", "VirtualAllocEx", "OpenProcess", "NtCreateThreadEx"]

# 正常系统/签名 DLL 常见域名（证书/CRL 校验等，不算回连）
TRUSTED_DOMAINS = ("microsoft.com", "windows.com", "msftconnecttest.com", "digicert.com",
                   "verisign.com", "globalsign.com", "entrust.net", "godaddy.com",
                   "thawte.com", "symantec.com", "apple.com", "adobe.com")

SUSPICIOUS_STRINGS = [
    ("执行外部命令", ["powershell -", "cmd /c", "cmd.exe /c", "wmic ", "schtasks /create", "certutil -", "bitsadmin /", "/c whoami", "powershell.exe"]),
    ("自启动注册表", ["CurrentVersion\\Run", "CurrentVersion\\RunOnce", "CurrentVersion\\RunServices"]),
    ("服务创建", ["CurrentControlSet\\Services", "CreateService"]),
    ("下载执行", ["URLDownloadToFile", "Invoke-WebRequest", "Invoke-Expression", "IEX("]),
    ("隐蔽文件操作", ["attrib +h +s", "rundll32 ", "svchost.exe -k"]),
    ("键盘记录", ["GetAsyncKeyState", "GetKeyState"]),
    ("进程注入", ["CreateRemoteThread", "WriteProcessMemory", "VirtualAllocEx", "NtCreateThreadEx", "QueueUserAPC"]),
    ("内存修改", ["VirtualProtectEx", "NtProtectVirtualMemory", "WriteProcessMemory"]),
]

URL_RE = re.compile(r"https?://[a-zA-Z0-9.\-/_]+", re.I)
IP_RE = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
B64_RE = re.compile(r"(?:[A-Za-z0-9+/]{40,}={0,2})")


def extract_strings(data, min_len=5):
    """提取二进制中的可打印 ASCII 字符串（含 UTF-16LE 宽字符）"""
    out = []
    cur = []
    for b in data:
        if 32 <= b <= 126:
            cur.append(chr(b))
        else:
            if len(cur) >= min_len:
                out.append("".join(cur))
            cur = []
    if len(cur) >= min_len:
        out.append("".join(cur))
    wcur = []
    i = 0
    while i < len(data) - 1:
        b0, b1 = data[i], data[i + 1]
        if 32 <= b0 <= 126 and b1 == 0:
            wcur.append(chr(b0)); i += 2
        else:
            if len(wcur) >= min_len:
                out.append("".join(wcur))
            wcur = []
            i += 1
    if len(wcur) >= min_len:
        out.append("".join(wcur))
    return out


def scan_pe(data):
    """PE 解析：导入表 + 数字签名检测。返回 (命中列表, 全部导入名, 是否签名)"""
    hits = []
    all_imports = []
    signed = False
    try:
        import pefile
        pe = pefile.PE(data=data, fast_load=True)
        # 数字签名（Authenticode）
        try:
            pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_SECURITY"]])
            sec = getattr(pe, "OPTIONAL_HEADER", None)
            if sec and getattr(sec, "DATA_DIRECTORY", None):
                for d in sec.DATA_DIRECTORY:
                    if d.name == "IMAGE_DIRECTORY_ENTRY_SECURITY" and d.VirtualAddress and d.Size:
                        signed = True
        except Exception:
            pass
        # 导入表
        try:
            pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
            for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
                for imp in entry.imports:
                    if imp.name:
                        name = imp.name.decode("utf-8", "replace")
                        all_imports.append(name)
                        if name in COMMON_APIS:
                            hits.append({"category": "常见动态加载(提示)", "api": name, "severity": 1})
                            continue
                        for cat, apis in SUSPICIOUS_APIS.items():
                            if name in apis:
                                hits.append({"category": cat, "api": name,
                                             "severity": _sev_for(cat)})
        except Exception:
            pass
    except Exception as e:
        hits.append({"category": "PE解析", "api": str(e)[:60], "severity": 0})
    return hits, all_imports, signed


def _sev_for(cat):
    return {"进程注入/远程执行": 8, "持久化/自启动": 6, "网络回连/下载": 5,
            "键盘记录/间谍": 8, "恶意载荷执行": 6, "进程伪装/篡改": 5}.get(cat, 2)


def scan_strings(data, signed=False):
    """字符串层扫描：URL/IP/base64/命令特征/注入关键词组合拳"""
    findings = []
    strs = extract_strings(data)
    joined = "\n".join(strs)
    # URL（排除可信域名）
    for u in set(URL_RE.findall(joined)):
        if not any(d in u for d in TRUSTED_DOMAINS):
            findings.append({"category": "网络地址", "detail": u[:120], "severity": 3})
    # 外部 IP
    for ip in set(IP_RE.findall(joined)):
        if not ip.startswith(("192.168.", "10.", "127.", "0.0.0.0", "169.254.")):
            findings.append({"category": "外部IP", "detail": ip, "severity": 2})
    # 命令/行为特征
    for label, pats in SUSPICIOUS_STRINGS:
        for p in pats:
            if p.lower() in joined.lower():
                findings.append({"category": "可疑字符串", "detail": label + " → " + p,
                                 "severity": 2})
    # 注入组合拳（字符串层命中 ≥2 个注入 API 名 → 严重）
    combo_hits = [a for a in INJECTION_COMBO if a in joined]
    if len(combo_hits) >= 2:
        findings.append({"category": "注入组合拳", "detail": "字符串同时含: " + " / ".join(combo_hits),
                         "severity": 10})
    # base64 长载荷
    for m in B64_RE.finditer(joined):
        findings.append({"category": "疑似编码载荷", "detail": "base64 长串 (" + str(len(m.group())) + " 字符)",
                         "severity": 3})
        break
    return findings, strs


def scan_dotnet(data):
    """.NET DLL：CIL 反编译 + 字符串扫描"""
    out = ""
    try:
        import dotnet_il
        out = dotnet_il.decompile_dotnet(data, "scan.dll")
    except Exception as e:
        out = "# .NET 反编译失败: %s" % e
    findings = []
    low = out.lower()
    for label, pats in SUSPICIOUS_STRINGS:
        for p in pats:
            if p.lower() in low:
                findings.append({"category": ".NET 可疑字符串", "detail": label + " → " + p,
                                 "severity": 2})
    combo = [a for a in INJECTION_COMBO if a in out]
    if len(combo) >= 2:
        findings.append({"category": "注入组合拳", "detail": "IL 代码含: " + " / ".join(combo),
                         "severity": 10})
    return out, findings


def scan(data, name):
    """主入口：全量扫描，返回 (summary, findings, out)"""
    findings = []
    all_imports = []
    is_dotnet = False
    signed = False
    out = ""

    if data[:2] == b"MZ":
        try:
            import bin_disasm
            kind, arch, _ = bin_disasm.detect(data)
            if kind == "pe-dotnet":
                is_dotnet = True
                out, net_f = scan_dotnet(data)
                findings += net_f
            else:
                import bin_disasm as bd
                out = bd.decompile_binary(data, name)
        except Exception as e:
            out = "# 反编译失败: %s" % e
        # 导入表 + 签名
        imp_hits, all_imports, signed = scan_pe(data)
        findings += imp_hits
        # 字符串层
        str_findings, strs = scan_strings(data, signed)
        findings += str_findings
        # 导入表组合拳
        imp_names = " ".join(all_imports)
        combo = [a for a in INJECTION_COMBO if a in imp_names]
        if len(combo) >= 2:
            findings.append({"category": "注入组合拳", "detail": "导入表同时含: " + " / ".join(combo),
                             "severity": 10})
    else:
        out = "# 非 PE 文件（跳过反编译，仅字符串扫描）"
        str_findings, strs = scan_strings(data)
        findings += str_findings
        strs = extract_strings(data)

    # 去重
    seen = set()
    uniq = []
    for f in findings:
        key = (f.get("category"), f.get("api") or f.get("detail"))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(f)

    # 评分：签名可信 DLL 降级（只算组合拳/注入，常见项不计）
    if signed:
        score = sum(f.get("severity", 0) for f in uniq if f.get("severity", 0) >= 8)
    else:
        score = sum(f.get("severity", 0) for f in uniq)

    if score >= 20:
        level = "严重"
    elif score >= 10:
        level = "高危"
    elif score >= 5:
        level = "中危"
    else:
        level = "低危（未见明显恶意特征）"

    cat_counts = {}
    for f in uniq:
        cat_counts[f["category"]] = cat_counts.get(f["category"], 0) + 1
    summary = {
        "risk_level": level,
        "risk_score": score,
        "findings_count": len(uniq),
        "categories": cat_counts,
        "dotnet": is_dotnet,
        "signed": signed,
        "string_count": len(strs),
        "import_count": len(all_imports),
    }
    return summary, uniq, out


def render_report(summary, findings, name, out=""):
    """渲染人类可读报告"""
    L = []
    L.append("# AXIOM 安全扫描报告 · %s" % name)
    L.append("")
    L.append("风险等级: %s（评分 %d）" % (summary["risk_level"], summary["risk_score"]))
    L.append("命中特征: %d 项 · 导入函数 %d 个 · 字符串 %d 条%s%s"
             % (summary["findings_count"], summary["import_count"], summary["string_count"],
                " · .NET 程序集" if summary["dotnet"] else "",
                " · 检测到数字签名（可信 DLL，常见项已降级）" if summary.get("signed") else ""))
    L.append("")
    if findings:
        L.append("## 可疑特征明细")
        for f in sorted(findings, key=lambda x: -x.get("severity", 0)):
            sev = {10: "严重", 8: "严重", 6: "高危", 5: "高危", 3: "中危", 2: "提示", 1: "提示"}.get(f.get("severity", 0), "提示")
            detail = f.get("api") or f.get("detail")
            L.append("  [%s] %s: %s" % (sev, f["category"], detail))
    else:
        L.append("未发现可疑特征。")
    L.append("")
    L.append("## 反编译预览（前 300 行）")
    L.append("")
    lines = str(out).split("\n") if out else []
    L.append("\n".join(lines[:300]))
    return "\n".join(L)
