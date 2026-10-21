# -*- coding: utf-8 -*-
"""font_tools.py — 字体容器引擎（零依赖）
覆盖：WOFF（zlib 压缩字体）、TTC/OTC（字体集合）、PFM（Printer Font Metrics）、
EOT（Embedded OpenType 头探测）
"""

import struct


def parse_woff(data):
    if data[:4] != b"wOFF":
        return None
    if len(data) < 44:
        return None
    flavor = data[4:8].decode("latin1", "replace")
    length = struct.unpack("<I", data[8:12])[0]
    n_tables = struct.unpack("<H", data[12:14])[0]
    total_sfnt = struct.unpack("<I", data[16:20])[0]
    out = ["Web Open Font Format（WOFF）"]
    out.append("字体风格: %s（%s）" % (flavor, {
        "OTTO": "OpenType/CFF", "ttcf": "TrueType 集合", "true": "TrueType"}.get(flavor, "?")))
    out.append("总大小: %d B · 未压缩字体数据: %d B · 表: %d" % (length, total_sfnt, n_tables))
    tables = []
    pos = 44
    for _ in range(min(n_tables, 20)):
        if pos + 32 > len(data):
            break
        tag = data[pos:pos + 4].decode("latin1", "replace")
        off = struct.unpack("<I", data[pos + 4:pos + 8])[0]
        (clen,) = struct.unpack("<I", data[pos + 8:pos + 12])
        tables.append("%s(%d B)" % (tag.strip(), clen))
        pos += 32
    if tables:
        out.append("表: " + " ".join(tables))
    return "\n".join(out)


def parse_collection(data):
    """TTC / OTC：ttcf 字体集合"""
    if data[:4] != b"ttcf":
        return None
    if len(data) < 16:
        return None
    ver = struct.unpack(">I", data[4:8])[0]
    n_fonts = struct.unpack(">I", data[8:12])[0]
    out = ["字体集合（TTC/OTC）"]
    out.append("版本: 0x%08X · 内嵌字体: %d" % (ver, n_fonts))
    if n_fonts <= 64:
        names = []
        pos = 12
        for i in range(min(n_fonts, 16)):
            if pos + 4 > len(data):
                break
            (off,) = struct.unpack(">I", data[pos:pos + 4])
            pos += 4
            if off + 12 <= len(data) and data[off:off + 4] in (b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf"):
                name_id = 4
                try:
                    if data[off:off + 4] == b"\x00\x01\x00\x00":
                        # sfnt 版本 1.0：name 表在表目录
                        nt = struct.unpack(">H", data[off + 4:off + 6])[0]
                        for t in range(nt):
                            tpos = off + 12 + t * 16
                            if data[tpos:tpos + 4] == b"name":
                                (st, so) = struct.unpack(">HH", data[tpos + 8:tpos + 12])
                                npos = off + so + 2
                                cnt = struct.unpack(">H", data[npos:npos + 2])[0]
                                for r in range(cnt):
                                    rpos = npos + 2 + r * 12
                                    pid, eid, lid, nid, ln, lo = struct.unpack(">HHHHHH", data[rpos:rpos + 12])
                                    if nid == 4 and pid in (0, 3) and lid in (0, 1033, 0x409):
                                        raw = data[off + so + lo:off + so + lo + ln]
                                        names.append(raw.decode("utf-16-be", "replace").strip("\x00") if eid in (0, 3) else raw.decode("latin1", "replace"))
                                        break
                                break
                except Exception:
                    pass
        if names:
            out.append("名称: " + " / ".join(names[:8]))
    return "\n".join(out)


def parse_pfm(data):
    """Printer Font Metrics：版本 + 长度 + 点数"""
    if len(data) < 4:
        return None
    (ver,) = struct.unpack("<H", data[0:2])
    (len_meta,) = struct.unpack("<I", data[4:8])
    if ver not in (0x100, 0x200, 0x300):
        return None
    out = ["Printer Font Metrics（PFM）· 版本 0x%04X" % ver]
    try:
        n_points = struct.unpack("<I", data[60:64])[0] if ver == 0x300 else 0
        out.append("度量数据: %d B" % len_meta)
        if n_points:
            out.append("点数: %d" % n_points)
        # 扩展区常见 'W' + face
        pos = 0x60
        if pos + 6 <= len(data) and data[pos:pos + 2] == b"\x01\x01":
            seg = data[pos + 4:pos + 4 + min(60, len(data) - pos - 4)]
            face = seg.split(b"\x00")[0].decode("cp1252", "replace")
            if face:
                out.append("字体名: " + face)
    except Exception:
        pass
    return "\n".join(out)


def parse_eot(data):
    """Embedded OpenType：头探测（size + 版本 + 字体名偏移）"""
    if len(data) < 82:
        return None
    try:
        (esz,) = struct.unpack("<I", data[0:4])
        (ver,) = struct.unpack("<I", data[4:8])
    except Exception:
        return None
    if ver != 0x00020001:
        return None
    out = ["Embedded OpenType（EOT）· v2.0"]
    out.append("文件大小声明: %d B（实际 %d B）" % (esz, len(data)))
    try:
        name_off = struct.unpack("<I", data[12:16])[0]
        name_len = struct.unpack("<I", data[16:20])[0]
        if name_off and name_len and name_off + name_len <= len(data):
            nm = data[name_off:name_off + name_len].decode("utf-16-le", "replace").strip("\x00")
            if nm:
                out.append("字体名: " + nm)
    except Exception:
        pass
    return "\n".join(out)


def parse_font(data, filename):
    fn = (filename or "").lower()
    ext = fn.rsplit(".", 1)[-1] if "." in fn else ""
    if ext == "woff":
        r = parse_woff(data)
        if r:
            return r
    if ext in ("ttc", "otc"):
        r = parse_collection(data)
        if r:
            return r
    if ext == "pfm":
        r = parse_pfm(data)
        if r:
            return r
    if ext == "eot":
        r = parse_eot(data)
        if r:
            return r
    for parser in (parse_woff, parse_collection, parse_pfm, parse_eot):
        try:
            r = parser(data)
        except Exception:
            continue
        if r is not None:
            return r
    if ext:
        return "该字体格式（.%s）暂无解析器；大小 %d 字节。" % (ext, len(data))
    return "未知字体二进制：%d 字节" % len(data)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        with open(sys.argv[1], "rb") as f:
            print(parse_font(f.read(), sys.argv[1]))
