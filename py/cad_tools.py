# -*- coding: utf-8 -*-
"""cad_tools.py — CAD 文本实体引擎（零依赖，纯文本解析）
覆盖：DXF（实体统计）、IGES/IGS（类型码统计）、SAT（ACIS 文本）、STEP/STP（EXPRESS 实体）
均为 ASCII/UTF-8 文本格式，浏览器内直接解析。
"""

import re


def parse_dxf(data):
    """DXF：成对 group code/value，统计 SECTION 与实体类型"""
    if b"ENTITIES" not in data[:200000] and not data[:20].decode("utf-8", "replace").startswith("0"):
        return None
    try:
        text = data.decode("utf-8", "replace")
    except Exception:
        return None
    lines = text.splitlines()
    if not lines or lines[0].strip() != "0":
        # DXF 常以 0 行起（如 "0\nSECTION"）
        return None
    out = ["DXF 图纸（Drawing Exchange Format）", "文本行: %d" % len(lines)]
    sections = []
    entities = {}
    cur_section = None
    prev = None
    i = 0
    while i < len(lines):
        code = lines[i].strip()
        i += 1
        if i >= len(lines):
            break
        val = lines[i].strip()
        i += 1
        try:
            c = int(code)
        except Exception:
            continue
        if c == 0 and val == "SECTION":
            if i < len(lines):
                if lines[i].strip() == "2" and i + 1 < len(lines):
                    cur_section = lines[i + 1].strip()
                    sections.append(cur_section)
                    i += 2
            continue
        if c == 0 and val == "ENDSEC":
            cur_section = None
            continue
        if c == 0 and val and val not in ("SECTION", "ENDSEC", "EOF"):
            entities[val] = entities.get(val, 0) + 1
        prev = val
    if sections:
        out.append("段: " + ", ".join(sections[:12]))
    ents = sorted(entities.items(), key=lambda x: -x[1])[:18]
    if ents:
        out.append("实体: " + ", ".join("%s×%d" % (k, v) for k, v in ents))
    else:
        out.append("（未统计到实体，仅头部片段？）")
    return "\n".join(out)


def parse_iges(data):
    """IGES：80 列定长记录，首字段参数类型码（100-199 几何）"""
    try:
        text = data.decode("utf-8", "replace")
    except Exception:
        return None
    if len(data) < 80 * 2 or not data[:1] in (b" ", b"1", b"S"):
        # IGES 起始于 'S' 行或空行
        if not data[:80].rstrip(b"\r\n").endswith(b"S"):
            return None
    lines = text.splitlines()
    types = {}
    for ln in lines:
        if len(ln) < 72:
            continue
        seg = ln[:72].rstrip()
        if len(seg) < 8:
            continue
        try:
            t = int(seg[0:8].strip() or "0")
        except Exception:
            continue
        types[t] = types.get(t, 0) + 1
    out = ["IGES 三维模型（Initial Graphics Exchange Specification）",
           "记录: %d" % sum(types.values())]
    geom = {k: v for k, v in types.items() if 100 <= k < 200}
    if geom:
        out.append("几何实体: " + ", ".join("T%d×%d" % (k, v) for k, v in sorted(geom.items())))
    known = {k: v for k, v in types.items() if k not in geom and k not in (1, 2)}
    if known:
        out.append("其他: " + ", ".join("T%d×%d" % (k, v) for k, v in sorted(known.items())[:12]))
    return "\n".join(out)


def parse_sat(data):
    """ACIS SAT：文本头 + 实体列表（关键字行）"""
    try:
        text = data.decode("utf-8", "replace")
    except Exception:
        return None
    if not text[:40].lstrip().startswith(("ACIS", "$")):
        return None
    lines = text.splitlines()
    out = ["ACIS SAT 三维模型（Spatial ACIS）", "行: %d" % len(lines)]
    for ln in lines[:4]:
        if ln.startswith("ACIS"):
            out.append("产品: " + ln)
            break
    kws = {}
    for ln in lines:
        for kw in re.findall(r"\b(body|shell|face|loop|coedge|edge|vertex|wire|point|transform)\b", ln, re.I):
            kws[kw.lower()] = kws.get(kw.lower(), 0) + 1
    if kws:
        out.append("实体: " + ", ".join("%s×%d" % (k, v) for k, v in sorted(kws.items())))
    return "\n".join(out)


def parse_step(data):
    """STEP/STP：ISO-10303-21 EXPRESS 实体"""
    try:
        text = data.decode("utf-8", "replace")
    except Exception:
        return None
    if "ISO-10303-21" not in text[:400]:
        return None
    out = ["STEP 三维模型（ISO 10303-21 EXPRESS）"]
    m = re.search(r"FILE_DESCRIPTION\s*\(\s*\(\s*('.*?')\s*\)", text)
    if m:
        out.append("描述: " + m.group(1)[:80])
    m = re.search(r"FILE_NAME\s*\(\s*'([^']*)'", text)
    if m:
        out.append("文件名: " + m.group(1))
    m = re.search(r"FILE_NAME\([^)]*,\s*'([^']*)',", text)
    if m and len(out) < 3:
        out.append("作者: " + m.group(1))
    types = {}
    for t in re.findall(r"#[0-9]+\s*=\s*([A-Z_0-9]+)\s*\(", text):
        types[t] = types.get(t, 0) + 1
    if types:
        out.append("实体: " + ", ".join("%s×%d" % (k, v) for k, v in sorted(types.items(), key=lambda x: -x[1])[:14]))
    return "\n".join(out)


def parse_cad(data, filename):
    fn = (filename or "").lower()
    ext = fn.rsplit(".", 1)[-1] if "." in fn else ""
    if ext == "dxf":
        r = parse_dxf(data)
        if r:
            return r
    if ext in ("iges", "igs"):
        r = parse_iges(data)
        if r:
            return r
    if ext == "sat":
        r = parse_sat(data)
        if r:
            return r
    if ext in ("step", "stp"):
        r = parse_step(data)
        if r:
            return r
    for parser in (parse_dxf, parse_iges, parse_sat, parse_step):
        try:
            r = parser(data)
        except Exception:
            continue
        if r is not None:
            return r
    if ext:
        return "该 CAD 格式（.%s）暂无文本解析器；大小 %d 字节。" % (ext, len(data))
    return "未知 CAD 二进制：%d 字节" % len(data)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        with open(sys.argv[1], "rb") as f:
            print(parse_cad(f.read(), sys.argv[1]))
