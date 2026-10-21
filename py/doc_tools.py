# -*- coding: utf-8 -*-
"""Axiom 文档引擎：docx/xlsx/pptx/odt/ods/odp/epub/rtf 浏览器内文本提取
原理：Office Open XML / OpenDocument 均为 zip 容器 → 解包提取 XML 文本；
RTF 为控制词文本 → 自研剥离器。
输出：纯文本（可进入翻译流水线）
"""
import io, os, sys, zipfile, re


def _read_zip(data):
    try:
        return zipfile.ZipFile(io.BytesIO(data))
    except Exception as e:
        raise ValueError("zip 容器解析失败：%s" % e)


def _xml_texts(xml, tag):
    # 提取指定标签内的纯文本（含子标签合并）
    return re.findall(r"<%s[^>]*>([^<]*)</%s>" % (tag, tag), xml)


def extract_docx(data):
    zf = _read_zip(data)
    if "word/document.xml" not in zf.namelist():
        # 兼容 docm/dotx 等
        cand = [n for n in zf.namelist() if n.endswith("document.xml") or n == "word/document.xml"]
        if not cand:
            return "未找到 document.xml（可能不是有效的 Word 文档）"
        path = cand[0]
    else:
        path = "word/document.xml"
    xml = zf.read(path).decode("utf-8", errors="replace")
    paras = re.split(r"</w:p>", xml)
    out = []
    for p in paras:
        texts = re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)
        if texts:
            line = "".join(texts).strip()
            if line:
                out.append(line)
    if not out:
        # 兜底：提取全部 <w:t>
        for t in re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml):
            if t.strip():
                out.append(t.strip())
    return "\n".join(out) if out else "文档中未提取到文本（可能是图片型/空文档）"


def extract_xlsx(data):
    zf = _read_zip(data)
    names = zf.namelist()
    # sharedStrings（共享字符串表）
    ss = {}
    if "xl/sharedStrings.xml" in names:
        xml = zf.read("xl/sharedStrings.xml").decode("utf-8", errors="replace")
        for m in re.finditer(r"<si>(.*?)</si>", xml, re.S):
            idx = len(ss)
            txt = "".join(re.findall(r"<t[^>]*>([^<]*)</t>", m.group(1)))
            ss[idx] = txt
    # 工作表
    lines = []
    sheet_files = sorted(n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
    for sf in sheet_files:
        xml = zf.read(sf).decode("utf-8", errors="replace")
        sheet_name = os.path.basename(sf)
        rows = re.split(r"</row>", xml)
        for r in rows:
            cells = []
            # 内联字符串 <is><t>..</t></is> 或共享索引 <c t="s" ...><v>n</v>
            for cm in re.finditer(r"<c[^>]*>(.*?)</c>|<c[^>]*/>", r, re.S):
                content = cm.group(1) if cm.group(1) is not None else ""
                if not content:
                    continue
                v = re.search(r"<v>([^<]*)</v>", content)
                is_t = re.findall(r"<t[^>]*>([^<]*)</t>", content)
                if is_t:
                    cells.append("".join(is_t))
                elif v and v.group(1).isdigit() and int(v.group(1)) in ss:
                    cells.append(ss[int(v.group(1))])
            line = "\t".join(c for c in cells if c.strip())
            if line.strip():
                lines.append("%s | %s" % (sheet_name, line))
    if not lines:
        # 兜底：sharedStrings 全文
        lines = list(ss.values())
    return "\n".join(lines) if lines else "工作簿中未提取到文本"


def extract_pptx(data):
    zf = _read_zip(data)
    names = zf.namelist()
    slides = sorted(n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n))
    if not slides:
        return "未找到幻灯片 XML（可能不是有效的 PPTX）"
    out = []
    for sf in slides:
        xml = zf.read(sf).decode("utf-8", errors="replace")
        texts = re.findall(r"<a:t[^>]*>([^<]*)</a:t>", xml)
        lines = [t.strip() for t in texts if t.strip()]
        if lines:
            out.append("--- %s ---" % os.path.basename(sf))
            out.extend(lines)
    return "\n".join(out) if out else "演示文稿中未提取到文本"


def extract_zip_xml(data, lower):
    """通用 zip + XML 容器：列包内文档并提取文本节点（sxw/stc/sxi/csproj/thmx 等）"""
    zf = _read_zip(data)
    names = zf.namelist()
    out = ["压缩文档包（%s）" % lower.rsplit(".", 1)[-1]]
    out.append("包内部件: %d" % len(names))
    xml_docs = [n for n in names if n.lower().endswith((".xml", ".rels", ".fpage", ".apxl", ".iwa", ".json", ".html", ".htm")) and not n.startswith("META-INF/") and "schemas" not in n.lower()]
    shown = 0
    for n in sorted(xml_docs)[:6]:
        try:
            xml = zf.read(n).decode("utf-8", "replace")
        except Exception:
            continue
        texts = re.findall(r"<(?:t|text|w:t|p|td|th|title)[^>]*>([^<]{1,200})</", xml, re.I)
        texts = [t.strip() for t in texts if t.strip()]
        if texts:
            out.append("--- %s（%d 文本）---" % (n, len(texts)))
            out.append(" ".join(texts[:30])[:500])
            shown += 1
    if not shown:
        # 兜底：全量剥离标签
        for n in sorted(xml_docs)[:3]:
            try:
                xml = zf.read(n).decode("utf-8", "replace")
            except Exception:
                continue
            txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml)).strip()
            if txt:
                out.append("--- %s ---" % n)
                out.append(txt[:400])
                shown += 1
    if not shown:
        out.append("（未提取到可见文本，仅容器结构）")
    return "\n".join(out)


def extract_odt(data, kind):
    zf = _read_zip(data)
    if "content.xml" not in zf.namelist():
        return "未找到 content.xml（可能不是有效的 OpenDocument）"
    xml = zf.read("content.xml").decode("utf-8", errors="replace")
    out = []
    if kind in ("odt", "ott", "odm"):
        # <text:p> / <text:h> 段落
        for m in re.finditer(r"<text:p[^>]*>(.*?)</text:p>|<text:h[^>]*>(.*?)</text:h>", xml, re.S):
            seg = m.group(1) or m.group(2) or ""
            txt = "".join(re.findall(r"<text:span[^>]*>([^<]*)</text:span>|<text:a[^>]*>([^<]*)</text:a>", seg))
            if not txt:
                txt = re.sub(r"<[^>]+>", "", seg)
            if txt.strip():
                out.append(txt.strip())
    else:
        # ods/odp：提取全部可见文本
        txt = re.sub(r"<[^>]+>", " ", xml)
        for line in txt.split("\n"):
            if line.strip():
                out.append(line.strip())
    return "\n".join(out) if out else "OpenDocument 中未提取到文本"


def extract_epub(data):
    zf = _read_zip(data)
    names = zf.namelist()
    docs = [n for n in names if n.endswith((".html", ".xhtml", ".htm", ".xml")) and not n.startswith("META-INF")]
    if not docs:
        return "未找到内容文档（可能不是有效的 EPUB）"
    out = []
    for n in sorted(docs):
        try:
            xml = zf.read(n).decode("utf-8", errors="replace")
        except Exception:
            continue
        body = xml
        bm = re.search(r"<body[^>]*>(.*?)</body>", xml, re.S)
        if bm:
            body = bm.group(1)
        text = re.sub(r"<[^>]+>", "", body)
        text = re.sub(r"\s*\n\s*", "\n", text).strip()
        if text:
            out.append("--- %s ---" % n)
            out.append(text)
    return "\n".join(out) if out else "EPUB 中未提取到文本"


def extract_rtf(data):
    # 自研 RTF 文本剥离器（控制词剥离 + \'XX 十六进制转义）
    text = data.decode("latin-1", errors="replace")
    out = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            j = i + 1
            while j < n and text[j].isalpha():
                j += 1
            word = text[i + 1:j]
            if word in ("par", "line", "pard", "sect", "page", "ltrpar"):
                out.append("\n")
            # \uN Unicode 控制符（Word 中文 RTF 标准编码）
            if word == "u" and j < n and text[j].isdigit():
                j2 = j
                while j2 < n and text[j2].isdigit():
                    j2 += 1
                try:
                    out.append(chr(int(text[j:j2])))
                except Exception:
                    pass
                j = j2
                if j < n and text[j] == "?":
                    j += 1  # fallback 字符
                i = j
                continue
            # 跳过数字参数
            while j < n and text[j].isdigit():
                j += 1
            if j < n and text[j] == " ":
                j += 1
            # 十六进制字节 \'XX
            if j + 3 < n and text[j] == "'":
                try:
                    out.append(bytes([int(text[j + 1:j + 3], 16)]).decode("latin-1"))
                except Exception:
                    pass
                j += 3
            i = j
        elif c in "{}\n\r":
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out).strip() or "RTF 中未提取到文本"


def extract_ole(data):
    """OLE 复合文档（Word 97-2003 .doc/.dot）通用文本提取。
    全文件 UTF-16LE 启发式扫描（Word 正文流以 UTF-16 存中文）+ ASCII 兜底。"""
    if data[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "非 OLE 复合文档（缺 D0CF11E0 头）"
    seen = set()
    kept = []

    def _push(buf):
        s = "".join(buf).strip()
        # 过滤 UTF-16 错位扫描产生的短噪音段（真实正文段通常较长）
        if len(s) >= 6 and any(c.isalnum() for c in s) and s not in seen:
            seen.add(s)
            kept.append(s)

    n = len(data)
    # 两个字节偏移各扫一遍 UTF-16LE（正文可能从任意对齐开始）
    for base in (0, 1):
        i = base
        buf = []
        while i + 1 < n:
            code = data[i] | (data[i + 1] << 8)
            if (0x20 <= code < 0x7F) or (0x4E00 <= code <= 0x9FFF) or code in (0x0A, 0x0D, 0x09):
                if code == 0x0D:
                    buf.append("\n")
                elif code == 0x0A:
                    pass
                elif code == 0x09:
                    buf.append(" ")
                else:
                    buf.append(chr(code))
            else:
                _push(buf)
                buf = []
            i += 2
        _push(buf)
    if kept:
        return "\n".join(kept[:500])
    # 兜底：单字节 ASCII 可读段
    i = 0
    buf = []
    while i < n:
        c = data[i]
        if 0x20 <= c < 0x7F:
            buf.append(chr(c))
        else:
            _push(buf)
            buf = []
        i += 1
    _push(buf)
    return "\n".join(kept[:500]) if kept else "OLE 文档中未提取到文本（可能是加密或图片型文档）"


def _score_summary(xml, label):
    """MuseScore/MusicXML 乐谱摘要（标题/作曲/拍号/小节/音符）"""
    lines = [label]
    for key, tag in (("标题", "workTitle"), ("标题", "title"), ("作曲", "composer"), ("作曲", "creator")):
        if len(lines) > 3:
            break
        m = re.search(r"<metaTag name=\"%s\">(.*?)</metaTag>" % tag, xml)
        if m and m.group(1).strip():
            lines.append("%s: %s" % (key, m.group(1).strip()))
            break
    if len(lines) < 3:
        m = re.search(r"<title>(.*?)</title>", xml)
        if m and m.group(1).strip():
            lines.append("标题: " + m.group(1).strip())
    m = re.search(r"<sig>\s*<nom>(\d+)</nom>\s*<den>(\d+)</den>", xml)
    if m:
        lines.append("拍号: %s/%s" % (m.group(1), m.group(2)))
    notes = len(re.findall(r"<Note>", xml))
    measures = len(re.findall(r"<Measure>", xml))
    lines.append("小节: %d · 音符: %d" % (measures, notes))
    return "\n".join(lines)


def extract_xml_score(data):
    """直接 XML 乐谱（mscx/musicxml）"""
    try:
        xml = data.decode("utf-8", "replace")
    except Exception:
        return None
    if "<score-partwise" in xml or "<ScorePartwise" in xml:
        return _score_summary(xml, "MusicXML 乐谱")
    if "<museScore" in xml or "<musescore" in xml:
        return _score_summary(xml, "MuseScore 乐谱（XML）")
    return None


def extract_mscz(data):
    """MuseScore/Finale 乐谱包：zip 内含 .mscx/.mscz/.musicxml XML"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        zf = None
    if zf is None:
        return extract_xml_score(data)
    names = zf.namelist()
    for nm in names:
        if nm.lower().endswith((".mscx", ".mscx.orig", ".xml", ".musicxml")):
            try:
                xml = zf.read(nm).decode("utf-8", "replace")
            except Exception:
                continue
            r = _score_summary(xml, "MuseScore 乐谱（压缩包）" if nm.endswith((".mscx", ".mscx.orig")) else "MusicXML 乐谱（压缩包）")
            if r:
                return r
    return "MuseScore/Finale 乐谱包：内部 XML 未找到（%d 个部件）" % len(names)


def extract_xps(data):
    """XPS/OpenXPS：zip + .fpage XML 文本"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        return None
    parts = zf.namelist()
    out = ["XPS 文档（XML Paper Specification）", "包内 %d 个部件" % len(parts)]
    texts = []
    for nm in parts:
        if nm.lower().endswith((".fpage", ".fdoc")):
            try:
                x = zf.read(nm).decode("utf-8", "replace")
                texts.extend(t for t in re.findall(r'<Glyphs[^>]*UnicodeString="([^"]*)"', x) if t.strip())
            except Exception:
                pass
    if texts:
        out.append("提取文本: " + " ".join(texts[:80])[:600])
    return "\n".join(out)


def extract_json5(data):
    """JSON5：去注释/尾逗号后解析（零依赖子集）"""
    try:
        text = data.decode("utf-8", "replace")
    except Exception:
        return None
    # JSON5 允许前置注释/空白（BOM/注释/换行），先去注释再判断是否对象/数组
    def strip_js_comments(s):
        out = []
        i = 0
        n = len(s)
        in_str = False
        q = ""
        while i < n:
            c = s[i]
            if in_str:
                out.append(c)
                if c == "\\" and i + 1 < n:
                    out.append(s[i + 1])
                    i += 2
                    continue
                if c == q:
                    in_str = False
                i += 1
                continue
            if c in "\"'":
                in_str = True
                q = c
                out.append(c)
                i += 1
                continue
            if c == "/" and i + 1 < n and s[i + 1] == "/":
                while i < n and s[i] != "\n":
                    i += 1
                continue
            if c == "/" and i + 1 < n and s[i + 1] == "*":
                i += 2
                while i + 1 < n and not (s[i] == "*" and s[i + 1] == "/"):
                    i += 1
                i += 2
                continue
            out.append(c)
            i += 1
        return "".join(out)

    clean = strip_js_comments(text)
    if not clean.lstrip().startswith(("{", "[")):
        return None
    clean = re.sub(r",\s*([}\]])", r"\1", clean)
    # JSON5 单引号字符串 → 双引号（处理 \' 与 \" 转义）
    def quotes_to_double(s):
        out = []
        i = 0
        n = len(s)
        q = None
        while i < n:
            c = s[i]
            if q:
                if c == "\\" and i + 1 < n:
                    nxt = s[i + 1]
                    if q == "'" and nxt == "'":
                        out.append("'")       # \' → '（双引号串内合法）
                    else:
                        out.extend((c, nxt))
                    i += 2
                    continue
                if c == q:
                    q = None
                    out.append('"')
                else:
                    out.append(c)
            else:
                if c == "'":
                    q = "'"
                    out.append('"')
                else:
                    out.append(c)
            i += 1
        return "".join(out)

    clean = quotes_to_double(clean)
    # JSON5 未加引号键 → 加双引号（仅匹配键后跟冒号：字面量字母/下划线/$ 开头）
    clean = re.sub(r"([{,]\s*)([A-Za-z_$][\w$]*)(\s*:)", r'\1"\2"\3', clean)
    try:
        import json
        obj = json.loads(clean)
    except Exception:
        return "JSON5：解析失败（该文件可能含更复杂 JSON5 特性，浏览器内为 JSON5 子集）"

    def brief(o, depth=0):
        if isinstance(o, dict):
            items = list(o.items())[:12]
            return "{%s}" % ", ".join("%s: %s" % (k, brief(v, depth + 1)) for k, v in items)
        if isinstance(o, list):
            return "[%s]" % ", ".join(brief(v, depth + 1) for v in o[:12])
        if isinstance(o, str):
            return repr(o)[:40]
        return repr(o)[:40]

    return "\n".join(["JSON5 数据", "根对象: " + brief(obj)[:800]])


def extract_xml_text(data):
    """通用 XML 文本提取：<t>/<text>/<w:t> 等文本节点（AbiWord/FictionBook/X3D/UOF/工程文件）"""
    try:
        xml = data.decode("utf-8", "replace")
    except Exception:
        return None
    if not xml.lstrip().startswith("<?xml") and "<html" not in xml[:200]:
        return None
    texts = re.findall(r"<(?:t|text|w:t|p|td|th)[^>]*>([^<]{1,200})</", xml, re.I)
    texts = [t.strip() for t in texts if t.strip()]
    out = ["XML 文本提取"]
    if texts:
        out.append("文本片段: %d" % len(texts))
        out.append(" ".join(texts[:60])[:700])
    else:
        out.append("（未提取到文本节点，仅结构）")
    return "\n".join(out)


def extract_mhtml(data):
    """MHTML：MIME 分隔 → HTML 正文 + 资源清单"""
    try:
        text = data.decode("utf-8", "replace")
    except Exception:
        return None
    if "--=_NextPart" not in text[:100000] and "\r\nMIME-Version:" not in text[:5000].upper() and "Content-Type: multipart" not in text[:5000].lower():
        return None
    parts = re.findall(r"Content-Type:\s*([^\r\n]+)[\s\S]*?Content-Transfer-Encoding:\s*(\S+)[\r\n]{2}([\s\S]*?)(?=\r\n--|$)", text, re.I)
    out = ["MHTML 网页归档", "MIME 部件: %d" % len(parts)]
    for i, (ct, enc, body) in enumerate(parts[:20]):
        ct = ct.strip()
        if "text/html" in ct:
            html = body if enc.lower() == "8bit" or "quoted" not in enc.lower() else body.replace("=\r\n", "").replace("=3D", "=")
            m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
            if m:
                out.append("HTML 标题: %s" % m.group(1).strip()[:80])
            m = re.search(r"<body[^>]*>([\s\S]*?)</body>", html, re.I)
            if m:
                txt = re.sub(r"<[^>]+>", " ", m.group(1))
                txt = re.sub(r"\s+", " ", txt).strip()
                if txt:
                    out.append("正文: " + txt[:400])
        else:
            out.append("部件 %d: %s (%d B)" % (i + 1, ct.split(";")[0], len(body)))
    return "\n".join(out)


def extract_dif(data):
    """DIF 数据交换格式：-1,0 元数据表 + 数据表"""
    try:
        text = data.decode("utf-8", "replace")
    except Exception:
        return None
    if "TABLE" not in text[:2000].upper() and "-1,0" not in text[:500]:
        return None
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    out = ["DIF 数据交换表格"]
    in_data = False
    rows = 0
    for i, ln in enumerate(lines):
        if ln == "-1,0":
            if i + 1 < len(lines) and lines[i + 1].upper() == "DATA":
                in_data = True
                continue
            if i + 1 < len(lines) and lines[i + 1].upper() == "EOD":
                break
        if in_data and ln.startswith("0,1"):
            rows += 1
    out.append("数据行: %d" % rows)
    return "\n".join(out)


def extract_slk(data):
    """SYLK：ID;P 表头 + C;X/Y;K 单元格"""
    try:
        text = data.decode("utf-8", "replace")
    except Exception:
        return None
    if not text[:100].startswith("ID;P"):
        return None
    cells = 0
    for ln in text.splitlines():
        if ";K" in ln:
            cells += 1
    out = ["SYLK 电子表格（Symbolic Link）"]
    out.append("单元格: %d" % cells)
    for ln in text.splitlines()[:8]:
        if ln.startswith("C;") and ";K" in ln:
            out.append("  " + ln[:80])
    return "\n".join(out)


def extract_pages(data):
    """Apple Pages 文档：zip 容器（index.xml/iWork 文本提取）"""
    if data[:2] != b"PK":
        return None
    r = extract_zip_xml(data, "pages")
    if r and "压缩文档包" in r:
        return "Apple Pages 文档\n" + r
    return r


def parse_ppt_ole(data):
    """老版 PowerPoint（.ppt/.pps）：OLE 复合文档 + PowerPoint 流探测"""
    if data[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return None
    out = ["PowerPoint 演示（OLE 复合文档，97-2003 二进制）"]
    r = extract_ole(data)
    if r:
        out.append("包结构: " + r[:200])
    low = data.lower()
    ppt_mark = b"PowerPoint Document" in low or b"PowerPoint 8.0" in low
    if ppt_mark:
        out.append("探测: PowerPoint Document 流存在")
    txt = data.decode("latin1", "replace")
    import re as _re
    texts = _re.findall(rb"[\x20-\x7e]{6,}", data)
    words = [w.decode("latin1") for w in texts if b"\x00" not in w][:10]
    if words:
        out.append("可读串: " + " | ".join(words)[:160])
    out.append("文件大小: %d B" % len(data))
    return "\n".join(out)


def extract_document(data, name):
    lower = name.lower()
    if lower.endswith((".docx", ".docm", ".dotx", ".dotm")):
        return extract_docx(data)
    if lower.endswith((".doc", ".dot")):
        return extract_ole(data)  # OLE 复合文档（Word 97-2003）
    if lower.endswith(".xls"):
        return extract_ole(data)  # OLE 复合文档（Excel 97-2003 二进制，UTF-16 正文扫描）
    if lower.endswith((".xlsx", ".xlsm", ".xltx", ".xltm")):
        return extract_xlsx(data)
    if lower.endswith((".pptx", ".pptm", ".potx")):
        return extract_pptx(data)
    if lower.endswith((".ppt", ".pps")):
        r = parse_ppt_ole(data)
        if r:
            return r
        return "PowerPoint 演示（二进制，仅识别）；大小 %d B" % len(data)
    if lower.endswith((".odt", ".ott", ".odm", ".ods", ".ots", ".odp", ".otp")):
        kind = lower.rsplit(".", 1)[-1]
        return extract_odt(data, kind)
    if lower.endswith(".epub"):
        return extract_epub(data)
    if lower.endswith(".rtf"):
        return extract_rtf(data)
    if lower.endswith((".mscz", ".mscx", ".musx", ".musicxml")):
        return extract_mscz(data)
    if lower.endswith((".xps", ".oxps")):
        return extract_xps(data)
    if lower.endswith(".json5"):
        return extract_json5(data)
    # ---- v2.8.3 新增：XML 家族 / MHTML / DIF / SLK / 工程文件 ----
    if lower.endswith((".abw", ".zabw", ".fb2", ".uot", ".uos", ".x3d")):
        if lower.endswith(".zabw"):
            try:
                import gzip
                data = gzip.decompress(data)
            except Exception:
                return "压缩 AbiWord 文档：gzip 解压失败"
        r = extract_xml_text(data)
        if r:
            return r
        return "该文档（%s）为 XML 格式但解析未命中文本节点" % lower
    if lower.endswith((".sxw", ".stw", ".sxc", ".stc", ".uop", ".sxi", ".sti", ".potm", ".ppsm", ".ppsx", ".thmx", ".xlam", ".csproj", ".vcxproj")):
        return extract_zip_xml(data, lower)
    if lower.endswith((".mhtml", ".mht")):
        r = extract_mhtml(data)
        if r:
            return r
    if lower.endswith(".dif"):
        r = extract_dif(data)
        if r:
            return r
    if lower.endswith(".slk"):
        r = extract_slk(data)
        if r:
            return r
    # ---- v2.8.9：老式表格二进制 / OLE 表族 / zip 表族 ----
    r = extract_spreadsheet(data, lower)
    if r:
        return r
    # ---- v2.8.12：笔记 / WPS 演示 ----
    if lower.endswith((".onepkg", ".onetoc2")):
        return extract_ole(data)  # OneNote 包/目录（OLE 复合文档）
    if lower.endswith((".dps", ".dpt")):
        return "WPS 演示专有二进制（%s）：金山私有格式，仅识别头；大小 %d B" % (lower.rsplit(".", 1)[-1], len(data))
    # ---- v2.8.14：Outlook 邮件 ----
    if lower.endswith(".msg"):
        return extract_ole(data)  # Outlook MSG（OLE 复合文档）
    # ---- v2.8.15：Pages / WPS / WordPerfect / Write ----
    if lower.endswith(".pages"):
        return extract_pages(data)
    if lower.endswith((".wps", ".wpt")):
        if data[:2] == b"PK":
            return extract_zip_xml(data, lower)  # WPS 新版 zip XML
        return extract_ole(data)                  # WPS 旧版 OLE
    if lower.endswith(".wpd"):
        return extract_ole(data)  # WordPerfect（OLE 尝试，兜底走暂不支持）
    if lower.endswith(".wri"):
        return extract_ole(data)  # Microsoft Write（OLE 复合文档）
    return "暂不支持该文档格式（%s）" % lower


# ---- v2.8.9 新增：老式表格二进制 / OLE 表族 / zip 表族 ----
def parse_lotus(data, kind):
    """Lotus 1-2-3（wk1/wk3）、MS Works（wks）、Quattro Pro（wb2）二进制头"""
    out = None
    if kind in ("wk1", "wk3"):
        if data[:2] == b"\x00\x00" and len(data) >= 4:
            rel = "1.x" if data[2:4] == b"\x02\x00" else "2.x/3.x"
            out = ["Lotus 1-2-3 工作表（BIFF，%s）" % rel]
    elif kind == "wks":
        if data[:1] == b"\xff":
            out = ["Microsoft Works 电子表格（WKS）"]
    elif kind == "wb2":
        if data[:4] == b"QPRO":
            out = ["Corel Quattro Pro 工作表（QPRO 二进制）"]
        elif data[:2] == b"\x00\x00" and data[2:4] in (b"\x02\x00", b"\x04\x00"):
            out = ["Quattro Pro 工作表（BIFF 兼容）"]
    if out is None:
        return None
    out.append("文件大小: %d B" % len(data))
    # 扫描可见 ASCII 文本片段（最多 12 条）
    found, cur, start = 0, [], None
    for i, b in enumerate(data[:min(len(data), 1 << 18)]):
        if 32 <= b < 127:
            if cur is None:
                cur, start = [], i
            cur.append(chr(b))
        else:
            if cur and len(cur) >= 4:
                found += 1
                out.append("文本: " + "".join(cur)[:40])
                if found >= 12:
                    break
            cur = None
    if cur and len(cur) >= 4 and found < 12:
        out.append("文本: " + "".join(cur)[:40])
    return "\n".join(out)


def extract_spreadsheet(data, name):
    lower = name.lower()
    ext = lower.rsplit(".", 1)[-1] if "." in name else ""
    if ext in ("wk1", "wk3", "wks", "wb2"):
        r = parse_lotus(data, ext)
        if r:
            return r
    if ext in ("xla", "xlt", "xlw", "et", "ett"):
        return extract_ole(data)  # OLE 复合文档（加载宏/模板/工作区/WPS 表）
    if ext in ("xlsb", "numbers", "keynote"):
        r = extract_zip_xml(data, lower)
        if r:
            return r
        return "该表格/文档为 ZIP 容器但无 XML 文本可提取"
    return None


if __name__ == "__main__":
    data = open(sys.argv[1], "rb").read()
    print(extract_document(data, sys.argv[1]))
