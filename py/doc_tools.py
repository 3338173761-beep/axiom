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


def extract_document(data, name):
    lower = name.lower()
    if lower.endswith((".docx", ".docm", ".dotx", ".dotm")):
        return extract_docx(data)
    if lower.endswith((".xlsx", ".xlsm", ".xltx", ".xltm")):
        return extract_xlsx(data)
    if lower.endswith((".pptx", ".pptm", ".potx")):
        return extract_pptx(data)
    if lower.endswith((".odt", ".ott", ".odm", ".ods", ".ots", ".odp", ".otp")):
        kind = lower.rsplit(".", 1)[-1]
        return extract_odt(data, kind)
    if lower.endswith(".epub"):
        return extract_epub(data)
    if lower.endswith(".rtf"):
        return extract_rtf(data)
    return "暂不支持该文档格式（%s）" % lower


if __name__ == "__main__":
    data = open(sys.argv[1], "rb").read()
    print(extract_document(data, sys.argv[1]))
