# -*- coding: utf-8 -*-
"""audio_meta.py — 音频元数据引擎（零依赖，纯标准库）
覆盖：追踪器模块（IT/MOD/S3M/XM）、芯片音乐（VGM/VGZ/PSF）、
卡拉OK MIDI（KAR）、RIFF MIDI（RMI）、XMIDI（XMI）
仅做结构化头/目录解析，不播放、不解码音频。
"""

import struct
import gzip


def parse_module(data, filename):
    """追踪器模块头：IT / MOD / S3M / XM"""
    fn = (filename or "").lower()
    out = []
    # Impulse Tracker
    if data[:4] == b"IMPM":
        ver = struct.unpack("<H", data[4:6])[0]
        name = data[8:34].split(b"\x00")[0].decode("cp437", "replace")
        n_ord = struct.unpack("<H", data[34:36])[0]
        n_ins = struct.unpack("<H", data[36:38])[0]
        n_smp = struct.unpack("<H", data[38:40])[0]
        n_pat = struct.unpack("<H", data[40:42])[0]
        out.append("Impulse Tracker 模块 · v%d.%02x" % (ver >> 8, ver & 0xFF))
        out.append("曲名: %s" % (name or "(未命名)"))
        out.append("序: %d · 乐器: %d · 采样: %d · 模式: %d" % (n_ord, n_ins, n_smp, n_pat))
        return "\n".join(out)
    # ProTracker MOD
    if data[:4] in (b"M.K.", b"M!K!", b"FLT4", b"FLT8", b"6CHN", b"8CHN", b"OCTA"):
        name = data[0:20].split(b"\x00")[0].decode("cp437", "replace")
        out.append("ProTracker 模块（MOD）")
        out.append("曲名: %s" % (name or "(未命名)"))
        out.append("通道: 4-8（标识 %s）" % data[1080:1084].decode("latin1", "replace"))
        return "\n".join(out)
    # ScreamTracker 3
    if data[:4] == b"SCRM":
        name = data[4:32].split(b"\x00")[0].decode("cp437", "replace")
        n_ord = struct.unpack("<H", data[32:34])[0]
        n_ins = struct.unpack("<H", data[34:36])[0]
        n_pat = struct.unpack("<H", data[36:38])[0]
        flags = data[38]
        out.append("ScreamTracker 3 模块")
        out.append("曲名: %s" % (name or "(未命名)"))
        out.append("序: %d · 乐器: %d · 模式: %d · 立体声: %s" % (n_ord, n_ins, n_pat, "是" if flags & 1 else "否"))
        return "\n".join(out)
    # FastTracker XM
    if data[:17] == b"Extended Module: ":
        name = data[17:37].split(b"\x00")[0].decode("cp437", "replace")
        ver = struct.unpack("<H", data[59:61])[0]
        header_sz = struct.unpack("<I", data[61:65])[0]
        n_ord = struct.unpack("<H", data[65:67])[0]
        n_pat = struct.unpack("<H", data[71:73])[0]
        n_ins = struct.unpack("<H", data[73:75])[0]
        out.append("FastTracker 2 模块（XM）· v%d.%02x" % (ver >> 8, ver & 0xFF))
        out.append("曲名: %s" % (name or "(未命名)"))
        out.append("序: %d · 乐器: %d · 模式: %d · 头 %d B" % (n_ord, n_ins, n_pat, header_sz))
        return "\n".join(out)
    return None


def _vgm_info(data):
    out = ["Video Game Music（VGM）"]
    ver = struct.unpack("<I", data[8:12])[0]
    out.append("版本: %d.%d" % ((ver >> 8) & 0xFF, ver & 0xFF))
    sn = struct.unpack("<I", data[12:16])[0]
    ym = struct.unpack("<I", data[16:20])[0]
    if sn:
        out.append("SN76489 时钟: %d Hz" % sn)
    if ym:
        out.append("YM2612 时钟: %d Hz" % ym)
    out.append("总长度: %d 采样" % struct.unpack("<I", data[24:28])[0])
    # GD3 标签（偏移 0x14 起的 GD3 偏移在 header 84-88）
    if len(data) >= 88:
        gd3 = struct.unpack("<I", data[84:88])[0]
        if gd3 and gd3 + 16 < len(data) and data[gd3:gd3 + 4] == b"Gd3 ":
            name = data[gd3 + 12:gd3 + 14]
            n = struct.unpack("<I", name)[0]
            enc = data[gd3 + 10] if len(data) > gd3 + 10 else 0
            if 0 < n < 4096 and gd3 + 14 + n <= len(data):
                tag = data[gd3 + 14:gd3 + 14 + n]
                try:
                    out.append("曲名: " + (tag.decode("utf-16-le" if enc == 1 else "utf-8", "replace") if enc in (0, 1) else tag.decode("latin1", "replace")))
                except Exception:
                    pass
    return "\n".join(out)


def parse_chip(data, filename):
    """芯片/游戏音乐：VGM / VGZ / PSF"""
    fn = (filename or "").lower()
    if data[:4] == b"Vgm ":
        return _vgm_info(data)
    if fn.endswith(".vgz"):
        try:
            raw = gzip.decompress(data)
            if raw[:4] == b"Vgm ":
                return "Compressed VGM（gzip）\n" + _vgm_info(raw)
        except Exception:
            pass
        return "Compressed VGM（gzip，解压失败或非 VGM）"
    if data[:3] == b"PSF":
        ver = struct.unpack("<B", data[3:4])[0]
        res = struct.unpack("<I", data[4:8])[0]
        out = ["Portable Sound Format（PSF）· v%d" % ver]
        out.append("保留区: 0x%08X（%d 字节库文件）" % (res, res))
        # 后面通常跟 exe 区
        return "\n".join(out)
    return None


def _smf_parse(data):
    """标准 MIDI 文件（SMF）头：MThd + 长度 + format/tracks/division"""
    if data[:4] != b"MThd" or len(data) < 14:
        return None
    (hlen,) = struct.unpack(">I", data[4:8])
    if hlen < 6 or 8 + hlen > len(data):
        return None
    fmt, tracks, div = struct.unpack(">HHH", data[8:14])
    out = ["标准 MIDI 文件（SMF）"]
    out.append("格式: %d · 音轨: %d · 时基: %d" % (fmt, tracks, div))
    if div & 0x8000:
        fps = {0: 24, 1: 25, 2: 30, 3: 30}[div >> 8]
        out.append("SMPTE 时间码: %d fps" % fps)
    # 扫描第一个文本/歌词事件
    txts = []
    pos = 8 + hlen
    for _ in range(tracks):
        if pos + 8 > len(data):
            break
        if data[pos:pos + 4] != b"MTrk":
            break
        (tlen,) = struct.unpack(">I", data[pos + 4:pos + 8])
        body = data[pos + 8:pos + 8 + tlen]
        # 扫 FF 05(歌词) / FF 01(文本)
        i = 0
        try:
            while i < len(body):
                # 跳过 VLQ
                while i < len(body) and body[i] & 0x80:
                    i += 1
                i += 1
                if i >= len(body):
                    break
                st = body[i]
                if st == 0xFF and i + 2 < len(body):
                    typ = body[i + 1]
                    if i + 5 > len(body):
                        break
                    (tlen2,) = struct.unpack(">I", b"\x00" + body[i + 2:i + 5])
                    i += 3
                    if i + tlen2 <= len(body):
                        s = body[i:i + tlen2].decode("utf-8", "replace")
                        if typ == 0x05 and s.strip():
                            txts.append(s.strip())
                        elif typ == 0x01 and s.strip() and len(txts) < 6:
                            txts.append(s.strip())
                        i += tlen2
                        continue
                    else:
                        break
                elif 0x80 <= st <= 0xEF:
                    i += 2 if st < 0xC0 or st > 0xDF else 1
                    continue
                else:
                    i += 1
        except Exception:
            pass
        pos += 8 + tlen
    if txts:
        out.append("文本/歌词: " + " | ".join(txts[:6]))
    return "\n".join(out)


def parse_midi(data, filename):
    """MIDI 家族：KAR（歌词）/ RMI（RIFF 封装）/ XMI（XMIDI）"""
    fn = (filename or "").lower()
    if data[:4] == b"MThd":
        r = _smf_parse(data)
        if r is not None and fn.endswith((".kar",)):
            return "Karaoke MIDI（卡拉OK 歌词）\n" + r
        return r
    if data[:4] == b"RIFF" and data[8:12] == b"RMID":
        # 找 MThd
        pos = 12
        while pos + 4 < len(data):
            if data[pos:pos + 4] == b"MThd":
                r = _smf_parse(data[pos:])
                if r is not None:
                    return "RIFF MIDI（RMID 封装）\n" + r
                break
            (sz,) = struct.unpack("<I", data[pos + 4:pos + 8])
            pos += 8 + sz + (sz & 1)
        return "RIFF MIDI（RMID）· 未找到 SMF 流"
    if data[:4] == b"RIFF" and data[8:12] == b"XMID":
        out = ["XMIDI（Extended MIDI，RIFF 封装）"]
        pos = 12
        evnt = 0
        while pos + 4 < len(data):
            cid = data[pos:pos + 4]
            (sz,) = struct.unpack("<I", data[pos + 4:pos + 8])
            if cid == b"EVNT":
                evnt += 1
            pos += 8 + sz + (sz & 1)
        out.append("EVNT 轨: %d" % evnt)
        return "\n".join(out)
    return None


def parse_mp3(data):
    if len(data) < 4:
        return None
    out = None
    b = 0
    if data[:3] == b"ID3":
        sz = (data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9]
        out = ["MP3（ID3v2 标签 + MPEG 音频）"]
        out.append("ID3v2.%d，标签 %d B" % (data[3], sz + 10))
        b = 10 + sz
    for i in range(b, min(len(data) - 4, 4096)):
        if data[i] == 0xFF and (data[i + 1] & 0xE0) == 0xE0:
            b = i
            break
    else:
        if out is None:
            return None
        b = len(data)
    if b < len(data) and data[b] == 0xFF and (data[b + 1] & 0xE0) == 0xE0:
        if out is None:
            out = ["MP3（MPEG 帧）"]
        h = data[b + 1]
        ver = {0: "MPEG 2.5", 2: "MPEG 2", 3: "MPEG 1"}.get((h >> 3) & 3, "?")
        layer = 4 - ((h >> 1) & 3)
        bitrate_idx = (data[b + 2] >> 4) & 0xF
        sr_idx = (data[b + 2] >> 2) & 3
        out.append("编码: %s Layer %d" % (ver, layer))
        br = {3: {1: 32, 2: 64, 3: 96, 4: 128, 5: 160, 6: 192, 7: 224, 8: 256, 9: 288, 10: 320},
              2: {1: 32, 2: 48, 3: 56, 4: 64, 5: 80, 6: 96, 7: 112, 8: 128, 9: 160, 10: 192}}.get(layer, {}).get(bitrate_idx)
        if br:
            out.append("码率: %d kbps" % br)
        sr = {0: 44100, 1: 48000, 2: 32000}.get(sr_idx)
        if sr and ver != "MPEG 2.5":
            out.append("采样率: %d Hz" % (sr // (2 if ver == "MPEG 2" else 1)))
    return "\n".join(out) if out else None


def parse_ogg(data):
    if data[:4] != b"OggS" or len(data) < 27:
        return None
    serial = struct.unpack_from("<I", data, 14)[0]
    page_seq = struct.unpack_from("<I", data, 18)[0]
    segs = data[26]
    out = ["Ogg 容器"]
    out.append("序列号: %08X  页序号: %d" % (serial, page_seq))
    out.append("段表: %d 段" % segs)
    payload = data[27 + segs:]
    if payload.startswith(b"FLAC") or payload.startswith(b"\x7fFLAC"):
        out.append("编码: FLAC")
    elif payload.startswith(b"OpusHead"):
        out.append("编码: Opus")
    elif payload.startswith(b"\x01vorbis"):
        out.append("编码: Vorbis")
    elif payload.startswith(b"Theora"):
        out.append("编码: Theora")
    else:
        out.append("编码: 未识别")
    return "\n".join(out)


def parse_flac(data):
    if data[:4] != b"fLaC" or len(data) < 42:
        return None
    if data[4] != 0:
        return None
    size = (data[5] << 16) | (data[6] << 8) | data[7]
    if size < 34 or 8 + size > len(data):
        return None
    s = data[8:8 + 34]
    val = int.from_bytes(s[:4], byteorder="big")
    sr = (val >> 8) & 0xFFFFF
    ch = ((val >> 5) & 0x7) + 1
    bps = (val & 0x1F) + 1
    out = ["FLAC 音频"]
    out.append("采样率: %d Hz" % sr)
    out.append("声道: %d" % ch)
    out.append("位深: %d bps" % bps)
    return "\n".join(out)


def parse_asf(data):
    # ASF/WMA：对象 GUID 头 + 文件大小
    asf_guid = b"\x30\x26\xb2\x75\x8e\x66\xcf\x11\xa6\xd9\x00\xaa\x00\x62\xce\x6c"
    if data[:16] != asf_guid or len(data) < 30:
        return None
    size = struct.unpack_from("<Q", data, 16)[0]
    num = struct.unpack_from("<I", data, 24)[0]
    out = ["ASF 容器（WMA/WMV）"]
    out.append("文件大小字段: %d B" % size)
    out.append("对象数: %d" % num)
    return "\n".join(out)


def parse_aac(data):
    if len(data) < 7 or data[0] != 0xFF or (data[1] & 0xF6) != 0xF0:
        return None
    profile = (data[2] >> 6) & 3
    sr_idx = (data[2] >> 2) & 0xF
    ch = ((data[2] & 1) << 2) | ((data[3] >> 6) & 3)
    fr = ((data[3] & 3) << 11) | (data[4] << 3) | ((data[5] >> 5) & 7)
    out = ["AAC（ADTS 帧）"]
    out.append("Profile: %s" % {0: "Main", 1: "LC", 2: "SSR", 3: "LTP"}.get(profile, "?"))
    sr = {0: 96000, 1: 88200, 2: 64000, 3: 48000, 4: 44100, 5: 32000, 6: 24000,
          7: 22050, 8: 16000, 9: 12000, 10: 11025, 11: 8000, 12: 7350}.get(sr_idx)
    out.append("采样率: %s Hz" % (sr if sr else "?"))
    out.append("声道: %d" % ch)
    out.append("帧长: %d B" % fr)
    return "\n".join(out)


def parse_aiff(data):
    if data[:4] != b"FORM" or data[8:12] != b"AIFF":
        return None
    out = ["AIFF 音频"]
    i = 12
    while i + 8 <= len(data) and i < min(len(data), 1 << 20):
        cid = data[i:i + 4]
        csz = struct.unpack_from(">I", data, i + 4)[0]
        if cid == b"COMM" and csz >= 18:
            ch, frames = struct.unpack_from(">HI", data, i + 8)
            bits = struct.unpack_from(">H", data, i + 14)[0]
            sr = struct.unpack_from(">I", data, i + 16)[0]
            out.append("声道: %d  采样率: %d Hz" % (ch, sr))
            out.append("位深: %d bps  采样帧: %d" % (bits, frames))
            out.append("时长约: %.1f s" % (frames / sr if sr else 0))
            break
        i += 8 + csz + (csz & 1)
    return "\n".join(out)


def parse_wavpack(data):
    if data[:4] != b"wvpk":
        return None
    csize = struct.unpack_from("<I", data, 4)[0]
    ver = struct.unpack_from("<H", data, 8)[0]
    total = struct.unpack_from("<I", data, 12)[0]
    flags = struct.unpack_from("<I", data, 24)[0] if len(data) >= 28 else 0
    out = ["WavPack 音频"]
    out.append("版本: %d.%02d" % (ver >> 8, ver & 0xFF))
    out.append("块大小: %d B  采样帧: %d" % (csize, total))
    out.append("flags: 0x%08X（含采样率/声道编码）" % flags)
    return "\n".join(out)


def parse_ape(data):
    if data[:4] != b"MAC ":
        return None
    ver = struct.unpack_from("<H", data, 4)[0]
    ch = struct.unpack_from("<H", data, 12)[0]
    sr = struct.unpack_from("<I", data, 14)[0]
    bits = struct.unpack_from("<H", data, 22)[0] if len(data) >= 24 else 0
    out = ["Monkey's Audio（APE）"]
    out.append("版本: %d.%02d" % (ver >> 8, ver & 0xFF))
    out.append("声道: %d  采样率: %d Hz" % (ch, sr))
    out.append("位深: %d bps" % bits)
    return "\n".join(out)


def parse_audio(data, filename):
    fn = (filename or "").lower()
    ext = fn.rsplit(".", 1)[-1] if "." in fn else ""
    if ext in ("it", "mod", "s3m", "xm"):
        r = parse_module(data, filename)
        if r:
            return r
    if ext in ("vgm", "vgz", "psf"):
        r = parse_chip(data, filename)
        if r:
            return r
    if ext in ("kar", "rmi", "xmi", "mid", "midi"):
        r = parse_midi(data, filename)
        if r:
            return r
    if ext == "mp3":
        r = parse_mp3(data)
        if r:
            return r
    if ext == "ogg":
        r = parse_ogg(data)
        if r:
            return r
    if ext == "flac":
        r = parse_flac(data)
        if r:
            return r
    if ext in ("wma", "asf"):
        r = parse_asf(data)
        if r:
            return r
    if ext == "aac":
        r = parse_aac(data)
        if r:
            return r
    if ext in ("aiff", "aif"):
        r = parse_aiff(data)
        if r:
            return r
    if ext in ("wv", "wavpack"):
        r = parse_wavpack(data)
        if r:
            return r
    if ext == "ape":
        r = parse_ape(data)
        if r:
            return r
    # 魔数兜底
    for parser in (parse_module, parse_chip, parse_midi, parse_mp3, parse_ogg,
                   parse_flac, parse_asf, parse_aac, parse_aiff, parse_wavpack, parse_ape):
        try:
            r = parser(data, filename)
        except Exception:
            continue
        if r is not None:
            return r
    if ext:
        return "该音频/音乐格式（.%s）暂无结构化解析器；大小 %d 字节。" % (ext, len(data))
    return "未知音乐二进制：大小 %d 字节，头 %s" % (len(data), " ".join("%02X" % b for b in data[:16]))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        with open(sys.argv[1], "rb") as f:
            print(parse_audio(f.read(), sys.argv[1]))
