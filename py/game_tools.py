# -*- coding: utf-8 -*-
"""game_tools — 游戏资源包 / 设计源文件解析（零依赖）：
  vpk Valve / wad Doom / ktx 纹理 / sketch / kra
入口：parse_game(data, filename) -> str|None
"""
import io
import os
import re
import json
import zipfile
import xml.etree.ElementTree as ET


def parse_vpk(data):
    """Valve VPK v2：12 字节头 + 目录树（ext\0 count(u16) 然后 每条：path\0name\0 + 5×u32）"""
    if len(data) < 12 or data[:2] not in (b"\x00\x00", b"\x01\x00", b"\x02\x00"):
        return None
    import struct
    ver = struct.unpack("<I", data[4:8])[0]
    tree_size = struct.unpack("<I", data[8:12])[0]
    out = ["Valve VPK 资源包 v%d" % ver]
    pos = 12
    end = min(12 + tree_size, len(data))
    count = 0
    while pos + 1 < end and count < 500:
        ext_end = data.find(b"\x00", pos)
        if ext_end < 0 or ext_end >= end:
            break
        ext = data[pos:ext_end].decode("utf-8", "replace")
        pos = ext_end + 1
        if pos + 2 > end:
            break
        n_entries = struct.unpack("<H", data[pos:pos + 2])[0]
        pos += 2
        if n_entries == 0xFFFF:  # 子目录分叉标记：递归处理（Valve 允许）
            continue
        for _ in range(n_entries):
            path_end = data.find(b"\x00", pos)
            if path_end < 0 or path_end >= end:
                break
            path = data[pos:path_end].decode("utf-8", "replace")
            pos = path_end + 1
            name_end = data.find(b"\x00", pos)
            if name_end < 0 or name_end >= end:
                break
            name = data[pos:name_end].decode("utf-8", "replace")
            pos = name_end + 1
            if pos + 20 > end:
                break
            crc, preload, archive_idx, entry_off, entry_len = struct.unpack("<IIIII", data[pos:pos + 20])
            pos += 20
            rel = os.path.join(path, name + ("." + ext if ext else ""))
            if not rel:
                continue
            size = preload + entry_len
            out.append("%s (%d bytes, 包 %d)" % (rel.replace("\\", "/"), size, archive_idx))
            count += 1
    if count:
        out.append("共 %d 项" % count)
    return "\n".join(out)


def parse_wad(data):
    """Doom WAD：'IWAD'/'PWAD' + numlumps + infotableofs；lump = 8字名+4大小+4偏移"""
    if data[:4] not in (b"IWAD", b"PWAD"):
        return None
    import struct
    kind = data[:4].decode("latin1")
    num = struct.unpack("<I", data[4:8])[0]
    table = struct.unpack("<I", data[8:12])[0]
    out = ["Doom %s · %d 个 lump" % (kind, num)]
    for i in range(min(num, 120)):
        off = table + i * 16
        if off + 16 > len(data):
            break
        name = data[off:off + 8].rstrip(b"\x00").decode("latin1", "replace")
        size = struct.unpack("<I", data[off + 12:off + 16])[0]
        out.append("- %-8s %d bytes" % (name, size))
    if num > 120:
        out.append("… 其余 %d 个省略" % (num - 120))
    return "\n".join(out)


def parse_ktx(data):
    """KTX 纹理：magic '«KTX 11»' + 端序 + gl 类型/格式/尺寸"""
    if not data.startswith(b"\xabKTX 11\xbb\r\n\x1a\n"):
        return None
    import struct
    little = struct.unpack("<I", data[12:16])[0] == 0x04030201
    fmt = ">I" if not little else "<I"
    gl_type = struct.unpack(fmt, data[16:20])[0]
    gl_fmt = struct.unpack(fmt, data[24:28])[0]
    gl_int = struct.unpack(fmt, data[28:32])[0]
    px_w = struct.unpack(fmt, data[40:44])[0]
    px_h = struct.unpack(fmt, data[44:48])[0]
    depth = struct.unpack(fmt, data[48:52])[0]
    gl = {0x1907: "RGB", 0x1908: "RGBA", 0x1906: "ALPHA", 0x1909: "LUMINANCE", 0x8D94: "R8", 0x8058: "RGBA8", 0x8051: "RGB8", 0x1401: "UNSIGNED_BYTE", 0x1406: "FLOAT", 0x8363: "UNSIGNED_SHORT_5_6_5"}
    return "\n".join([
        "KTX 纹理（Khronos）",
        "尺寸: %d × %d × %d" % (px_w, px_h, depth),
        "内部格式: %s" % gl.get(gl_int, "0x%X" % gl_int),
        "像素格式: %s / 类型: %s" % (gl.get(gl_fmt, "0x%X" % gl_fmt), gl.get(gl_type, "0x%X" % gl_type)),
    ])


def parse_sketch(data):
    """Sketch 设计源：zip 包 + document.json 页面/图层"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        return None
    names = zf.namelist()
    if "document.json" not in names:
        return None
    try:
        doc = json.loads(zf.read("document.json").decode("utf-8", "replace"))
    except Exception:
        doc = None
    out = ["Sketch 设计文件 · 包内 %d 个对象" % len(names)]
    if isinstance(doc, dict):
        pages = []
        def walk(o, depth=0):
            if isinstance(o, dict):
                cls = o.get("_class")
                if cls == "page":
                    pages.append(o.get("name", "(未命名页面)"))
                for v in o.values():
                    walk(v, depth + 1)
            elif isinstance(o, list):
                for it in o:
                    walk(it, depth + 1)
        walk(doc)
        out.append("页面: " + " / ".join(pages[:20]) if pages else "页面: (无)")
    out.append("关键文件: document.json / meta.json / user.json")
    return "\n".join(out)


def parse_kra(data):
    """Krita 图像源：zip 包 + maindoc.xml"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        return None
    names = zf.namelist()
    if "maindoc.xml" not in names:
        return None
    try:
        root = ET.fromstring(zf.read("maindoc.xml"))
    except Exception:
        root = None
    out = ["Krita 图像源文件 · 包内 %d 个对象" % len(names)]
    if root is not None:
        w = root.get("width", "?")
        h = root.get("height", "?")
        name = root.get("name", "")
        layers = len([l for l in root.iter() if l.tag.endswith("layers") and l.get("name")])
        out.append("画布: %s × %s%s" % (w, h, " · 文档名 " + name if name else ""))
    out.append("关键文件: maindoc.xml / mergedimage.png / layers")
    return "\n".join(out)


def parse_game(data, filename):
    fn = (filename or "").lower()
    if fn.endswith(".vpk"):
        r = parse_vpk(data)
        if r:
            return r
    if fn.endswith(".wad"):
        r = parse_wad(data)
        if r:
            return r
    if fn.endswith(".ktx"):
        r = parse_ktx(data)
        if r:
            return r
    if fn.endswith(".sketch"):
        r = parse_sketch(data)
        if r:
            return r
    if fn.endswith(".kra"):
        r = parse_kra(data)
        if r:
            return r
    for parser in (parse_vpk, parse_wad, parse_ktx, parse_sketch, parse_kra):
        r = parser(data)
        if r:
            return r
    return None


if __name__ == "__main__":
    import sys
    data = open(sys.argv[1], "rb").read()
    print(parse_game(data, sys.argv[1]))
