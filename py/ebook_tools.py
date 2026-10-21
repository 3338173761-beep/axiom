# -*- coding: utf-8 -*-
"""ebook_tools.py — 电子书容器引擎（零依赖）
覆盖：PalmDB(.pdb/.prc 记录列表)、Palm Markup Language(.pml 文本)、
Mobipocket(.mobi 已在 media_meta，此处 pdb/prc 通用 PalmDB 头)
"""

import struct
import re


def parse_palmdb(data):
    """Palm Database 头：名称/属性/记录数（78 字节头 + 记录偏移表）"""
    if len(data) < 78:
        return None
    name = data[0:32].split(b"\x00")[0].decode("latin1", "replace")
    attr, ver = struct.unpack(">HH", data[32:36])
    ctime, mtime, btime, mod = struct.unpack(">IIII", data[36:52])
    appinfo, sortinfo = struct.unpack(">II", data[52:60])
    typ, creator = struct.unpack(">II", data[60:68])
    uid, nxt = struct.unpack(">II", data[68:76])
    (num,) = struct.unpack(">H", data[76:78])
    out = ["Palm Database（PalmDB）"]
    out.append("数据库名: %s" % (name or "(未命名)"))
    out.append("类型/创建者: %s/%s" % (typ.to_bytes(4, "big").decode("latin1", "replace"),
                                      creator.to_bytes(4, "big").decode("latin1", "replace")))
    out.append("记录数: %d · 属性 0x%04X · 版本 %d" % (num, attr, ver))
    offs = []
    for i in range(min(num, 6)):
        if 78 + i * 4 + 4 > len(data):
            break
        (o,) = struct.unpack(">I", data[78 + i * 4:82 + i * 4])
        offs.append(o)
    if offs:
        out.append("记录偏移(前%d): %s" % (len(offs), ", ".join(str(o) for o in offs)))
    return "\n".join(out)


def parse_pml(data):
    """Palm Markup Language：标签化文本（/B 粗体、/S 斜体等）"""
    try:
        text = data.decode("utf-8", "replace")
    except Exception:
        return None
    if not re.search(r"^.{0,200}?<P>", text, re.S) and "PML" not in text[:200]:
        # PML 文本以 <P> 段落等标签开头
        if not any(tag in text[:500] for tag in ("<P>", "<BR>", "/B", "/S", "<IMAGE")):
            return None
    out = ["Palm Markup Language（Palm 电子书文本）"]
    plain = re.sub(r"<[^>]+>", "", text)
    plain = re.sub(r"/[A-Z]", "", plain)
    out.append("字符数: %d" % len(plain))
    m = re.search(r"<P>([^<]{1,120})", text)
    if m:
        out.append("开头: " + m.group(1).strip())
    return "\n".join(out)


def parse_ebook(data, filename):
    fn = (filename or "").lower()
    ext = fn.rsplit(".", 1)[-1] if "." in fn else ""
    if ext in ("pdb", "prc"):
        r = parse_palmdb(data)
        if r:
            return r
    if ext == "pml":
        r = parse_pml(data)
        if r:
            return r
    for parser in (parse_palmdb, parse_pml):
        try:
            r = parser(data)
        except Exception:
            continue
        if r is not None:
            return r
    if ext:
        return "该电子书格式（.%s）暂无解析器；大小 %d 字节。" % (ext, len(data))
    return "未知电子书二进制：%d 字节" % len(data)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        with open(sys.argv[1], "rb") as f:
            print(parse_ebook(f.read(), sys.argv[1]))
