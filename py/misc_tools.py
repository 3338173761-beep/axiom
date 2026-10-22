# -*- coding: utf-8 -*-
"""misc_tools.py — 杂项容器引擎（零依赖）
覆盖：Windows 快捷方式(.lnk ShellLink 二进制)、BitTorrent(.torrent bencode)、
CUE 轨道表(.cue 文本)、WoT 回放(.wotreplay zip+json)、CD+G(.cdg 指令包)、
PostScript(.eps 头)、Apple 属性列表(.plist XML/二进制)
"""

import re
import json
import struct
import zipfile
import io


def parse_lnk(data):
    """Windows ShellLink：头 + 链接目标信息"""
    if len(data) < 76 or data[:4] != b"\x4c\x00\x00\x00":
        return None
    out = ["Windows ShellLink 快捷方式"]
    flags = struct.unpack("<I", data[20:24])[0]
    attrs = struct.unpack("<I", data[24:28])[0]
    out.append("标志 0x%08X · 文件属性 0x%08X" % (flags, attrs))
    # 文件定位信息（StringData，UTF-16 路径）
    if flags & 0x20000000 and len(data) >= 104:  # HasLinkInfo
        lii = struct.unpack("<I", data[76:80])[0]
        if 0 < lii < len(data) - 4:
            h = data[76 + lii:76 + lii + 28]
            if len(h) >= 28 and h[:4] == b"\x01\x00\x00\x00":
                voff, vlen = struct.unpack("<II", h[16:24])
                try:
                    vol = data[76 + lii + 28 + voff:76 + lii + 28 + voff + vlen * 2].decode("utf-16-le", "replace").strip("\x00")
                    if vol:
                        out.append("卷: " + vol)
                except Exception:
                    pass
    # 路径段：尝试抓 UTF-16 串
    try:
        seg = re.findall(r"([A-Za-z]:\\\\[^\x00]{1,120})", data[200:min(len(data), 4000)].decode("utf-16-le", "replace"))
        if seg:
            out.append("路径: " + seg[0][:120])
    except Exception:
        pass
    return "\n".join(out)


def _bdecode(b, i):
    """bencode 解码，返回 (value, i)"""
    c = b[i:i + 1]
    if c == b"i":
        j = b.index(b"e", i)
        return int(b[i + 1:j]), j + 1
    if c == b"l":
        i += 1
        lst = []
        while b[i:i + 1] != b"e":
            v, i = _bdecode(b, i)
            lst.append(v)
        return lst, i + 1
    if c == b"d":
        i += 1
        d = {}
        while b[i:i + 1] != b"e":
            k, i = _bdecode(b, i)
            v, i = _bdecode(b, i)
            d[k] = v
        return d, i + 1
    if c in (b"0", b"1", b"2", b"3", b"4", b"5", b"6", b"7", b"8", b"9"):
        j = b.index(b":", i)
        n = int(b[i:j])
        return b[j + 1:j + 1 + n], j + 1 + n
    raise ValueError("bad bencode at %d" % i)


def parse_torrent(data):
    if not data[:1] in (b"d", b"8"):
        return None
    try:
        meta, _ = _bdecode(data, 0)
    except Exception:
        return None
    if not isinstance(meta, dict):
        return None
    out = ["BitTorrent 种子元数据"]
    info = meta.get(b"info")
    if isinstance(info, dict):
        name = info.get(b"name", b"")
        if isinstance(name, bytes):
            out.append("文件名: " + name.decode("utf-8", "replace")[:80])
        fl = info.get(b"files")
        if isinstance(fl, list):
            out.append("文件数: %d" % len(fl))
            for f in fl[:8]:
                if isinstance(f, dict) and isinstance(f.get(b"path"), list):
                    p = b"/".join(x for x in f[b"path"] if isinstance(x, bytes)).decode("utf-8", "replace")
                    out.append("  " + p[:100])
        else:
            length = info.get(b"length")
            if isinstance(length, int):
                out.append("单文件大小: %d B" % length)
    tr = meta.get(b"announce")
    if isinstance(tr, bytes):
        out.append("Tracker: " + tr.decode("utf-8", "replace")[:120])
    return "\n".join(out)


def parse_cue(data):
    try:
        text = data.decode("utf-8", "replace")
    except Exception:
        return None
    if "FILE" not in text[:2000].upper():
        return None
    out = ["CUE 轨道表"]
    files = re.findall(r"FILE\s+([^\r\n]+?)\s+(?:WAVE|BINARY|MP3|AIFF)", text, re.I)
    if files:
        out.append("音频文件: " + files[0].strip()[:100])
    tracks = re.findall(r"TRACK\s+(\d+)\s+(\S+)", text, re.I)
    out.append("轨道: %d" % len(tracks))
    for t, mode in tracks[:12]:
        out.append("  TRACK %s %s" % (t, mode))
    return "\n".join(out)


def parse_wotreplay(data):
    """World of Tanks 回放 = zip + JSON 元数据"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        return None
    names = zf.namelist()
    if not names:
        return None
    out = ["World of Tanks 回放（zip 容器）"]
    out.append("内部文件: %d" % len(names))
    for n in names:
        if n.lower().endswith(".json") or n.lower().startswith("meta"):
            try:
                raw = zf.read(n)
                txt = raw.decode("utf-8", "replace")
                d = json.loads(txt)
                out.append("元数据: " + json.dumps(d, ensure_ascii=False)[:400])
            except Exception:
                pass
    return "\n".join(out)


def parse_cdg(data):
    """CD+G：98 字节指令包（16 子码包）"""
    if len(data) < 98:
        return None
    # Real CD+G is a whole number of 16-byte subcode packets whose first packet
    # carries the ASCII 'CD' marker at offset 3..4. The previous gate only tested
    # data[0] in (0x00, 0x01), so any zero-filled or incrementing buffer was
    # reported as a karaoke track -- the root cause of the UE-pak-as-CDG misfire.
    has_marker = data[3:5] == b"CD"
    packets = 0
    struct_ok = 0
    for i in range(0, len(data) - 15, 16):
        packets += 1
        if data[i + 1] < 24 and data[i + 2] in (0x2C, 0x2D, 0x2E, 0x2F, 0x36, 0x37):
            struct_ok += 1
    if not has_marker and not (packets and struct_ok * 100 >= packets * 80):
        return None
    out = ["CD+Graphics（CD+G 卡拉OK 图形轨）"]
    if has_marker:
        out.append("首包标记: 'CD' @0x03（结构合法子码包 %d/%d）" % (struct_ok, packets))
    else:
        out.append("结构合法子码包 %d/%d" % (struct_ok, packets))
    out.append("指令包: %d" % (len(data) // 98))
    cmds = {}
    for i in range(0, len(data) - 96, 98):
        cmd = data[i + 4] & 0x3F
        cmds[cmd] = cmds.get(cmd, 0) + 1
    if cmds:
        out.append("指令分布: " + ", ".join("0x%02X×%d" % (k, v) for k, v in sorted(cmds.items())))
    return "\n".join(out)


def parse_eps(data):
    """Encapsulated PostScript：%%BoundingBox 等头信息"""
    try:
        head = data[:8192].decode("latin1", "replace")
    except Exception:
        return None
    if "%%BoundingBox" not in head and not head.lstrip().startswith("%!PS"):
        return None
    out = ["Encapsulated PostScript（EPS 矢量）"]
    m = re.search(r"%%BoundingBox:\s*([^\r\n]+)", head)
    if m:
        out.append("边界框: " + m.group(1).strip())
    m = re.search(r"%%Title:\s*([^\r\n]+)", head)
    if m:
        out.append("标题: " + m.group(1).strip())
    m = re.search(r"%%Creator:\s*([^\r\n]+)", head)
    if m:
        out.append("创建者: " + m.group(1).strip())
    out.append("总大小: %d B" % len(data))
    return "\n".join(out)


def parse_plist(data):
    """Apple plist：XML 或二进制（bplist00）"""
    if data[:7] == b"bplist0":
        out = ["Apple 二进制 plist"]
        out.append("版本: " + data[6:8].decode("latin1", "replace"))
        out.append("大小: %d B" % len(data))
        return "\n".join(out)
    try:
        head = data[:2000].decode("utf-8", "replace")
    except Exception:
        return None
    if "<plist" not in head.lower():
        return None
    out = ["Apple XML plist 属性列表"]
    keys = re.findall(r"<key>([^<]+)</key>", data.decode("utf-8", "replace"))
    if keys:
        out.append("键: " + ", ".join(keys[:16]))
    return "\n".join(out)


def parse_idx(data):
    """VOBsub 字幕索引：timestamp: x,y,w,h, 页列表"""
    try:
        text = data.decode("utf-8", "replace")
    except Exception:
        return None
    if not any(k in text[:2000].upper() for k in ("# VobSub", "TIMESTAMP", "IDX", "INDEX")):
        if "timestamp:" not in text[:2000].lower():
            return None
    out = ["VOBsub 字幕索引（idx）"]
    pages = 0
    for ln in text.splitlines():
        if re.match(r"^\d{2}:\d{2}:\d{2}:\d{3}\s*:", ln):
            pages += 1
        if ln.upper().startswith("ID:"):
            out.append("  " + ln[:80])
    out.append("时间戳页: %d" % pages)
    m = re.search(r"#\s*VobSub\s*index", text, re.I)
    if m:
        out.append("标识: VobSub index")
    return "\n".join(out)


# ---- v2.8.10 新增：矢量图 / 游戏资源包 ----
def parse_ai(data):
    if data[:4] != b"%PDF" and data[:2] != b"AI":
        return None
    out = ["Adobe Illustrator 矢量文件"]
    if data[:4] == b"%PDF":
        out.append("新版封装：PDF 流（含 AI 专有流）")
        try:
            head = data[:1 << 16].decode("latin1", "replace")
            m = re.search(r"/Title\s*\(([^)]{1,60})\)", head)
            if m:
                out.append("标题: " + m.group(1))
        except Exception:
            pass
    else:
        out.append("旧版：AI 头 + PostScript")
        try:
            head = data[:1 << 15].decode("latin1", "replace")
            m = re.search(r"%%Title:\s*([^\r\n]{1,60})", head)
            if m:
                out.append("标题: " + m.group(1).strip())
        except Exception:
            pass
    return "\n".join(out)


def parse_emf(data):
    if len(data) < 88 or data[:4] != b"\x01\x00\x00\x00":
        return None
    if data[40:44] != b" EMF":
        return None
    ver = struct.unpack_from("<I", data, 44)[0]
    recs = struct.unpack_from("<I", data, 52)[0]
    out = ["Windows 增强图元（EMF）"]
    out.append("EMF 版本: %d  记录数: %d" % (ver, recs))
    r_x, r_y, r_w, r_h = struct.unpack_from("<iiii", data, 8)
    out.append("边界: %d,%d → %dx%d" % (r_x, r_y, r_w, r_h))
    return "\n".join(out)


def parse_wmf(data):
    if data[:4] == b"\xd7\xcd\xc6\x9a":
        ver = struct.unpack_from("<H", data, 4)[0]
        out = ["Windows 图元文件（WMF，Placeable）"]
        out.append("WMF 版本: 0x%04X" % ver)
        return "\n".join(out)
    if data[:2] in (b"\x01\x00", b"\x02\x00"):
        return "Windows 图元文件（WMF，标准头，版本 0x%04X）" % struct.unpack_from("<H", data, 0)[0]
    return None


def parse_unity3d(data):
    if data[:7] != b"UnityFS":
        return None
    ver = data[7:].split(b"\x00")[0].decode("latin1", "replace") if b"\x00" in data[7:64] else "?"
    out = ["Unity Web 资源包（UnityFS）"]
    out.append("Unity 版本: " + (ver or "?"))
    m = re.search(rb"m_FileName: ([^\x00]{1,80})", data[:1 << 16])
    if m:
        out.append("资产名: " + m.group(1).decode("utf-8", "replace"))
    return "\n".join(out)


def parse_bsa(data):
    if data[:4] != b"BSA\x00":
        return None
    ver = struct.unpack_from("<I", data, 4)[0]
    fo = struct.unpack_from("<I", data, 8)[0]
    out = ["Bethesda 归档（BSA）"]
    out.append("版本: %d  文件数: %d" % (ver, fo))
    return "\n".join(out)


# ---- v2.8.13 新增：Android 系统二进制 ----
def parse_art(data):
    if data[:4] != b"\x40\x03\x01\x00" or data[4:7] != b"art":
        return None
    ver = struct.unpack_from("<I", data, 7)[0]
    out = ["Android ART 运行时镜像"]
    out.append("ART 版本: %d" % ver)
    return "\n".join(out)


def parse_vdex(data):
    if data[:4] != b"vdex":
        return None
    ver = struct.unpack_from("<I", data, 4)[0]
    nb = struct.unpack_from("<I", data, 8)[0]
    out = ["Android VDEX 缓存（Validated Dex）"]
    out.append("版本: %d  Dex 数: %d" % (ver, nb))
    return "\n".join(out)


def parse_oat(data):
    # OAT = ELF 容器 + oatdata（识别 ELF 后找 "oat" 版本串）
    if len(data) < 4 or data[:4] not in (b"\x7fELF", b"\x64\x65\x79\x0a"):
        return None
    head = data[:1 << 20]
    m = re.search(rb"oat\x00(\d{1,2})\x00", head)
    if not m:
        return None
    out = ["Android OAT 可执行（ELF + oat 段）"]
    out.append("OAT 版本: " + m.group(1).decode())
    return "\n".join(out)


def parse_gp5(data):
    """Guitar Pro 乐谱（GP3/GP4/GP5）：FWH 头 + 版本 + 长度前缀文本字段"""
    if data[:3] != b"FWH" or len(data) < 16:
        return None
    ver_end = data.find(b"\x00", 3, 32)
    ver_raw = data[3:ver_end] if ver_end > 0 else data[3:16]
    out = ["Guitar Pro 乐谱"]
    out.append("版本: " + ver_raw.decode("latin1", "replace").strip())
    # GP5 用 4 字节整数长度，GP3/GP4 用 1 字节：先试 4 字节，若长度合理则采用
    fields = ["标题", "副标题", "艺术家", "专辑", "作词", "作曲", "版权", "备注"]
    pos = ver_end + 1 if ver_end > 0 else 3
    got = []
    try:
        for name in fields:
            if pos >= len(data):
                break
            four = struct.unpack_from("<I", data, pos)[0]
            if 0 < four < 4096:
                ln = four
                pos += 4
            else:
                ln = data[pos]
                pos += 1
            if ln == 0:
                continue
            if ln > 4096:
                break
            s = data[pos:pos + ln].decode("latin1", "replace").strip()
            pos += ln
            if s and len(s) < 200:
                got.append("%s: %s" % (name, s))
    except (struct.error, IndexError):
        pass
    out.extend(got)
    out.append("文件大小: %d B" % len(data))
    return "\n".join(out)


def parse_z(data):
    """Unix compress（.Z）：0x1F 0x9D LZW 头，尾部 4 字节原始大小（大端）"""
    if data[:2] != b"\x1f\x9d" or len(data) < 8:
        return None
    flags = data[2]
    magic_hdr = bool(flags & 0x01)
    maxbits = (flags >> 1) & 0x1F
    out = ["Unix compress（LZW）压缩流"]
    out.append("魔数字头: %s  最大位数: %d" % ("有" if magic_hdr else "无", maxbits))
    if len(data) >= 8:
        orig = struct.unpack(">I", data[-4:])[0]
        out.append("解压后原始大小: %d B" % orig)
    out.append("文件大小: %d B" % len(data))
    return "\n".join(out)


def parse_pak(data):
    """Quake PAK 资源包：PACK + 目录偏移/大小 → 条目列表"""
    if data[:4] != b"PACK" or len(data) < 12:
        return None
    (diroff, dirsize) = struct.unpack_from("<II", data, 4)
    n = dirsize // 64
    out = ["Quake PAK 资源包"]
    out.append("目录偏移: %d  目录大小: %d B  条目数: %d" % (diroff, dirsize, n))
    names = []
    for i in range(min(n, 24)):
        p = diroff + i * 64
        if p + 64 > len(data):
            break
        nm = data[p:p + 56].split(b"\x00")[0].decode("latin1", "replace").strip()
        if nm:
            names.append(nm)
    if names:
        out.append("条目示例: " + ", ".join(names))
    return "\n".join(out)


# ============================================================
# AES-256 (ECB) — 纯 Python 实现（Pyodide 无标准 AES；Web Crypto
# 不支持 ECB，故手写）。用于 UE pak 加密 index 解密。
# 已知向量（FIPS-197 C.3）：
#   key=000102...1f  pt=00112233445566778899aabbccddeeff
#   ct=8ea2b7ca516745bfeafc49904b496089
# ============================================================
_AES_SBOX = (
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
    0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
    0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
    0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
    0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
    0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
    0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
    0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
    0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16)
_AES_INV_SBOX = tuple(_AES_SBOX.index(i) for i in range(256))


def _aes_xtime(a):
    a <<= 1
    if a & 0x100:
        a ^= 0x11b
    return a & 0xff


def _aes_gmul(a, b):
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xff
        if hi:
            a ^= 0x1b
        b >>= 1
    return p


def _aes_key_expand(key):
    """AES-256 密钥扩展：32 字节 → 15 轮密钥（每轮 16 字节）"""
    w = [list(key[i:i + 4]) for i in range(0, 32, 4)]
    rcon = 1
    for i in range(8, 60):
        t = list(w[i - 1])
        if i % 8 == 0:
            t = t[1:] + t[:1]
            t = [_AES_SBOX[b] for b in t]
            t[0] ^= rcon
            rcon = (rcon << 1) ^ 0x11b if rcon & 0x80 else rcon << 1
        elif i % 8 == 4:
            t = [_AES_SBOX[b] for b in t]
        w.append([w[i - 8][j] ^ t[j] for j in range(4)])
    return w


def _aes_sub_bytes(s):
    for i in range(16):
        s[i] = _AES_SBOX[s[i]]


def _aes_inv_sub_bytes(s):
    for i in range(16):
        s[i] = _AES_INV_SBOX[s[i]]


def _aes_shift_rows(s):
    # 显式置换：行 r 循环左移 r 字节
    # 行0: 0,4,8,12 不变；行1: 4,8,12,0；行2: 8,12,0,4；行3: 12,0,4,8
    s[0], s[4], s[8], s[12] = s[0], s[4], s[8], s[12]
    s[1], s[5], s[9], s[13] = s[5], s[9], s[13], s[1]
    s[2], s[6], s[10], s[14] = s[10], s[14], s[2], s[6]
    s[3], s[7], s[11], s[15] = s[15], s[3], s[7], s[11]


def _aes_inv_shift_rows(s):
    s[0], s[4], s[8], s[12] = s[0], s[4], s[8], s[12]
    s[1], s[5], s[9], s[13] = s[13], s[1], s[5], s[9]
    s[2], s[6], s[10], s[14] = s[10], s[14], s[2], s[6]
    s[3], s[7], s[11], s[15] = s[7], s[11], s[15], s[3]


def _aes_mix_columns(s):
    for c in range(0, 16, 4):
        a0, a1, a2, a3 = s[c], s[c + 1], s[c + 2], s[c + 3]
        s[c] = _aes_xtime(a0) ^ (_aes_xtime(a1) ^ a1) ^ a2 ^ a3
        s[c + 1] = a0 ^ _aes_xtime(a1) ^ (_aes_xtime(a2) ^ a2) ^ a3
        s[c + 2] = a0 ^ a1 ^ _aes_xtime(a2) ^ (_aes_xtime(a3) ^ a3)
        s[c + 3] = (_aes_xtime(a0) ^ a0) ^ a1 ^ a2 ^ _aes_xtime(a3)


def _aes_inv_mix_columns(s):
    for c in range(0, 16, 4):
        a0, a1, a2, a3 = s[c], s[c + 1], s[c + 2], s[c + 3]
        s[c] = (_aes_gmul(a0, 14) ^ _aes_gmul(a1, 11) ^ _aes_gmul(a2, 13) ^ _aes_gmul(a3, 9))
        s[c + 1] = (_aes_gmul(a0, 9) ^ _aes_gmul(a1, 14) ^ _aes_gmul(a2, 11) ^ _aes_gmul(a3, 13))
        s[c + 2] = (_aes_gmul(a0, 13) ^ _aes_gmul(a1, 9) ^ _aes_gmul(a2, 14) ^ _aes_gmul(a3, 11))
        s[c + 3] = (_aes_gmul(a0, 11) ^ _aes_gmul(a1, 13) ^ _aes_gmul(a2, 9) ^ _aes_gmul(a3, 14))


def _aes_add_round_key(s, w, rnd):
    base = rnd * 4
    for c in range(4):
        for r in range(4):
            s[r + c * 4] ^= w[base + c][r]


def _aes_encrypt_block(blk, w):
    s = list(blk)
    _aes_add_round_key(s, w, 0)
    for rnd in range(1, 14):
        _aes_sub_bytes(s)
        _aes_shift_rows(s)
        _aes_mix_columns(s)
        _aes_add_round_key(s, w, rnd)
    _aes_sub_bytes(s)
    _aes_shift_rows(s)
    _aes_add_round_key(s, w, 14)
    return bytes(s)


def _aes_decrypt_block(blk, w):
    s = list(blk)
    _aes_add_round_key(s, w, 14)
    for rnd in range(13, 0, -1):
        _aes_inv_shift_rows(s)
        _aes_inv_sub_bytes(s)
        _aes_add_round_key(s, w, rnd)
        _aes_inv_mix_columns(s)
    _aes_inv_shift_rows(s)
    _aes_inv_sub_bytes(s)
    _aes_add_round_key(s, w, 0)
    return bytes(s)


def aes256_ecb_encrypt(data, key):
    """标准 AES-256-ECB 加密（data 长度须为 16 的倍数）"""
    w = _aes_key_expand(key)
    out = bytearray()
    for i in range(0, len(data), 16):
        out += _aes_encrypt_block(data[i:i + 16], w)
    return bytes(out)


def aes256_ecb_decrypt(data, key):
    """标准 AES-256-ECB 解密"""
    w = _aes_key_expand(key)
    out = bytearray()
    for i in range(0, len(data), 16):
        out += _aes_decrypt_block(data[i:i + 16], w)
    return bytes(out)


def aes256_faes_decrypt(data, key):
    """UE4 FAES 变体：ECB 解密后每块 XOR 块计数器（大端 8 字节+8 零）。
    index 解密用标准 ECB；数据块解密用本变体。防御式都提供。"""
    base = aes256_ecb_decrypt(data, key)
    out = bytearray(base)
    for i in range(0, len(data), 16):
        bidx = i // 16
        ctr = bidx.to_bytes(8, "big") + b"\x00" * 8
        for j in range(16):
            out[i + j] ^= ctr[j]
    return bytes(out)
def _pak_read_fstring(data, pos):
    """UE FString: int32 长度（>0 UTF-16LE 字符数；<0 ANSI 字节数；0 空串）"""
    if pos + 4 > len(data):
        return None, pos
    (ln,) = struct.unpack_from("<i", data, pos)
    pos += 4
    if ln > 0:
        if pos + ln * 2 > len(data):
            return None, pos
        s = data[pos:pos + ln * 2].decode("utf-16-le", "replace").rstrip("\x00")
        pos += ln * 2
        return s, pos
    if ln < 0:
        nb = -ln
        if pos + nb > len(data):
            return None, pos
        s = data[pos:pos + nb].decode("latin1", "replace").rstrip("\x00")
        pos += nb
        return s, pos
    return "", pos


def _pak_find_index(data, version):
    """定位 index 偏移/大小；返回 (off, size) 或 None"""
    if version < 3:
        if len(data) >= 44:
            (off, size) = struct.unpack_from("<qq", data, 8)
            if off >= 0 and size > 0 and off + size <= len(data):
                return (off, size)
        return None
    # Version>=3：footer 在文件尾（最后 4B magic，前 4B footer size）
    if len(data) < 56:
        return None
    if data[-4:] != b"Zong":
        # 尝试在尾部 1KB 内搜 magic（部分工具追加数据的情况）
        tail = data[-1024:]
        p = tail.rfind(b"Zong")
        if p < 0 or len(data) - (1024 - p) < 16:
            return None
        base = len(data) - 1024 + p
        fsize = struct.unpack_from("<I", data, base - 4)[0] if base >= 4 else 0
        fstart = len(data) - fsize if 0 < fsize < len(data) else base - 4
    else:
        fsize = struct.unpack_from("<I", data, -8)[0]
        fstart = len(data) - fsize if 0 < fsize < len(data) else len(data) - 52
    # footer 内布局候选：IndexOffset@0/IndexSize@8（标准）
    candidates = []
    if 0 <= fstart < len(data) - 16:
        candidates.append((fstart, fstart + 8))
    # 兜底：在尾部 128B 内暴力搜合法 qq 对
    for p in range(max(0, len(data) - 128), len(data) - 16, 2):
        (off, size) = struct.unpack_from("<qq", data, p)
        if off >= 0 and size > 0 and off + size <= len(data):
            candidates.append((p, p + 8))
    for (pa, pb) in candidates:
        (off, size) = struct.unpack_from("<qq", data, pa)
        if off >= 0 and size > 0 and off + size <= len(data):
            return (off, size)
    return None


def _pak_parse_index(idx):
    """解析 UE4 pak index 目录树 → 文件名列表"""
    if len(idx) < 12:
        return []
    (iv, n_entries) = struct.unpack_from("<ii", idx, 0)
    if n_entries <= 0 or n_entries > (1 << 24):
        return []
    pos = 8
    if pos + n_entries * 4 > len(idx):
        return []
    pos += n_entries * 4  # 跳过 hash 表
    files = []
    MAX_FILES = 60
    guard = 0
    while pos < len(idx) and len(files) < MAX_FILES and guard < 20000:
        guard += 1
        (dname, pos) = _pak_read_fstring(idx, pos)
        if dname is None or pos + 4 > len(idx):
            break
        (fc,) = struct.unpack_from("<i", idx, pos)
        pos += 4
        if fc < 0 or fc > 5000:
            break
        for _k in range(fc):
            if len(files) >= MAX_FILES:
                break
            (fname, pos) = _pak_read_fstring(idx, pos)
            if fname is None or pos + 16 > len(idx):
                return files
            (fo, fs) = struct.unpack_from("<qq", idx, pos)
            pos += 16
            if pos + 20 + 1 + 4 > len(idx):
                return files
            pos += 20  # sha1
            cm = idx[pos]
            pos += 1
            (fl,) = struct.unpack_from("<I", idx, pos)
            pos += 4
            name = (dname.rstrip("/") + "/" + fname) if dname else fname
            flags_txt = []
            if fl & 0x01:
                flags_txt.append("压缩")
            if fl & 0x02:
                flags_txt.append("加密")
            if fl & 0x04:
                flags_txt.append("带签名")
            if cm != 0:
                flags_txt.append("压缩方法%d" % cm)
            size_txt = ("%.1f MB" % (fs / 1048576.0)) if fs > 1048576 else ("%d B" % fs)
            files.append("%s  [%s  off=%d%s]" % (name, size_txt, fo,
                                                  ("  " + "/".join(flags_txt)) if flags_txt else ""))
    return files


def parse_ue_pak(data, key_hex=None):
    """Unreal Engine Pak 资源包：Zong 魔数 + footer/index → 文件清单。
    key_hex: 可选 AES-256 密钥（64 hex，可带 0x 前缀），用于解密加密 index。"""
    if len(data) < 12 or data[:4] != b"Zong":
        return None
    version = struct.unpack_from("<i", data, 4)[0]
    out = ["Unreal Engine Pak 资源包 (UE4/UE5)"]
    out.append("魔数: Zong  版本: %d" % version)
    out.append("文件大小: %d B (%.2f MB)" % (len(data), len(data) / 1048576.0))
    idx = _pak_find_index(data, version)
    if idx is None:
        out.append("Index 目录：未能定位（可能是 Io Store 容器 / 损坏）")
        return "\n".join(out)
    (off, size) = idx
    out.append("Index 目录偏移: %d  大小: %d B" % (off, size))
    if off + size > len(data):
        out.append("Index 越界，无法读取")
        return "\n".join(out)
    blob = data[off:off + size]
    files = _pak_parse_index(blob)
    if files:
        out.append("文件条目（最多 60 条）：")
        out.extend(files)
        return "\n".join(out)
    # 明文解析失败 → 尝试 AES 解密（index 加密时）
    if key_hex:
        key_txt = key_hex.strip()
        if key_txt.lower().startswith("0x"):
            key_txt = key_txt[2:]
        try:
            key = bytes.fromhex(key_txt)
        except Exception:
            out.append("密钥格式无效（需要 64 位 hex）")
            return "\n".join(out)
        if len(key) != 32:
            out.append("密钥长度错误（需要 32 字节 = 64 hex，实际 %d 字节）" % len(key))
            return "\n".join(out)
        if len(blob) % 16 != 0:
            out.append("Index 大小 %d 不是 16 的倍数，无法 AES 解密" % len(blob))
            return "\n".join(out)
        # 试两种：标准 ECB（UE index 用）→ FAES 计数器变体
        plain = None
        for label, dec in (("AES-256-ECB", aes256_ecb_decrypt),
                           ("AES-256-FAES(计数器)", aes256_faes_decrypt)):
            try:
                cand = dec(blob, key)
            except Exception:
                continue
            if len(cand) >= 12:
                try:
                    (iv2, ne2) = struct.unpack_from("<ii", cand, 0)
                except Exception:
                    continue
                if 0 < ne2 <= (1 << 24):
                    plain = cand
                    out.append("Index 已加密 → 用密钥解密成功（%s）" % label)
                    break
        if plain is None:
            out.append("Index 解密失败：密钥可能不匹配，或 index 非 16 字节对齐")
            return "\n".join(out)
        files = _pak_parse_index(plain)
        if files:
            out.append("文件条目（最多 60 条，已解密）：")
            out.extend(files)
        else:
            out.append("Index 解密成功但未解析出文件条目（可能是其他容器格式）")
    else:
        out.append("Index 内未解析出文件条目：可能已加密。"
                   "输入 AES 密钥（64 位 hex）后重试，或点击「自动获取鸣潮密钥」")
    return "\n".join(out)


def parse_img(data):
    """磁盘镜像（.img 软盘/分区）：FAT 引导扇区识别（OEM/卷标/几何参数）"""
    if len(data) < 64:
        return None
    oem = data[3:11].decode("latin1", "replace").strip("\x00 ")
    if not oem:
        return None
    fat_magic = oem in ("MSDOS5.0", "MSWIN4.1", "MSWIN4.0", "MSDOS   ", "mkfs.fat", "FAT16   ", "FAT12   ")
    if not fat_magic:
        return None
    bps = struct.unpack_from("<H", data, 11)[0]
    spc = data[13]
    rsvd = struct.unpack_from("<H", data, 14)[0]
    vol = data[0x2B:0x36].decode("latin1", "replace").strip("\x00 ") if len(data) > 0x36 else ""
    out = ["磁盘镜像（FAT 引导扇区）"]
    out.append("OEM: %s" % oem)
    if bps:
        out.append("扇区: %d B  每簇扇区: %d  保留扇区: %d" % (bps, spc, rsvd))
    if vol:
        out.append("卷标: " + vol)
    out.append("文件大小: %d B" % len(data))
    return "\n".join(out)


def parse_dat(data):
    """通用游戏/应用数据（.dat）：内容探测（魔数/可打印比例/可读字符串）"""
    if len(data) < 16:
        return None
    out = ["通用数据文件（dat）"]
    magic = " ".join("%02X" % b for b in data[:8])
    out.append("头: " + magic)
    if data[:2] == b"PK":
        out.append("容器: ZIP")
    elif data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        out.append("容器: OLE 复合文档")
    elif data[:4] == b"RIFF":
        out.append("容器: RIFF")
    elif data[:3] == b"ID3":
        out.append("容器: MP3 标签")
    txt = data[:4096]
    printable = sum(32 <= b < 127 or b in (9, 10, 13) for b in txt)
    if txt:
        ratio = printable / len(txt)
        if ratio > 0.6:
            try:
                s = txt.decode("utf-8", "replace")
                words = [w for w in s.split() if any(c.isalpha() for c in w)][:8]
                if words:
                    out.append("可读文本: " + " ".join(words)[:120])
            except Exception:
                pass
        out.append("前 4KB 可打印比例: %.0f%%" % (ratio * 100))
    out.append("文件大小: %d B" % len(data))
    return "\n".join(out)


def parse_nwc(data):
    """NoteWorthy Composer 乐谱（.nwc）：文本行解析"""
    if len(data) < 20:
        return None
    text = data.decode("latin1", "replace")
    head = text[:32].upper()
    if "NOTEWORTHY" not in head and "!NOTEWRITER" not in head:
        return None
    out = ["NoteWorthy Composer 乐谱"]
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    out.append("行数: %d" % len(lines))
    shown = 0
    for l in lines:
        if l.startswith("|") or l.startswith("!"):
            out.append("乐谱行: " + l[:80])
            shown += 1
            if shown >= 8:
                break
    out.append("文件大小: %d B" % len(data))
    return "\n".join(out)


def parse_rpm(data):
    """Red Hat Package（.rpm）：ed ab ee db 魔数 + 版本 + 类型/架构"""
    if len(data) < 16 or data[:4] != b"\xed\xab\xee\xdb":
        return None
    major, minor = data[4], data[5]
    rtype, arch = data[6], data[7]
    out = ["Red Hat Package（rpm）"]
    out.append("版本: %d.%d  类型: %d  架构: %d" % (major, minor, rtype, arch))
    out.append("文件大小: %d B" % len(data))
    return "\n".join(out)


def parse_probe(data, label):
    """通用内容探测：头 hex + 容器魔数 + 可打印比例 + 可读字符串"""
    if len(data) < 16:
        return None
    out = ["%s（内容探测）" % label]
    out.append("头: " + " ".join("%02X" % b for b in data[:8]))
    if data[:2] == b"PK":
        out.append("容器: ZIP")
    elif data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        out.append("容器: OLE 复合文档")
    elif data[:4] == b"RIFF":
        out.append("容器: RIFF")
    elif data[:2] in (b"MZ",):
        out.append("容器: DOS/PE 可执行")
    elif data[:4] == b"\x7fELF":
        out.append("容器: ELF 可执行")
    txt = data[:4096]
    printable = sum(32 <= b < 127 or b in (9, 10, 13) for b in txt)
    if txt:
        out.append("前 4KB 可打印比例: %.0f%%" % (printable * 100 / len(txt)))
    if printable > 0:
        texts = __import__("re").findall(rb"[\x20-\x7e]{6,}", txt)
        words = [w.decode("latin1") for w in texts][:8]
        if words:
            out.append("可读文本: " + " ".join(words)[:140])
    out.append("文件大小: %d B" % len(data))
    return "\n".join(out)


def parse_prt(data):
    """CAD 零件（.prt）：Pro/ENGINEER 文本版本头探测 / 内容探测兜底"""
    text = data[:512].decode("latin1", "replace")
    head = text.strip().splitlines()[0] if text.strip() else ""
    if "PRO/ENGINEER" in head.upper() or "PROE" in head.upper():
        return "CAD 零件（Pro/ENGINEER）\n版本串: %s\n文件大小: %d B" % (head[:80], len(data))
    return parse_probe(data, "CAD 零件（prt）")


def parse_misc(data, filename, key_hex=None):
    fn = (filename or "").lower()
    ext = fn.rsplit(".", 1)[-1] if "." in fn else ""
    if ext == "lnk":
        r = parse_lnk(data)
        if r:
            return r
    if ext == "torrent":
        r = parse_torrent(data)
        if r:
            return r
    if ext == "cue":
        r = parse_cue(data)
        if r:
            return r
    if ext == "wotreplay":
        r = parse_wotreplay(data)
        if r:
            return r
    if ext == "cdg":
        r = parse_cdg(data)
        if r:
            return r
    if ext == "eps":
        r = parse_eps(data)
        if r:
            return r
    if ext == "plist":
        r = parse_plist(data)
        if r:
            return r
    if ext == "idx":
        r = parse_idx(data)
        if r:
            return r
    if ext in ("ai", "emf", "wmf", "unity3d", "bsa"):
        r = {"ai": parse_ai, "emf": parse_emf, "wmf": parse_wmf,
             "unity3d": parse_unity3d, "bsa": parse_bsa}[ext](data)
        if r:
            return r
    if ext in ("art", "vdex", "oat"):
        r = {"art": parse_art, "vdex": parse_vdex, "oat": parse_oat}[ext](data)
        if r:
            return r
    if ext in ("gp", "gp3", "gp4", "gp5"):
        r = parse_gp5(data)
        if r:
            return r
    if ext == "z":
        r = parse_z(data)
        if r:
            return r
    if ext == "pak":
        r = parse_pak(data)
        if r:
            return r
        r = parse_ue_pak(data, key_hex)
        if r:
            return r
    if ext == "img":
        r = parse_img(data)
        if r:
            return r
    if ext == "dat":
        r = parse_dat(data)
        if r:
            return r
    if ext == "nwc":
        r = parse_nwc(data)
        if r:
            return r
    if ext == "rpm":
        r = parse_rpm(data)
        if r:
            return r
    if ext == "prt":
        r = parse_prt(data)
        if r:
            return r
    if ext in ("eep", "ldb", "lrf", "sav", "srm", "state"):
        labels = {"eep": "EEPROM 数据", "ldb": "LevelDB 数据", "lrf": "Sony Reader 电子书",
                  "sav": "游戏存档", "srm": "SRAM 存档", "state": "模拟器即时存档"}
        r = parse_probe(data, labels.get(ext, "数据"))
        if r:
            return r
    # CD+G is only tried when the extension actually says so. Its subcode layout
    # has no strong leading signature, so leaving it in the blind loop below let
    # it claim unrelated binaries (it matched a zero-filled buffer before).
    if ext == "cdg":
        r = parse_cdg(data)
        if r:
            return r
    # Blind fallback probing. Keep ONLY parsers with a real magic-number check here.
    # parse_img / parse_dat / parse_nwc / parse_rpm / parse_prt used to sit in this
    # loop as well: they match almost anything (parse_dat fires on any payload of
    # 16+ bytes), so every unmatched misc file got mislabelled as a generic ".dat"
    # data file -- the same class of bug that reported a UE pak as a CD+G karaoke
    # track. They still run above via their explicit extension branches, so a real
    # .dat file keeps working; they are just no longer used as a catch-all.
    for parser in (parse_lnk, parse_torrent, parse_cue, parse_wotreplay, parse_eps, parse_plist,
                   parse_ai, parse_emf, parse_wmf, parse_unity3d, parse_bsa,
                   parse_art, parse_vdex, parse_oat, parse_gp5, parse_z, parse_pak,
                   parse_ue_pak):
        try:
            r = parser(data)
        except Exception:
            continue
        if r is not None:
            return r
    # Nothing genuinely matched -> return None so the caller reports "unparsed".
    # The old code returned a human-readable "no parser for this format" string,
    # which the front end counted as a successful parse (silent false success).
    return None


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        with open(sys.argv[1], "rb") as f:
            print(parse_misc(f.read(), sys.argv[1]))
