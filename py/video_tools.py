# -*- coding: utf-8 -*-
"""video_tools.py — 视频容器头解析引擎（零依赖）
覆盖：AVI（RIFF）、MP4/MOV/M4V/F4V（atom 结构）、MPEG-PS、M2TS（188B TS 包）
"""

import struct


def _fourcc(b):
    return b.decode("latin1", "replace") if len(b) == 4 else "?"


def parse_avi(data):
    if data[:4] != b"RIFF" or data[8:12] != b"AVI ":
        return None
    out = ["AVI 视频（RIFF AVI）"]
    riff_size = struct.unpack_from("<I", data, 4)[0]
    out.append("RIFF 大小: %d B" % riff_size)
    # 首个 chunk 起点 12（RIFF+size+type 共 12B），chunk = size(4)+id(4)+data
    idx = 12
    while idx + 8 <= len(data) and idx < min(len(data), 1 << 20):
        csz = struct.unpack_from("<I", data, idx)[0]
        cid = data[idx + 4:idx + 8]
        if cid == b"LIST":
            if data[idx + 8:idx + 12] == b"hdrl":
                sub = idx + 12
                while sub + 8 <= len(data) and sub < idx + 8 + csz:
                    ssz = struct.unpack_from("<I", data, sub)[0]
                    sid = data[sub + 4:sub + 8]
                    if sid == b"avih" and ssz >= 40:
                        micro = struct.unpack_from("<I", data, sub + 8)[0]
                        fr = struct.unpack_from("<I", data, sub + 24)[0]
                        out.append("帧率: %.2f fps" % (1e6 / micro if micro else 0))
                        out.append("总帧数: %d" % fr)
                        break
                    sub += 8 + ssz + (ssz & 1)
                break
        idx += 8 + csz + (csz & 1)
    return "\n".join(out)


def parse_mp4(data):
    if len(data) < 12:
        return None
    def box(off, end):
        while off + 8 <= end:
            sz = struct.unpack_from(">I", data, off)[0]
            typ = data[off + 4:off + 8]
            hdr = 8
            if sz == 1:
                if off + 16 > end:
                    return
                sz = struct.unpack_from(">Q", data, off + 8)[0]
                hdr = 16
            elif sz == 0:
                sz = end - off
            yield off, sz, typ, hdr
            off += sz
    out = []
    ftyp = None
    top = []
    for off, sz, typ, hdr in box(0, len(data)):
        top.append(typ)
        if typ == b"ftyp" and sz >= 16:
            brand = data[off + 8:off + 12]
            ftyp = _fourcc(brand)
        if typ == b"moov" and off + hdr + 8 <= len(data):
            # 找 mvhd
            for o2, s2, t2, h2 in box(off + hdr, off + sz):
                if t2 == b"mvhd" and s2 >= 32:
                    ver = data[o2 + h2]
                    if ver == 1:
                        ts, dur = struct.unpack_from(">II", data, o2 + h2 + 20)
                    else:
                        ts, dur = struct.unpack_from(">II", data, o2 + h2 + 12)
                    out.append("时长: %.2f s（timescale %d）" % (dur / ts if ts else 0, ts))
                if t2 == b"trak":
                    pass
    if not top:
        return None
    res = ["MP4/MOV 视频（atom 容器）"]
    if ftyp:
        res.append("品牌: " + ftyp)
    res.append("顶层盒: " + ", ".join(_fourcc(t) for t in top[:8]))
    res.extend(out)
    return "\n".join(res)


def parse_mpeg(data):
    # MPEG-PS：0x000001BA 包起始码
    if data[:4] != b"\x00\x00\x01\xba":
        return None
    out = ["MPEG 节目流（PS）"]
    out.append("检测到包起始码 0x000001BA")
    # 统计起始码类型
    kinds = {}
    for i in range(0, min(len(data) - 4, 1 << 20), 4):
        if data[i:i + 3] == b"\x00\x00\x01":
            code = data[i + 3]
            if code in (0xBA, 0xBB, 0xB9, 0xE0, 0xE1, 0xE2, 0xC0, 0xC1, 0xC2, 0xB0, 0xB1, 0xB2, 0xB3, 0xB5, 0xB7):
                kinds[code] = kinds.get(code, 0) + 1
    names = {0xBA: "pack", 0xBB: "system", 0xB9: "end", 0xE0: "video0", 0xE1: "video1",
             0xC0: "audio0", 0xC1: "audio1", 0xB0: "map", 0xB5: "private1"}
    for code, n in sorted(kinds.items()):
        if n:
            out.append("%s: %d 个" % (names.get(code, "0x%02X" % code), n))
    return "\n".join(out)


def parse_m2ts(data):
    # TS：188B 包，sync 0x47
    if len(data) < 188 or data[0] != 0x47:
        return None
    out = ["M2TS/TS 传输流"]
    sync = sum(1 for i in range(0, min(len(data), 188 * 64), 188) if data[i] == 0x47)
    out.append("同步包: %d/%d（%.0f%%）" % (sync, min(len(data), 188 * 64) // 188,
            100.0 * sync / max(1, min(len(data), 188 * 64) // 188)))
    pids = {}
    for i in range(0, min(len(data), 188 * 64), 188):
        if data[i] != 0x47:
            continue
        pid = ((data[i + 1] & 0x1F) << 8) | data[i + 2]
        if pid:
            pids[pid] = pids.get(pid, 0) + 1
    top = sorted(pids.items(), key=lambda x: -x[1])[:4]
    for pid, n in top:
        out.append("PID 0x%04X: %d 包" % (pid, n))
    return "\n".join(out)


def parse_video(data, filename):
    fn = (filename or "").lower()
    ext = fn.rsplit(".", 1)[-1] if "." in fn else ""
    if ext in ("mp4", "mov", "m4v", "f4v", "m4a", "3gp", "3g2", "3gpp"):
        r = parse_mp4(data)
        if r:
            return r
    if ext == "avi":
        r = parse_avi(data)
        if r:
            return r
    if ext in ("mpeg", "mpg", "vob"):
        r = parse_mpeg(data)
        if r:
            return r
    if ext in ("m2ts", "ts", "mts"):
        r = parse_m2ts(data)
        if r:
            return r
    for parser in (parse_avi, parse_mp4, parse_mpeg, parse_m2ts):
        try:
            r = parser(data)
        except Exception:
            continue
        if r is not None:
            return r
    if ext:
        return "该视频格式（.%s）暂无解析器；大小 %d B。" % (ext, len(data))
    return "未知视频二进制：%d B" % len(data)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        with open(sys.argv[1], "rb") as f:
            print(parse_video(f.read(), sys.argv[1]))
