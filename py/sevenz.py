# -*- coding: utf-8 -*-
"""Axiom 自研 7z 解压器 v4（浏览器 Pyodide / 本地均可跑）
严格对照 py7zr 1.1.4 源码翻译：
  UInt64 = 首字节高 3 位 1 个数 = 额外字节数；值 = (首字节低位 << 8*n) + 后续字节拼接；0xFF = 8 字节定长
  Coder: methodsize = flags & 0x0F（0 = Copy）；num_bindpairs = totalout - 1（计算）；num_packedstreams = totalin - num_bindpairs（==1 不读）
  bitvector = MSB-first
支持：Copy / LZMA / LZMA2 / Deflate / BZip2 / ZSTD；链式 coder（BCJ x86 后处理）
"""
import io, sys, zlib, bz2, struct

try:
    import lzma as _lzma
except Exception:
    _lzma = None
try:
    import zstandard as _zstd
except Exception:
    _zstd = None

MAGIC = b"\x37\x7a\xbc\xaf\x27\x1c"

K_END = 0x00; K_HEADER = 0x01; K_ARCHIVE_PROPS = 0x02; K_ADDITIONAL = 0x03
K_MAIN_STREAMS = 0x04; K_FILES_INFO = 0x05; K_PACK_INFO = 0x06; K_UNPACK_INFO = 0x07
K_SUB_STREAMS = 0x08; K_SIZE = 0x09; K_CRC = 0x0A; K_FOLDER = 0x0B; K_CODERS_UNPACK = 0x0C
K_NUM_UNPACK = 0x0D; K_EMPTY_STREAM = 0x0E; K_EMPTY_FILE = 0x0F; K_ANTI = 0x10
K_NAME = 0x11; K_CTIME = 0x12; K_ATIME = 0x13; K_MTIME = 0x14; K_ATTRS = 0x15
K_COMMENT = 0x16; K_ENCODED_HEADER = 0x17; K_START_POS = 0x18; K_DUMMY = 0x19

M_COPY = b"\x00"; M_LZMA = b"\x03\x01\x01"; M_LZMA2 = b"\x21"
M_DEFLATE = b"\x04\x01\x08"; M_BZIP2 = b"\x04\x02\x02"; M_ZSTD = b"\x04\xf7\x11\x01"
M_BCJ = b"\x04"; M_P7Z_BCJ = b"\x03\x03\x01\x03"; M_P7Z_BCJ2 = b"\x03\x03\x01\x1b"
M_PPMD = b"\x03\x04\x01"; M_DELTA = b"\x03"; M_ZIP = b"\x04\x01"


class Reader:
    def __init__(self, data, pos=0):
        self.data = data; self.pos = pos
    def read(self, n):
        if self.pos + n > len(self.data):
            raise ValueError("越界 pos=%d n=%d len=%d" % (self.pos, n, len(self.data)))
        b = self.data[self.pos:self.pos + n]; self.pos += n; return b
    def byte(self):
        return self.read(1)[0]
    def uint64(self):
        b = self.byte()
        if b == 0xFF:
            return int.from_bytes(self.read(8), "little")
        if not (b & 0x80):
            return b
        if not (b & 0x40):
            return ((b & 0x3F) << 8) | self.byte()
        if not (b & 0x20):
            v = (b & 0x1F) << 16
            v |= self.byte() << 8
            v |= self.byte()
            return v
        if not (b & 0x10):
            v = (b & 0x0F) << 24
            for _ in range(3):
                v = (v << 8) | self.byte()
            return v
        if not (b & 0x08):
            v = (b & 0x07) << 32
            for _ in range(4):
                v = (v << 8) | self.byte()
            return v
        if not (b & 0x04):
            v = (b & 0x03) << 40
            for _ in range(5):
                v = (v << 8) | self.byte()
            return v
        if not (b & 0x02):
            v = (b & 0x01) << 48
            for _ in range(6):
                v = (v << 8) | self.byte()
            return v
        v = 0
        for _ in range(7):
            v = (v << 8) | self.byte()
        return v


MAX_ENTRIES = 100000


def _checked_count(n, r, what):
    """Counts declared inside the file are attacker controlled. A single uint64
    could ask for a 2**63-element list and take the whole browser tab down (the
    Pyodide heap) before any later bounds check ever runs. Cap against both a
    fixed ceiling and the real buffer size: every declared entry costs at least
    one header byte, so a count above the file size is by definition bogus."""
    if n is None or n < 0 or n > MAX_ENTRIES or n > len(r.data):
        raise ValueError("%s 数量异常：%s（缓冲仅 %d 字节）" % (what, n, len(r.data)))
    return n


def read_boolean(r, count):
    count = _checked_count(count, r, "Boolean")
    allv = r.byte()
    if allv == 1:
        return [True] * count
    if allv == 0:
        return [False] * count
    raw = [allv] + list(r.read((count + 7) // 8 - 1))
    return [bool(raw[i // 8] & (1 << (7 - i % 8))) for i in range(count)]


def _method_name(mid):
    t = {
        M_COPY: "Copy", M_LZMA: "LZMA", M_LZMA2: "LZMA2", M_DEFLATE: "Deflate",
        M_BZIP2: "BZip2", M_ZSTD: "ZSTD", M_BCJ: "BCJ", M_P7Z_BCJ: "BCJ",
        M_PPMD: "PPMd", M_DELTA: "Delta", M_ZIP: "Deflate64", M_P7Z_BCJ2: "BCJ2",
    }
    return t.get(mid, "未知/" + mid.hex())


def _decompress_payload(mid, props, pack, unpack_size):
    if mid == M_LZMA2:
        if _lzma is None:
            raise ValueError("LZMA2 不可用")
        return _lzma.decompress(pack, format=_lzma.FORMAT_RAW, filters=[{"id": _lzma.FILTER_LZMA2}])
    if mid == M_LZMA:
        if _lzma is None:
            raise ValueError("LZMA 不可用")
        filt = {"id": _lzma.FILTER_LZMA1}
        if len(props) >= 5:
            d = props[0]
            filt["lc"] = d % 9; filt["lp"] = (d // 9) % 5; filt["pb"] = d // 45
        return _lzma.decompress(pack, format=_lzma.FORMAT_RAW, filters=[filt])
    if mid == M_DEFLATE:
        return zlib.decompress(pack, -15)
    if mid == M_BZIP2:
        return bz2.decompress(pack)
    if mid == M_COPY:
        return pack[:unpack_size] if unpack_size else pack
    if mid == M_ZSTD:
        if _zstd is None:
            raise ValueError("ZSTD 不可用")
        return _zstd.ZstdDecompressor().decompress(pack, max_output_size=max(unpack_size * 2 + 4096, 65536))
    raise ValueError("不支持方法 %s" % _method_name(mid))


def _x86_decode(data):
    out = bytearray(data)
    size = len(out)
    ip = 0; prev_mask = 0; pos = 0
    while pos < size:
        b = out[pos]
        mask = 0
        if b == 0xE8:
            mask = 0x100
        elif b == 0xE9:
            mask = 0x80
        elif b == 0x0F:
            mask = 0x40
        if mask and (prev_mask & mask) == 0:
            if pos + 5 <= size:
                v = int.from_bytes(out[pos + 1:pos + 5], "little")
                v = (v - (ip + pos)) & 0xFFFFFFFF
                out[pos + 1:pos + 5] = v.to_bytes(4, "little")
                pos += 5; ip += 5; prev_mask = 0
                continue
            break
        pos += 1; ip += 1
        prev_mask = (prev_mask >> 1) | (mask >> 1) if mask else (prev_mask >> 1)
    return bytes(out)


def _read_folder(r):
    num_coders = r.uint64()
    coders = []
    totalin = 0; totalout = 0
    for _ in range(num_coders):
        b = r.byte()
        methodsize = b & 0x0F
        mid = r.read(methodsize) if methodsize > 0 else M_COPY
        if b & 0x10:
            num_in = r.uint64(); num_out = r.uint64()
        else:
            num_in = 1; num_out = 1
        props = r.read(r.uint64()) if (b & 0x20) else b""
        totalin += num_in; totalout += num_out
        coders.append({"mid": mid, "num_in": num_in, "num_out": num_out, "props": props})
    num_binds = totalout - 1
    binds = [(r.uint64(), r.uint64()) for _ in range(max(num_binds, 0))]
    num_packed = totalin - num_binds
    if num_packed == 1:
        packed = [0]
    else:
        packed = [r.uint64() for _ in range(max(num_packed, 0))]
    return {"coders": coders, "binds": binds, "packed": packed}


def _decode_folder(folder, packs, unpack_sizes):
    """链式解压 folder。binds 存全局流索引（7z 规范：InIndex OutIndex）"""
    coders = folder["coders"]
    n = len(coders)
    if n == 0:
        return b""
    # 全局流索引映射
    out_global = {}
    g = 0
    for ci, c in enumerate(coders):
        for oi in range(c["num_out"]):
            out_global[(ci, oi)] = g; g += 1
    in_global = {}
    g = 0
    for ci, c in enumerate(coders):
        for ii in range(c["num_in"]):
            in_global[(ci, ii)] = g; g += 1
    bind_ins = set(inc for (inc, outc) in folder["binds"])
    out_to_in = {}
    for (inc, outc) in folder["binds"]:
        out_to_in[outc] = inc
    if n == 1:
        c = coders[0]
        pidx = folder["packed"][0] if folder["packed"] else 0
        pack = packs.get(pidx, b"")
        us = unpack_sizes[0] if unpack_sizes else 0
        if c["mid"] in (M_BCJ, M_P7Z_BCJ):
            return _x86_decode(pack)
        return _decompress_payload(c["mid"], c["props"], pack, us)
    # packed 输入 → 无 bind 输入的 (coder, in)
    inputs = {}
    packed_idx = 0
    for ci, c in enumerate(coders):
        for ii in range(c["num_in"]):
            if in_global[(ci, ii)] not in bind_ins:
                pidx = folder["packed"][packed_idx] if packed_idx < len(folder["packed"]) else 0
                inputs[(ci, ii)] = packs.get(pidx, b"")
                packed_idx += 1
    results = {}
    us_idx = 0
    remaining = set(range(n))
    while remaining:
        progressed = False
        for ci in sorted(remaining):
            if (ci, 0) not in inputs:
                continue
            c = coders[ci]
            us = unpack_sizes[us_idx] if us_idx < len(unpack_sizes) else 0
            if c["mid"] in (M_BCJ, M_P7Z_BCJ):
                out = _x86_decode(inputs[(ci, 0)])
            elif c["mid"] == M_DELTA:
                out = inputs[(ci, 0)]
            else:
                out = _decompress_payload(c["mid"], c["props"], inputs[(ci, 0)], us)
            us_idx += 1
            results[(ci, 0)] = out
            remaining.discard(ci)
            progressed = True
            for oi in range(c["num_out"]):
                og = out_global[(ci, oi)]
                if og in out_to_in:
                    dst = out_to_in[og]
                    for cj, c2 in enumerate(coders):
                        for ij in range(c2["num_in"]):
                            if in_global[(cj, ij)] == dst:
                                inputs[(cj, ij)] = out
            break
        if not progressed:
            raise ValueError("folder 死循环")
    bound_outs = set(outc for (inc, outc) in folder["binds"])
    finals = [(ci, oi) for ci in range(n) for oi in range(coders[ci]["num_out"])
              if out_global[(ci, oi)] not in bound_outs]
    if finals:
        return results.get(finals[-1], b"")
    return results.get(max(results), b"")


def _read_pack_info(r):
    pack_pos = r.uint64()
    num_streams = r.uint64()
    pack_sizes = []
    pid = r.byte()
    if pid == K_SIZE:
        pack_sizes = [r.uint64() for _ in range(num_streams)]
        pid = r.byte()
    if pid == K_CRC:
        defined = read_boolean(r, num_streams)
        for crcexist in defined:
            if crcexist:
                r.read(4)
        pid = r.byte()
    if pid != K_END:
        raise ValueError("PackInfo 期望 END 得到 0x%02x" % pid)
    return {"pos": pack_pos, "sizes": pack_sizes}


def _read_unpack_info(r):
    pid = r.byte()
    if pid != K_FOLDER:
        raise ValueError("UnpackInfo 期望 FOLDER 得到 0x%02x" % pid)
    num_folders = _checked_count(r.uint64(), r, "Folder")
    external = r.byte()
    folders = [_read_folder(r) for _ in range(num_folders)]
    unpack_sizes = []
    pid = r.byte()
    if pid != K_CODERS_UNPACK:
        raise ValueError("UnpackInfo 期望 CODERS_UNPACK 得到 0x%02x" % pid)
    for f in folders:
        for c in f["coders"]:
            for _ in range(c["num_out"]):
                unpack_sizes.append(r.uint64())
    pid = r.byte()
    if pid == K_CRC:
        defined = read_boolean(r, num_folders)
        for d in defined:
            if d:
                r.read(4)
        pid = r.byte()
    if pid != K_END:
        raise ValueError("UnpackInfo 期望 END 得到 0x%02x" % pid)
    return {"folders": folders, "unpack_sizes": unpack_sizes, "num_folders": num_folders}


def _read_substreams_info(r, num_folders, folders):
    sub_num = []
    pid = r.byte()
    if pid == K_NUM_UNPACK:
        sub_num = [r.uint64() for _ in range(num_folders)]
        pid = r.byte()
    else:
        sub_num = [1] * num_folders
    sub_sizes = []
    if pid == K_SIZE:
        for i in range(len(sub_num)):
            total = 0
            for _ in range(1, sub_num[i]):
                s = r.uint64(); sub_sizes.append(s); total += s
            sub_sizes.append(folders[i]["unpack"] - total)
        pid = r.byte()
    if pid == K_CRC:
        num_digests = sum(sn for sn in sub_num)
        defined = read_boolean(r, num_digests)
        for d in defined:
            if d:
                r.read(4)
        pid = r.byte()
    if pid != K_END:
        raise ValueError("SubStreamsInfo 期望 END 得到 0x%02x" % pid)
    return {"sub_num": sub_num, "sub_sizes": sub_sizes}


def _read_streams_info(r, base_pos, file_data):
    pid = r.byte()
    packinfo = None; unpackinfo = None
    if pid == K_PACK_INFO:
        packinfo = _read_pack_info(r)
        pid = r.byte()
    if pid == K_UNPACK_INFO:
        unpackinfo = _read_unpack_info(r)
        pid = r.byte()
    # 预计算每个 folder 的 unpack size（SubStreamsInfo 需要）
    if unpackinfo:
        us_iter = iter(unpackinfo["unpack_sizes"])
        for f in unpackinfo["folders"]:
            sizes = []
            for c in f["coders"]:
                for _ in range(c["num_out"]):
                    sizes.append(next(us_iter))
            f["unpack"] = sizes[-1] if sizes else 0
            f["sizes"] = sizes
    if pid == K_SUB_STREAMS:
        subinfo = _read_substreams_info(r, unpackinfo["num_folders"], unpackinfo["folders"])
        pid = r.byte()
    else:
        subinfo = {"sub_num": None, "sub_sizes": None}
    if pid != K_END:
        raise ValueError("StreamsInfo 期望 END 得到 0x%02x" % pid)
    out = {}
    data_start = base_pos + packinfo["pos"]
    packs = {}
    for pi, psize in enumerate(packinfo["sizes"]):
        packs[pi] = file_data[data_start:data_start + psize]
    idx = 0
    for f in unpackinfo["folders"]:
        out[idx] = _decode_folder(f, packs, f.get("sizes", []))
        idx += 1
    return {"streams": out, "sub_sizes": subinfo.get("sub_sizes")}


def _read_files_info(r):
    num_files = _checked_count(r.uint64(), r, "File")
    files = [{"emptystream": False} for _ in range(num_files)]
    num_empty = 0
    while True:
        pid = r.byte()
        if pid == K_END:
            break
        size = r.uint64()
        if pid == K_DUMMY:
            r.read(size); continue
        buf = Reader(r.read(size))
        if pid == K_EMPTY_STREAM:
            isempty = read_boolean(buf, num_files)
            for i in range(num_files):
                files[i]["emptystream"] = isempty[i]
            num_empty = sum(isempty)
        elif pid == K_EMPTY_FILE:
            ef = read_boolean(buf, num_empty)
            ei = 0
            for f in files:
                if f["emptystream"]:
                    f["emptyfile"] = ef[ei]; ei += 1
        elif pid == K_NAME:
            buf.byte()
            for f in files:
                f["filename"] = _read_utf16(buf).replace("\\", "/")
        elif pid in (K_CTIME, K_ATIME, K_MTIME):
            read_boolean(buf, num_files)
            buf.byte()
        elif pid == K_ATTRS:
            read_boolean(buf, num_files)
            buf.byte()
        elif pid == K_START_POS:
            read_boolean(buf, num_files)
            buf.byte()
        elif pid in (K_ANTI, K_COMMENT, K_ARCHIVE_PROPS):
            pass
        else:
            raise ValueError("FilesInfo 未知属性 0x%02x" % pid)
    return files


def _read_utf16(r):
    out = []
    while True:
        ch = r.read(2)
        if ch == b"\x00\x00" or len(ch) < 2:
            break
        out.append(ch)
    return b"".join(out).decode("utf-16-le", errors="replace")


def _get_next_header(data):
    if len(data) < 32 or data[:6] != MAGIC:
        raise ValueError("不是 7z 文件")
    next_off = int.from_bytes(data[12:20], "little")
    next_size = int.from_bytes(data[20:28], "little")
    base = 32
    raw = data[32 + next_off:32 + next_off + next_size]
    if not raw:
        raise ValueError("空 NextHeader")
    pid = raw[0]
    if pid == K_HEADER:
        return raw, base
    if pid == K_ENCODED_HEADER:
        r = Reader(raw[1:])
        sinfo = _read_streams_info(r, base, data)
        nh = b""
        for fi in sorted(sinfo["streams"]):
            nh += sinfo["streams"][fi]
        if not nh or nh[0] != K_HEADER:
            raise ValueError("解出的头异常: %s" % nh[:16].hex())
        return nh, base
    raise ValueError("NextHeader 未知开头 0x%02x" % pid)


def _parse_header(hdr, file_data, base_pos):
    r = Reader(hdr)
    pid = r.byte()
    if pid == K_HEADER:
        pid = r.byte()
    elif pid == K_ARCHIVE_PROPS:
        pid = r.byte()
    streams = {}
    if pid == K_MAIN_STREAMS:
        sinfo = _read_streams_info(r, base_pos, file_data)
        streams = sinfo["streams"]
        sub_sizes = sinfo["sub_sizes"]
        pid = r.byte()
    else:
        sub_sizes = None
    if pid == K_FILES_INFO:
        files_info = _read_files_info(r)
        pid = r.byte()
    else:
        files_info = None
    if pid != K_END:
        raise ValueError("Header 期望 END 得到 0x%02x" % pid)
    files = []
    if files_info:
        # 流按 folder 展开；sub_sizes 平铺（若有）则按大小分割
        flat = []
        for fi in sorted(streams):
            flat.append(streams[fi])
        if sub_sizes:
            # 平铺为单个大流再按 sizes 切
            blob = b"".join(flat)
            pieces = []
            off = 0
            for s in sub_sizes:
                pieces.append(blob[off:off + s])
                off += s
            if off < len(blob):
                pieces.append(blob[off:])
        else:
            pieces = flat
        si = 0
        for i, f in enumerate(files_info):
            name = f.get("filename", "file_%d" % i)
            if f.get("emptystream"):
                files.append({"name": name, "size": 0, "data": b""})
                continue
            data = pieces[si] if si < len(pieces) else b""
            si += 1
            files.append({"name": name, "size": len(data), "data": data})
    return files


def decompile_7z(data, name="input.7z"):
    try:
        nh, base = _get_next_header(data)
        files = _parse_header(nh, data, base)
    except Exception as e:
        import traceback
        return "7z 解析失败：%s\n%s" % (e, traceback.format_exc(limit=3))
    lines = ["7z 解包完成：共 %d 个文件（%s）" % (len(files), name)]
    for f in files:
        lines.append("- %s (%s)" % (f["name"], _fmt(f["size"])))
    preview = []
    for f in files[:10]:
        if f["data"] and _looks_text(f["data"]):
            try:
                head = f["data"][:400].decode("utf-8", errors="replace")
                preview.append("\n--- %s ---\n%s" % (f["name"], head))
            except Exception:
                pass
    if preview:
        lines.append("\n===== 文本预览 =====")
        lines.extend(preview)
    return "\n".join(lines)


def extract_file(data, target):
    try:
        nh, base = _get_next_header(data)
        files = _parse_header(nh, data, base)
    except Exception:
        return None
    for f in files:
        if f["name"] == target:
            return f["data"]
    return None


def _fmt(n):
    if n >= 1048576: return "%.1f MB" % (n / 1048576)
    if n >= 1024: return "%.1f KB" % (n / 1024)
    return "%d B" % n


def _looks_text(b):
    if not b:
        return False
    try:
        t = b[:512].decode("utf-8")
        return t.count("\ufffd") == 0 and t.strip() != ""
    except Exception:
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1], "rb") as f:
            d = f.read()
        print(decompile_7z(d, sys.argv[1]))
    else:
        print("用法: python sevenz.py <sample.7z>")
