# -*- coding: utf-8 -*-
"""Axiom 歌声合成/音频工程引擎：ust/ufdata/vsqx/vpr/svp/dv/ccs/mid
原理：UTAU(ust) 为 INI、Vocaloid/SynthesizerV/DeepVocal/CeVIO 为 XML、
MIDI 为 SMF 二进制（自研解析）。
输出：可翻译歌词/文本块（保留换行结构）
"""
import io, os, sys, re


def _try_decode(data, encs=("utf-8", "utf-8-sig", "gb18030", "shift_jis", "latin-1")):
    for enc in encs:
        try:
            return data.decode(enc)
        except Exception:
            continue
    return data.decode("utf-8", errors="replace")


# ---------- UTAU ----------
def extract_ust(data):
    """ust 是 INI：[#N] 音符块里 Lyric=歌词行"""
    text = _try_decode(data)
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.lower().startswith("lyric="):
            out.append(s[6:].strip())
    # 兜底：也抓 Note 块内其他文本属性（如 Program/Outer 的注释行）
    return "\n".join(out) if out else "未找到歌词行（Lyric=），可能是纯参数工程"


def extract_ufdata(data):
    return extract_ust(data)  # UTAU 音符数据同 INI 结构


# ---------- Vocaloid ----------
def extract_vsqx(data):
    """Vocaloid 4/5 .vsqx：XML，<p name="lyric">歌词</p>"""
    xml = _try_decode(data)
    lyrics = []
    for m in re.finditer(r'<p[^>]*name="lyric"[^>]*>(.*?)</p>', xml, re.S):
        t = m.group(1).strip()
        if t:
            lyrics.append(t)
    if not lyrics:
        # 兼容 <phonetic> / 注释类
        for m in re.finditer(r"<p[^>]*>(.*?)</p>", xml, re.S):
            t = m.group(1).strip()
            if t and len(t) < 40 and not t.startswith("<"):
                lyrics.append(t)
    return "\n".join(lyrics) if lyrics else "未找到歌词（vsqx 无 <p name=lyric>）"


def extract_vsq(data):
    """Vocaloid 2 .vsq：二进制——解析 VSQ 块提取演唱音符文本"""
    if data[:2] != b"VST" and data[:2] != b"VSQ":
        return "非标准 VSQ 文件（应为 VST/VSQ 二进制头）"
    out = []
    i = 0
    n = len(data)
    # VSQ 文件：Nch blocks——尽力提取 ASCII 文本片段
    while i < n - 1:
        # 寻找可打印 ASCII 片段（歌词通常为半角/ASCII）
        j = i
        buf = []
        while j < n and 0x20 <= data[j] < 0x7F:
            buf.append(chr(data[j]))
            j += 1
        if len(buf) >= 1:
            s = "".join(buf).strip()
            if s and s.isascii() and not s.isdigit():
                out.append(s)
            i = j
        else:
            i += 1
    return "\n".join(out[:200]) if out else "未提取到文本（vsq 二进制无文本块）"


def extract_vpr(data):
    """Vocaloid 5 .vpr：XML（含 <p name="lyric">）"""
    return extract_vsqx(data)


# ---------- Synthesizer V ----------
def extract_svp(data):
    """Synthesizer V .svp：XML，<lyric>..</lyric> 或 <p name="lyric">"""
    xml = _try_decode(data)
    lyrics = []
    for m in re.finditer(r"<lyric[^>]*>(.*?)</lyric>|<p[^>]*name=\"lyric\"[^>]*>(.*?)</p>", xml, re.S):
        t = (m.group(1) or m.group(2) or "").strip()
        if t:
            lyrics.append(t)
    # s5p 是 zip 容器：解包后找 .s5p/.project
    if not lyrics and data[:2] == b"PK":
        import zipfile
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
            for nm in zf.namelist():
                if nm.endswith((".s5p", ".project", ".svp", ".xml")):
                    sub = zf.read(nm)
                    xml = _try_decode(sub)
                    for m in re.finditer(r"<lyric[^>]*>(.*?)</lyric>|<p[^>]*name=\"lyric\"[^>]*>(.*?)</p>", xml, re.S):
                        t = (m.group(1) or m.group(2) or "").strip()
                        if t:
                            lyrics.append(t)
                    if lyrics:
                        break
        except Exception:
            pass
    return "\n".join(lyrics) if lyrics else "未找到歌词（Synthesizer V 工程无 lyric 节点）"


# ---------- DeepVocal / CeVIO ----------
def extract_dv(data):
    """DeepVocal .dv：XML <p name="lyric">"""
    return extract_vsqx(data)


def extract_ccs(data):
    """CeVIO .ccs：XML <p name="lyric"> 或 <lyric>"""
    xml = _try_decode(data)
    lyrics = []
    for m in re.finditer(r"<lyric[^>]*>(.*?)</lyric>|<p[^>]*name=\"lyric\"[^>]*>(.*?)</p>", xml, re.S):
        t = (m.group(1) or m.group(2) or "").strip()
        if t:
            lyrics.append(t)
    return "\n".join(lyrics) if lyrics else "未找到歌词（CeVIO 工程无 lyric 节点）"


# ---------- MIDI ----------
def extract_midi(data):
    """SMF（Standard MIDI File）自研解析：MThd + MTrk + 事件。
    提取 Text(0x01)/Lyric(0x05)/TrackName(0x03) 事件 + 统计音符数。"""
    if len(data) < 14 or data[:4] != b"MThd":
        return "非标准 MIDI 文件（缺 MThd 头）"
    fmt = int.from_bytes(data[8:10], "big")
    ntracks = int.from_bytes(data[10:12], "big")
    hdr_len = int.from_bytes(data[4:8], "big")
    pos = 8 + hdr_len
    texts = []
    notes = 0
    while pos + 8 <= len(data) and data[pos:pos + 4] == b"MTrk":
        tlen = int.from_bytes(data[pos + 4:pos + 8], "big")
        chunk = data[pos + 8:pos + 8 + tlen]
        pos += 8 + tlen
        i = 0
        last_status = 0
        while i < len(chunk):
            # Delta VLQ
            while i < len(chunk) and chunk[i] & 0x80:
                i += 1
            i += 1
            if i >= len(chunk):
                break
            ev = chunk[i]
            if ev == 0xFF:  # 元事件
                i += 1
                if i >= len(chunk):
                    break
                typ = chunk[i]
                i += 1
                ln = 0
                while True:
                    if i >= len(chunk):
                        break
                    b = chunk[i]
                    i += 1
                    ln = ln * 128 + (b & 0x7F)
                    if not (b & 0x80):
                        break
                dat = chunk[i:i + ln]
                i += ln
                if typ in (0x01, 0x05, 0x03):
                    t = _try_decode(dat)
                    if t.strip():
                        texts.append(t.strip())
            elif ev == 0xF0 or ev == 0xF7:  # SysEx
                i += 1
                ln = 0
                while True:
                    if i >= len(chunk):
                        break
                    b = chunk[i]
                    i += 1
                    ln = ln * 128 + (b & 0x7F)
                    if not (b & 0x80):
                        break
                i += ln
            elif ev & 0x80:  # 通道消息
                hi = ev & 0xF0
                if hi in (0xC0, 0xD0):
                    i += 1
                else:
                    i += 2
                if hi == 0x90:
                    notes += 1
                last_status = ev
            else:
                # 运行状态（无状态字节）
                hi = last_status & 0xF0 if last_status else 0x90
                if hi == 0x90:
                    notes += 1
                if hi in (0xC0, 0xD0):
                    i += 1
                else:
                    i += 1  # 只有数据字节
        if i > len(chunk):
            break
    head = "MIDI：format=%d，音轨=%d，音符事件≈%d" % (fmt, ntracks, notes)
    return (head + "\n" + "\n".join(texts)) if texts else head + "\n未找到文本/歌词事件"


# ---------- 入口 ----------
def extract_voice(data, name):
    lower = name.lower()
    if lower.endswith((".ust", ".uproject")):
        return extract_ust(data)
    if lower.endswith(".ufdata"):
        return extract_ufdata(data)
    if lower.endswith(".vsqx"):
        return extract_vsqx(data)
    if lower.endswith(".vsq"):
        return extract_vsq(data)
    if lower.endswith(".vpr"):
        return extract_vpr(data)
    if lower.endswith((".svp", ".s5p")):
        return extract_svp(data)
    if lower.endswith((".dv", ".dva", ".dvpp")):
        return extract_dv(data)
    if lower.endswith((".ccs", ".ccsi")):
        return extract_ccs(data)
    if lower.endswith((".mid", ".midi", ".smf")):
        return extract_midi(data)
    return "暂不支持该歌声工程格式（%s）" % lower


if __name__ == "__main__":
    data = open(sys.argv[1], "rb").read()
    print(extract_voice(data, sys.argv[1]))
