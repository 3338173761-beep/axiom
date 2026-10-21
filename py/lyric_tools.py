# -*- coding: utf-8 -*-
"""lyric_tools — 加密歌词解析（零依赖）：
  krc 酷狗 / qrc QQ音乐 / yrc 网易云逐字 / trc 天天动听
入口：parse_lyric(data, filename) -> str|None
"""
import re
import struct
import json
import zlib


def _fmt_ms(ms):
    ms = max(0, int(ms))
    m, s = divmod(ms // 1000, 60)
    return "%02d:%02d.%02d" % (m, s, (ms % 1000) // 10)


def _inflate_krc_block(raw):
    """krc/trc 主体：先 zlib inflate，再 XOR 0x40（真实格式：XOR 后再压缩）"""
    try:
        dec = zlib.decompress(raw)
        return bytes(b ^ 0x40 for b in dec).decode("utf-8", "replace")
    except Exception:
        return None


def parse_krc(data):
    """酷狗 krc：4 字节长度 + XOR + inflate → XML，逐字时间轴"""
    if len(data) < 8:
        return None
    size = struct.unpack("<I", data[:4])[0]
    xml = _inflate_krc_block(data[4:4 + size] if size else data[4:])
    if xml is None:
        xml = _inflate_krc_block(data[4:])
    if not xml:
        return None
    out = ["krc 歌词（酷狗）· 时间轴已还原"]
    for m in re.finditer(r'<t t="(\d+),(\d+)">(.*?)</t>', xml, re.S):
        start, dur, text = m.group(1), m.group(2), m.group(3)
        text = text.replace("<br/>", " / ").strip()
        if text:
            out.append("[%s]%s" % (_fmt_ms(start), text))
    if len(out) == 1:
        return None
    return "\n".join(out)


def parse_qrc(data):
    """QQ 音乐 qrc：4 字节长度 + zlib inflate（旧版无加密）→ 行歌词"""
    if len(data) < 8:
        return None
    size = struct.unpack("<I", data[:4])[0]
    try:
        xml = zlib.decompress(data[4:4 + size] if size else data[4:]).decode("utf-8", "replace")
    except Exception:
        try:
            xml = zlib.decompress(data[4:]).decode("utf-8", "replace")
        except Exception:
            return None
    out = ["qrc 歌词（QQ 音乐）"]
    for m in re.finditer(r'([\d:.]+),([^,<]*?)(?:\r?\n|$)', xml):
        ts, text = m.group(1).strip(), m.group(2).strip()
        if text:
            out.append("[%s]%s" % (ts, text))
    if len(out) == 1:
        return None
    return "\n".join(out)


def parse_yrc(data):
    """网易云 yrc：JSON 逐字歌词"""
    try:
        obj = json.loads(data.decode("utf-8", "replace"))
    except Exception:
        return None
    content = (obj.get("data") or {}).get("content") or []
    out = ["yrc 歌词（网易云·逐字）"]
    for it in content:
        if not isinstance(it, dict):
            continue
        t = it.get("time")
        lyr = (it.get("lyric") or "").strip()
        if t is not None and lyr:
            out.append("[%s]%s" % (_fmt_ms(t), lyr))
    if len(out) == 1:
        return None
    return "\n".join(out)


def parse_trc(data):
    """天天动听 trc：同 krc 结构（长度 + XOR + inflate）"""
    r = parse_krc(data)
    if r:
        return r.replace("krc 歌词（酷狗）", "trc 歌词（天天动听）")
    return None


def parse_lyric(data, filename):
    fn = (filename or "").lower()
    for parser, exts in ((parse_krc, (".krc",)), (parse_qrc, (".qrc",)),
                         (parse_yrc, (".yrc",)), (parse_trc, (".trc",))):
        if fn.endswith(exts):
            r = parser(data)
            if r:
                return r
    # 兜底：逐格式尝试
    for parser in (parse_krc, parse_qrc, parse_yrc, parse_trc):
        r = parser(data)
        if r:
            return r
    return None


if __name__ == "__main__":
    import sys
    data = open(sys.argv[1], "rb").read()
    print(parse_lyric(data, sys.argv[1]))
