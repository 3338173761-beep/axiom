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


def parse_fnt(data):
    # Windows FNT：FONTINFO 头 0x00 版本(2B) 0x02 总大小(4B) 0x42 类型(2B) 0x44 点阵(2B)
    if len(data) < 0x4C:
        return None
    ver = struct.unpack_from("<H", data, 0)[0]
    if ver > 0x300:
        return None
    total = struct.unpack_from("<I", data, 2)[0]
    if total == 0 or total > 64 * 1024 * 1024:
        return None
    points = struct.unpack_from("<H", data, 0x44)[0]
    pix_h = struct.unpack_from("<H", data, 0x4A)[0]
    out = ["Windows FNT 位图字体"]
    out.append("头版本: 0x%X" % ver)
    out.append("点阵: %d pt" % points)
    out.append("像素高: %d" % pix_h)
    out.append("文件大小字段: %d B" % total)
    return "\n".join(out)


def parse_pfb(data):
    # Type1 PFB：0x80 0x01 长度 + 段
    if data[:2] != b"\x80\x01" or len(data) < 6:
        return None
    seg = struct.unpack_from("<I", data, 2)[0]
    text = data[6:6 + seg].decode("latin1", "replace")
    name = ""
    for ln in text.splitlines()[:40]:
        if ln.startswith("/FontName"):
            parts = ln.split()
            name = parts[1].replace("def", "").strip() if len(parts) > 1 else ""
            break
    out = ["PostScript Type1 字体（PFB）"]
    out.append("首段: %d B" % seg)
    if name:
        out.append("字体名: " + name)
    else:
        fam = ""
        for ln in text.splitlines()[:80]:
            if ln.startswith("/FamilyName"):
                fam = ln.replace("/FamilyName", "").strip().rstrip("def").strip()
                break
        if fam:
            out.append("家族: " + fam)
    return "\n".join(out)


def parse_woff2(data):
    if data[:4] != b"wOF2" or len(data) < 48:
        return None
    ver = struct.unpack_from("<I", data, 4)[0]
    flavor = data[8:12]
    num_tables = struct.unpack_from("<H", data, 12)[0]
    size = struct.unpack_from("<I", data, 16)[0]
    out = ["WOFF2 字体"]
    out.append("字体版本: 0x%X" % ver)
    out.append("flavor: " + flavor.decode("latin1"))
    out.append("表数: %d" % num_tables)
    out.append("解压后大小: %d B" % size)
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
    if ext == "fnt":
        r = parse_fnt(data)
        if r:
            return r
    if ext == "pfb":
        r = parse_pfb(data)
        if r:
            return r
    if ext == "woff2":
        r = parse_woff2(data)
        if r:
            return r
    if ext == "fon":
        return "Windows FON（NE 资源字体）：%d B" % len(data)
    for parser in (parse_woff, parse_collection, parse_pfm, parse_eot,
                   parse_fnt, parse_pfb, parse_woff2):
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
