# -*- coding: utf-8 -*-
"""media_meta — 媒体/字体/镜像元数据与结构解析（wav/png/jpg/gif/psd/ttf/otf/mobi/msi）
纯标准库（struct/binascii/zlib），Pyodide 可直接运行。入口：parse_media(data, filename) -> str|None
"""
import struct
import re


def _dec(b):
    try:
        return b.decode("utf-8", "replace")
    except Exception:
        return ""


def parse_wav(data):
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    out = ["RIFF/WAVE 音频容器", "大小: %d 字节" % len(data)]
    i, fmt, dur = 12, None, 0
    while i + 8 <= len(data):
        cid, sz = data[i:i + 4], struct.unpack("<I", data[i + 4:i + 8])[0]
        if cid == b"fmt " and sz >= 16:
            af, ch, sr, br, _, bd = struct.unpack("<HHIIHH", data[i + 8:i + 24])
            fmt = (af, ch, sr, bd)
            out.append("格式: PCM=%s  声道=%d  采样率=%d Hz  位深=%d  比特率=%d bps" % (af == 1, ch, sr, bd, br))
        elif cid == b"data" and fmt:
            out.append("音频数据: %d 字节 ≈ %.1f 秒" % (sz, sz / (fmt[2] * fmt[1] * (fmt[3] // 8)) if fmt[1] and fmt[3] else 0))
        elif cid == b"LIST":
            out.append("LIST 元数据块: %d 字节（INFO 子块）" % sz)
        elif cid == b"fact":
            out.append("fact 块: %d 字节（压缩音频标记）" % sz)
        i += 8 + sz + (sz & 1)
    return out


def parse_png(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    out, i, chunks = ["PNG 图像（无损）"], 8, []
    while i + 8 <= len(data):
        ln = struct.unpack(">I", data[i:i + 4])[0]
        typ = data[i + 4:i + 8]
        chunks.append(typ.decode("latin1", "replace"))
        if typ == b"IHDR":
            w, h, bd, ct, _, _, _ = struct.unpack(">IIBBBBB", data[i + 8:i + 21])
            out.append("尺寸: %dx%d  位深: %d  颜色: %s" % (w, h, bd, {0: "灰度", 2: "RGB", 3: "调色板", 4: "灰度+Alpha", 6: "RGBA"}.get(ct, "?")))
        elif typ == b"tEXt":
            k = data[i + 8:i + 8 + ln].split(b"\x00")
            if len(k) > 1:
                out.append("文本: %s = %s" % (_dec(k[0]), _dec(k[1])))
        i += 12 + ln
    out.append("块序列: " + " ".join(chunks[:24]) + (" …" if len(chunks) > 24 else ""))
    return out


def parse_jpg(data):
    if data[:2] != b"\xff\xd8":
        return None
    out, i, mk = ["JPEG 图像（有损）", "大小: %d 字节" % len(data)], 2, []
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        m = data[i + 1]
        if m in (0xD8, 0xD9):
            mk.append("SOI/EOI")
            i += 2
            continue
        if m == 0xDA:
            mk.append("SOS")
            break
        ln = struct.unpack(">H", data[i + 2:i + 4])[0]
        if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF) and ln >= 8:
            h, w, _ = struct.unpack(">BHHB", data[i + 5:i + 10])
            mk.append("SOF%d %dx%d" % (m & 0xF, w, h))
        elif m == 0xE0:
            mk.append("JFIF")
        elif m == 0xE1:
            mk.append("EXIF" if data[i + 4:i + 6] == b"Ex" else "APP1")
        elif m == 0xEE:
            mk.append("Adobe")
        else:
            mk.append("M%02X" % m)
        i += 2 + ln
    out.append("标记: " + " ".join(mk[:20]) + (" …" if len(mk) > 20 else ""))
    return out


def parse_gif(data):
    if data[:6] not in (b"GIF87a", b"GIF89a"):
        return None
    out = ["GIF %s" % _dec(data[:6])]
    w, h, packed = struct.unpack("<HHB", data[6:11])
    gct = packed & 0x80
    out.append("逻辑屏幕: %dx%d  全局色表:%s  色深:%d bit" % (w, h, "有" if gct else "无", (packed & 7) + 1))
    frames = 0
    comments = []
    i = 13 + (3 * (2 ** ((packed & 7) + 1)) if gct else 0)
    while i + 6 <= len(data) and frames < 300:
        if data[i] == 0x2C:
            frames += 1
            i += 10
            if i + 1 < len(data):
                lp = data[i + 1]
                i += 2 + (3 * (2 ** ((lp & 7) + 1)) if lp & 0x80 else 0)
            else:
                break
            i += 1
            while i < len(data) and data[i] != 0x00:
                i += data[i] + 1
            i += 1
        elif data[i] == 0x21:
            lb = data[i + 1]
            i += 2
            if lb == 0xFE:
                cm = b""
                while i < len(data) and data[i] != 0x00:
                    n = data[i]
                    cm += data[i + 1:i + 1 + n]
                    i += 1 + n
                i += 1
                comments.append(_dec(cm))
            else:
                while i < len(data) and data[i] != 0x00:
                    i += data[i] + 1
                i += 1
        else:
            i += 1
    out.append("帧数: %d" % frames)
    for c in comments[:4]:
        out.append("注释: " + c[:80])
    return out


def parse_psd(data):
    if data[:4] != b"8BSB" or struct.unpack(">H", data[4:6])[0] not in (1, 2):
        return None
    ver = struct.unpack(">H", data[4:6])[0]
    ch, h, w, depth, mode = struct.unpack(">HIIHH", data[12:24])
    modes = {0: "Bitmap", 1: "灰度", 2: "索引", 3: "RGB", 4: "CMYK", 7: "多通道", 8: "Duotone", 9: "Lab"}
    return ["Adobe Photoshop PSD（版本 %d）" % ver,
            "尺寸: %dx%d  通道: %d  位深: %d" % (w, h, ch, depth),
            "色彩模式: %s" % modes.get(mode, "?"),
            "大小: %d 字节" % len(data)]


def parse_font(data):
    sig = data[:4]
    if sig == b"\x00\x01\x00\x00":
        kind = "TrueType"
    elif sig == b"OTTO":
        kind = "OpenType (CFF)"
    elif sig == b"true":
        kind = "Apple TrueType"
    elif sig == b"ttcf":
        return ["TrueType 字体集合（TTC）", "大小: %d 字节" % len(data)]
    else:
        return None
    if len(data) < 12:
        return [kind + " 字体（文件过小）"]
    nt = struct.unpack(">H", data[4:6])[0]
    out = ["%s 字体" % kind, "表数量: %d  大小: %d 字节" % (nt, len(data))]
    tbls = []
    for i in range(nt):
        o = 12 + 16 * i
        if o + 16 > len(data):
            break
        tag = _dec(data[o:o + 4])
        _, oo, ll = struct.unpack(">III", data[o + 4:o + 16])
        tbls.append((tag, oo, ll))
    out.append("表: " + " ".join(t for t, _, _ in sorted(tbls)[:18]))
    for tag, oo, ll in tbls:
        if tag != "name" or oo + 6 > len(data):
            continue
        try:
            cnt = struct.unpack(">H", data[oo + 2:oo + 4])[0]
            names = []
            for j in range(min(cnt, 14)):
                ro = oo + 6 + 12 * j
                if ro + 12 > len(data):
                    break
                pid, _, _, nid, sl, so = struct.unpack(">HHHHHH", data[ro:ro + 12])
                if so + sl > len(data):
                    continue
                raw = data[oo + so:oo + so + sl]
                if pid == 3:
                    txt = raw.decode("utf-16-be", "replace")
                elif pid == 1:
                    txt = raw.decode("mac_roman", "replace")
                else:
                    continue
                if nid in (1, 4) and txt:
                    names.append("%s: %s" % ("家族" if nid == 1 else "全名", txt))
            if names:
                out.append("; ".join(names[:4]))
        except Exception:
            pass
        break
    return out


def parse_mobi(data):
    if data[:4] != b"BOOK" or data[68:72] != b"MOBI":
        return None
    palm_len = struct.unpack(">I", data[4:8])[0]
    mobi_off = struct.unpack(">I", data[104:108])[0]
    if mobi_off + 100 > len(data):
        return ["Mobipocket 电子书（MOBI 头偏移异常）", "大小: %d 字节" % len(data)]
    m = data[mobi_off:mobi_off + 100]
    ver = struct.unpack(">I", m[0:4])[0]
    title_off = struct.unpack(">I", m[4:8])[0]
    title_len = struct.unpack(">I", m[8:12])[0]
    out = ["Mobipocket 电子书", "MOBI 版本: %d  大小: %d 字节" % (ver, len(data))]
    if title_off and title_len and mobi_off + title_off + title_len <= len(data):
        out.append("标题: %s" % _dec(data[mobi_off + title_off:mobi_off + title_off + title_len]).strip())
    else:
        out.append("标题: （不可用）")
    if palm_len:
        out.append("PalmDOC 记录长度: %d 字节（正文，可能压缩）" % palm_len)
    return out


def parse_ole(data):
    # OLE 复合文档（msi）：签名 + 目录扇区 → 流列表
    if data[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return None
    out = ["OLE 复合文档（MSI/旧 Office）", "大小: %d 字节" % len(data)]
    sector_sz = struct.unpack("<H", data[30:32])[0]
    sec_cnt = struct.unpack("<I", data[40:44])[0]
    dir_sid = struct.unpack("<I", data[48:52])[0]
    out.append("扇区大小: %d  总扇区: %d  目录扇区: %d" % (sector_sz, sec_cnt, dir_sid))
    # 简易：按目录扇区链解析 128 字节目录条目（name 64 + 其余）
    # 目录扇区链（sect 表）简化读取：从 header 72 起 109 个 uint32，等于扇区数则扇区链在头；否则用 FAT
    # 目录扇区链（sect 表）简化读取：从 header 72 起 109 个 uint32，等于扇区数则扇区链在头；否则用 FAT
    try:
        names = []
        visited = set()
        sid = dir_sid
        guard = 0
        while sid < sec_cnt and sid not in visited and sid != 0xFFFFFFFE and guard < 200:
            visited.add(sid)
            base = (sid + 1) * sector_sz
            for k in range(sector_sz // 128):
                e = base + k * 128
                if e + 128 > len(data):
                    break
                name_b = data[e:e + 64]
                nlen = struct.unpack("<H", data[e + 64:e + 66])[0]
                if nlen == 0:
                    continue
                nm = name_b[:nlen - 2].decode("utf-16-le", "replace")
                otype = data[e + 66]
                left, right, child = struct.unpack("<III", data[e + 68:e + 80])
                size = struct.unpack("<I", data[e + 120:e + 124])[0]
                names.append("%s %s（%d 字节）" % ("[存储]" if otype == 1 else "[流]", nm, size))
            # 下一目录扇区：简化按 FAT 链（mini-FAT 复杂，普通情况目录在 FAT 链）
            # 读取 FAT 扇区（sector 0 起）找 next
            fat_base = (0 + 1) * sector_sz
            if fat_base + 4 * (sid + 1) <= len(data):
                nxt = struct.unpack("<I", data[fat_base + 4 * sid:fat_base + 4 * sid + 4])[0]
                sid = nxt
            else:
                break
            guard += 1
        out.append("对象: %d 个" % len(names))
        out.extend(names[:40])
        if len(names) > 40:
            out.append("… 其余 %d 个省略" % (len(names) - 40))
    except Exception as e:
        out.append("目录解析受限: %s" % e)
    return out


# ---------- 容器/音频/视频头解析（SF2/DLS/FXB/FXP/VOC/AU/W64/MKV/FLV/SWF） ----------

def parse_riff(data):
    """RIFF 家族：WAV/SF2/DLS/FXB/FXP 块列表"""
    if data[:4] not in (b"RIFF", b"RF64"):
        return None
    size = struct.unpack("<I", data[4:8])[0]
    typ = data[8:12].decode("latin1", "replace")
    names = {"WAVE": "Wave 音频", "sfbk": "SoundFont 2 音色库", "DLS ": "DLS 可下载音色",
             "FXP ": "VST 预置", "FXB ": "VST 音色库", "RMID": "RIFF MIDI"}
    out = ["RIFF %s（%s, %d bytes）" % (typ, names.get(typ, "?"), size)]
    pos = 12
    n = 0
    while pos + 8 <= len(data) and pos < 12 + size:
        cid = data[pos:pos + 4].decode("latin1", "replace")
        csize = struct.unpack("<I", data[pos + 4:pos + 8])[0]
        out.append("- %-4s %d bytes" % (cid, csize))
        pos += 8 + csize + (csize & 1)
        n += 1
        if n >= 40:
            out.append("… 更多块省略")
            break
    return "\n".join(out)


def parse_voc(data):
    """Creative Voice：VOC 块头"""
    if not data.startswith(b"Creative Voice File"):
        return None
    if len(data) < 26:
        return None
    ver = struct.unpack("<H", data[20:22])[0]
    sig = struct.unpack("<H", data[22:24])[0]
    out = ["Creative Voice 音频 (VOC v%d.%d)" % (ver >> 8, ver & 0xFF), "签名: 0x%04X" % sig]
    names = {1: "语音", 2: "续接", 3: "静音", 4: "标记", 5: "文本", 6: "重复", 7: "重复结束", 8: "扩展", 9: "结束"}
    pos = 26
    n = 0
    while pos + 1 < len(data):
        bt = data[pos]
        if bt == 0:
            out.append("- 结束块")
            break
        if bt == 9:
            pos += 4
            continue
        if 1 <= bt <= 8:
            if pos + 4 > len(data):
                break
            size = data[pos + 1] | (data[pos + 2] << 8) | (data[pos + 3] << 16)
            pos += 4
        else:
            pos += 1
            continue
        out.append("- 块%d %s %d bytes" % (bt, names.get(bt, "?"), size))
        pos += size + (size & 1)
        n += 1
        if n >= 24:
            out.append("… 更多块省略")
            break
    return "\n".join(out)


def parse_au(data):
    """Sun/NeXT .au：.snd 头"""
    if data[:4] != b".snd":
        return None
    if len(data) < 24:
        return None
    rate, off, length, enc = struct.unpack(">IIII", data[4:20])
    encs = {1: "8bit μ-law", 2: "8bit linear", 3: "16bit linear", 4: "24bit", 5: "32bit", 7: "float", 27: "A-law"}
    return "\n".join([
        "Sun/NeXT 音频 (.au)",
        "采样率: %d Hz · 数据偏移: %d · 长度: %d bytes" % (rate, off, length),
        "编码: %s" % encs.get(enc, "0x%X" % enc),
    ])


def parse_w64(data):
    """Sony Wave64：riff 64 位块"""
    if data[:4] != b"riff":
        return None
    if len(data) < 64 or data[8:16] != b"WAVEfmt ":
        return "Sony Wave64 音频"
    fmt_size = struct.unpack("<I", data[16:20])[0]
    if 24 + fmt_size > len(data) or fmt_size < 16:
        return "Sony Wave64 音频"
    ch = struct.unpack("<H", data[24:26])[0]
    rate = struct.unpack("<I", data[28:32])[0]
    return "\n".join([
        "Sony Wave64 音频",
        "采样率: %d Hz · 通道: %d" % (rate, ch),
    ])


def _ebml_vint(b, pos):
    first = b[pos]
    m = 0x80
    width = 1
    while not (first & m) and width < 8:
        m >>= 1
        width += 1
    v = first & (m - 1)
    for i in range(1, width):
        if pos + i >= len(b):
            break
        v = (v << 8) | b[pos + i]
    return v, width


def parse_mkv(data):
    """Matroska/WebM：EBML 头 + DocType + 时长"""
    if data[:4] != b"\x1a\x45\xdf\xa3":
        return None
    pos = 4
    _, w = _ebml_vint(data, pos)
    pos += w
    out = ["Matroska 容器 (EBML)"]
    doc_type = None
    duration = None
    seg_size = None
    p = pos
    limit = min(len(data), 262144)
    while p + 2 < limit:
        try:
            eid, w1 = _ebml_vint(data, p)
            esize, w2 = _ebml_vint(data, p + w1)
        except Exception:
            break
        p += w1 + w2
        if p + esize > limit:
            break
        if eid == 0x4282:  # DocType
            doc_type = data[p:p + esize].decode("utf-8", "replace")
        elif eid == 0x4489 and esize in (4, 8):  # Duration
            if esize == 8:
                duration = struct.unpack(">d", data[p:p + 8])[0]
            else:
                duration = struct.unpack(">f", data[p:p + 4])[0]
        elif eid == 0x18538067 and esize <= 8:  # Segment 大小
            seg_size = esize
        p += esize
        if doc_type and duration is not None and seg_size is not None:
            break
    out.append("类型: %s" % (doc_type or "?"))
    out.append("时长: %.2f 秒" % duration if duration else "时长: (未知)")
    out.append("总大小: %d bytes" % len(data))
    return "\n".join(out)


def parse_flv(data):
    """FLV：头 + tag 计数"""
    if data[:3] != b"FLV":
        return None
    if len(data) < 9:
        return None
    ver = data[3]
    flags = data[4]
    hlen = struct.unpack(">I", data[5:9])[0]
    tags = {0x08: "音频", 0x09: "视频", 0x12: "脚本元数据"}
    counts = {}
    pos = hlen
    n = 0
    while pos + 15 <= len(data):
        if data[pos + 4] != 0:
            break
        ttype = data[pos + 4]
        tsize = struct.unpack(">I", b"\x00" + data[pos + 5:pos + 8])[0]
        counts[ttype] = counts.get(ttype, 0) + 1
        pos += 11 + tsize + 4
        n += 1
        if n > 5000:
            break
    out = ["FLV 视频 · 版本 %d%s%s" % (
        ver,
        " · 视频流" if flags & 1 else "",
        " · 音频流" if flags & 4 else "")]
    out.append("标签: %s" % " / ".join("%s×%d" % (tags.get(k, "0x%X" % k), v) for k, v in sorted(counts.items())))
    return "\n".join(out)


def parse_swf(data):
    """SWF：FWS/CWS/ZWS 头 + 版本 + 舞台尺寸（RECT）"""
    if data[:3] not in (b"FWS", b"CWS", b"ZWS"):
        return None
    if len(data) < 8:
        return None
    ver = data[3]
    size = struct.unpack("<I", data[4:8])[0]
    comp = {b"FWS": "未压缩", b"CWS": "zlib 压缩", b"ZWS": "LZMA 压缩"}[data[:3]]
    out = ["Shockwave Flash (SWF) · 版本 %d · %s · %d bytes" % (ver, comp, size)]
    # RECT：第 8 字节起，前 5 位 = nbits，随后 4×nbits 位 = Xmin Xmax Ymin Ymax
    if len(data) >= 9:
        nbits = (data[8] >> 3) & 0x1F
        if 0 < nbits <= 31:
            total = (5 + 4 * nbits + 7) // 8
            if 8 + total <= len(data):
                bits = "".join(format(data[8 + i], "08b") for i in range(total))
                p = 5
                vals = []
                ok = True
                for _ in range(4):
                    if p + nbits > len(bits):
                        ok = False
                        break
                    vals.append(int(bits[p:p + nbits], 2))
                    p += nbits
                if ok:
                    xmin, xmax, ymin, ymax = vals
                    out.append("舞台尺寸: %d×%d（坐标 %d,%d ~ %d,%d）" % (xmax - xmin, ymax - ymin, xmin, ymin, xmax, ymax))
    return "\n".join(out)


def parse_ppm(data):
    """PPM/PGM/PBM：ASCII/二进制图像头"""
    if not data[:2] in (b"P1", b"P2", b"P3", b"P4", b"P5", b"P6"):
        return None
    out = ["Portable Pixmap（PPM 族）"]
    kind = {b"P1": "PBM 位图", b"P2": "PGM 灰度文本", b"P3": "PPM 彩色文本",
            b"P4": "PBM 二进制", b"P5": "PGM 灰度二进制", b"P6": "PPM 彩色二进制"}.get(data[:2], "")
    out.append("类型: " + kind)
    head = data[2:200].decode("latin1", "replace")
    nums = re.findall(r"\d+", head)
    if len(nums) >= 2:
        out.append("尺寸: %s × %s" % (nums[0], nums[1]))
    if len(nums) >= 3:
        out.append("最大灰度/色值: %s" % nums[2])
    return "\n".join(out)


def parse_media(data, filename):
    fn = (filename or "").lower()
    ext = fn.rsplit(".", 1)[-1] if "." in fn else ""
    # 扩展名优先分派（同魔数多格式场景）
    if ext == "sf2":
        r = parse_riff(data)
        if r:
            return r
    if ext in ("voc",):
        r = parse_voc(data)
        if r:
            return r
    if ext == "au":
        r = parse_au(data)
        if r:
            return r
    if ext == "w64":
        r = parse_w64(data)
        if r:
            return r
    if ext == "mkv":
        r = parse_mkv(data)
        if r:
            return r
    if ext == "flv":
        r = parse_flv(data)
        if r:
            return r
    if ext == "swf":
        r = parse_swf(data)
        if r:
            return r
    if ext in ("ppm", "pgm", "pbm", "pnm"):
        r = parse_ppm(data)
        if r:
            return r
    for parser in (parse_wav, parse_png, parse_jpg, parse_gif, parse_psd, parse_font,
                   parse_mobi, parse_ole, parse_riff, parse_voc, parse_au, parse_w64,
                   parse_mkv, parse_flv, parse_swf, parse_ppm):
        try:
            r = parser(data)
        except Exception:
            continue
        if r is not None:
            return "\n".join(r) if isinstance(r, list) else r
    # 兜底：按扩展名给提示
    if ext:
        return "该类型（.%s）暂无结构化解析器；已识别为二进制文件，大小 %d 字节。" % (ext, len(data))
    return "未知二进制：大小 %d 字节，文件头 %s" % (len(data), " ".join("%02X" % b for b in data[:16]))
