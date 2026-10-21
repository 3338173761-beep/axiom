# -*- coding: utf-8 -*-
"""image_tools.py — TIFF/相机 RAW 头解析引擎（零依赖）
覆盖：TIFF（tif/tiff）及相机 RAW 变体 dng/cr2/nef/arw/orf/pef/rw2/srw
原理：TIFF 系文件共用 IFD 结构，读 IFD0 的 Make/Model/宽/高/压缩即可。
"""

import struct


def parse_tiff(data):
    if len(data) < 8:
        return None
    bo = data[:2]
    if bo == b"II":
        endian = "<"
    elif bo == b"MM":
        endian = ">"
    else:
        return None
    if data[2:4] != b"\x2a\x00" and data[2:4] != b"\x00\x2a":
        return None
    ifd_off = struct.unpack_from(endian + "I", data, 4)[0]
    if ifd_off == 0 or ifd_off + 2 > len(data):
        return None
    n = struct.unpack_from(endian + "H", data, ifd_off)[0]
    if n == 0 or n > 512:
        return None
    out = ["TIFF/相机 RAW（IFD 结构）"]
    tags = {}
    for i in range(n):
        off = ifd_off + 2 + i * 12
        if off + 12 > len(data):
            break
        tag, typ, cnt, val = struct.unpack_from(endian + "HHII", data, off)
        if typ == 3 and cnt == 1:
            v = val & 0xFFFF
        elif typ in (1, 4) and cnt == 1:
            v = val
        elif typ == 2 and cnt <= 4:
            v = data[off + 8:off + 8 + cnt].rstrip(b"\x00").decode("latin1", "replace")
        else:
            continue
        tags[tag] = v
    if 271 in tags:
        out.append("厂商: " + str(tags[271]))
    if 272 in tags:
        out.append("型号: " + str(tags[272]))
    w = tags.get(256)
    h = tags.get(257)
    if w and h:
        out.append("尺寸: %s × %s" % (w, h))
    comp = tags.get(259)
    if comp is not None:
        comps = {1: "无压缩", 2: "CCITT RLE", 5: "LZW", 6: "JPEG旧", 7: "JPEG",
                 8: "Deflate", 32773: "PackBits", 34892: "Lossy JPEG", 34893: "Deflate(RAW)"}
        out.append("压缩: %s" % comps.get(comp, "0x%X" % comp))
    bps = tags.get(258)
    if bps:
        out.append("位深: %s bps" % bps)
    return "\n".join(out)


def parse_image_raw(data, filename):
    fn = (filename or "").lower()
    ext = fn.rsplit(".", 1)[-1] if "." in fn else ""
    r = parse_tiff(data)
    if r is not None:
        return r
    if ext:
        return "该相机 RAW 格式（.%s）暂无解析器；大小 %d B。" % (ext, len(data))
    return "未知图像/RAW 二进制：%d B" % len(data)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        with open(sys.argv[1], "rb") as f:
            print(parse_image_raw(f.read(), sys.argv[1]))
