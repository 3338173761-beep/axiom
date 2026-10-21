# -*- coding: utf-8 -*-
"""daw_tools.py — DAW 工程引擎（零依赖）
覆盖：Ableton Live Set(.als, gzip XML)、LMMS Project(.mmpz, gzip XML)、
Audacity Project(.aup3, SQLite 数据库)
"""

import gzip
import re


def _xml_texts(xml, tags=("name", "title", "value", "text")):
    out = []
    for tag in tags:
        for m in re.finditer(r"<%s[^>]*>([^<]{1,200})</%s>" % (tag, tag), xml, re.I):
            t = m.group(1).strip()
            if t and t not in out:
                out.append(t)
    return out


def parse_als(data):
    try:
        xml = gzip.decompress(data).decode("utf-8", "replace")
    except Exception:
        return None
    if "<Ableton" not in xml[:5000] and "LiveSet" not in xml[:5000]:
        return None
    out = ["Ableton Live Set（Live 工程）"]
    m = re.search(r"<MajorVersion[^>]*>(\d+)</MajorVersion>", xml)
    if m:
        out.append("主版本: " + m.group(1))
    names = []
    for tag in ("Name", "Value"):
        names += _xml_texts(xml, (tag,))
    uniq = []
    for n in names:
        if n and n not in uniq:
            uniq.append(n)
    if uniq:
        out.append("名称/值: " + ", ".join(uniq[:10]))
    out.append("XML 规模: %d 字符" % len(xml))
    return "\n".join(out)


def parse_mmpz(data):
    try:
        xml = gzip.decompress(data).decode("utf-8", "replace")
    except Exception:
        return None
    if "<lmms-project" not in xml[:5000] and "<project" not in xml[:3000]:
        return None
    out = ["LMMS Project（Linux MultiMedia Studio 工程）"]
    m = re.search(r"<lmms-project[^>]*>", xml)
    if m:
        # 提取 version / name 属性
        for attr, key in (("version", "版本"), ("name", "工程名")):
            a = re.search(attr + r"=['\"]([^'\"]+)", m.group(0))
            if a:
                out.append("%s: %s" % (key, a.group(1)))
    out.append("乐器/轨道标签: " + ", ".join(sorted(set(re.findall(r"<([a-zA-Z0-9_]+)[ >]", xml)) & set(
        "song instruments instrument effectcontrols automationpattern pattern bb track trackcontainer clip".split()))[:12]))
    return "\n".join(out)


def parse_aup3(data):
    """Audacity 3 工程 = SQLite 数据库"""
    if data[:16] != b"SQLite format 3\x00":
        return None
    out = ["Audacity Project 3（SQLite 工程数据库）"]
    out.append("数据库大小: %d B" % len(data))
    # 非空字符串表名（只读探测）
    names = re.findall(rb"[A-Za-z_]{3,32}", data[:80000])
    cand = []
    for n in names:
        try:
            s = n.decode("ascii")
        except Exception:
            continue
        if any(k in s for k in ("project", "clip", "track", "schema", "db", "table")):
            if s not in cand:
                cand.append(s)
    if cand:
        out.append("相关表名线索: " + ", ".join(cand[:10]))
    return "\n".join(out)


def parse_band(data):
    """GarageBand 工程（.band）：zip 容器列内部件 / 二进制头兜底"""
    if data[:2] == b"PK":
        import io as _io, zipfile as _zip
        try:
            zf = _zip.ZipFile(_io.BytesIO(data))
            names = zf.namelist()
            out = ["GarageBand 工程（zip 容器）"]
            out.append("包内部件: %d" % len(names))
            shown = [n for n in names if not n.endswith("/")][:12]
            if shown:
                out.append("文件: " + ", ".join(shown))
            return "\n".join(out)
        except Exception:
            pass
    return "GarageBand 工程（目录 bundle / 二进制，仅识别）；大小 %d B，头 %s" % (
        len(data), " ".join("%02X" % b for b in data[:16]))


def parse_daw(data, filename):
    fn = (filename or "").lower()
    ext = fn.rsplit(".", 1)[-1] if "." in fn else ""
    if ext == "als":
        r = parse_als(data)
        if r:
            return r
    if ext == "mmpz":
        r = parse_mmpz(data)
        if r:
            return r
    if ext == "aup3":
        r = parse_aup3(data)
        if r:
            return r
    if ext == "band":
        r = parse_band(data)
        if r:
            return r
    # 魔数兜底
    for parser in (parse_als, parse_mmpz, parse_aup3, parse_band):
        try:
            r = parser(data)
        except Exception:
            continue
        if r is not None:
            return r
    # 魔数兜底
    for parser in (parse_als, parse_mmpz, parse_aup3):
        try:
            r = parser(data)
        except Exception:
            continue
        if r is not None:
            return r
    if ext:
        return "该 DAW 工程格式（.%s）暂无解析器；大小 %d 字节。" % (ext, len(data))
    return "未知 DAW 工程二进制：%d 字节" % len(data)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        with open(sys.argv[1], "rb") as f:
            print(parse_daw(f.read(), sys.argv[1]))
