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
    # CD+G 包：开头常为 0x00 控制字节 + 指令
    if data[0] not in (0x00, 0x01) and not data.startswith(b"CD"):
        return None
    out = ["CD+Graphics（CD+G 卡拉OK 图形轨）"]
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


def parse_misc(data, filename):
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
    for parser in (parse_lnk, parse_torrent, parse_cue, parse_wotreplay, parse_cdg, parse_eps, parse_plist):
        try:
            r = parser(data)
        except Exception:
            continue
        if r is not None:
            return r
    if ext:
        return "该格式（.%s）暂无解析器；大小 %d 字节。" % (ext, len(data))
    return "未知二进制：%d 字节，头 %s" % (len(data), " ".join("%02X" % b for b in data[:16]))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        with open(sys.argv[1], "rb") as f:
            print(parse_misc(f.read(), sys.argv[1]))
