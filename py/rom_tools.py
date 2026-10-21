# -*- coding: utf-8 -*-
"""rom_tools.py — 游戏主机 ROM 头解析引擎（零依赖）
覆盖：NES/GB/GBC/GBA/NDS/N64(z64)/SFC/SMC/FDS/CIA
仅读固定偏移头字段，不做深解。
"""

import struct


def _clean(b):
    s = b.decode("latin1")
    s = "".join(ch for ch in s if 32 <= ord(ch) < 127)
    return s.strip()


def parse_nes(data):
    if data[:4] != b"NES\x1a":
        return None
    prg = data[4]
    chr = data[5]
    mapper = (data[6] >> 4) | (data[7] & 0xF0)
    out = ["NES ROM（iNES 头）"]
    out.append("PRG-ROM: %d × 16KB（%d KB）" % (prg, prg * 16))
    out.append("CHR-ROM: %d × 8KB（%d KB）" % (chr, chr * 8))
    out.append("Mapper: %d" % mapper)
    flags = []
    if data[6] & 0x08:
        flags.append("四屏 VRAM")
    if data[6] & 0x04:
        flags.append("电池备份")
    if data[6] & 0x02:
        flags.append("训练器")
    if data[7] & 0x08:
        flags.append("PAL")
    if flags:
        out.append("特性: " + "/".join(flags))
    return "\n".join(out)


def _parse_gb(data, title_off, cgb_check):
    if data[0x104:0x10C] != b"Nintendo":
        return None
    title = _clean(data[0x134:0x144])
    out = ["%s ROM" % ("Game Boy Color" if cgb_check and data[0x143] == 0x80 else "Game Boy")]
    out.append("标题: " + title)
    cart_type = data[0x147]
    out.append("卡带类型: 0x%02X" % cart_type)
    rom_sz = {0: 32, 1: 64, 2: 128, 3: 256, 4: 512, 5: 1024, 6: 2048,
              0x52: 1152, 0x53: 1280, 0x54: 1536}.get(data[0x148], -1)
    out.append("ROM 大小: %s KB" % (rom_sz if rom_sz > 0 else "未知(0x%02X)" % data[0x148]))
    if data[0x143] == 0x80:
        out.append("标志: CGB 增强")
    elif data[0x143] == 0xC0:
        out.append("标志: CGB 独占")
    return "\n".join(out)


def parse_gb(data):
    if data[:4] != b"\x80\x00\x00\x00" or data[0x104:0x10C] != b"Nintendo":
        return None
    return _parse_gb(data, 0x134, True)


def parse_gba(data):
    # GBA 头：0xAC 处 gamecode / 0xA0 处标题（12B）
    if data[:4] != b"\x00\x00\x00\x00":
        return None
    title = _clean(data[0xA0:0xAC])
    if not title:
        return None
    out = ["Game Boy Advance ROM"]
    out.append("标题: " + title)
    code = _clean(data[0xAC:0xB0])
    maker = _clean(data[0xB0:0xB2])
    out.append("GameCode: %s  Maker: %s" % (code, maker or "?"))
    return "\n".join(out)


def parse_nds(data):
    title = _clean(data[0x0:0xC])
    if not title and data[0:4] not in (b"\x00\x00\x00\x00", b"\x12\x00\x00\x00"):
        return None
    out = ["Nintendo DS ROM"]
    if title:
        out.append("标题: " + title)
    code = _clean(data[0xC:0x10])
    maker = _clean(data[0x10:0x12])
    out.append("GameCode: %s  Maker: %s" % (code or "?", maker or "?"))
    return "\n".join(out)


def parse_n64(data):
    # 大端 z64：0x0 处 0x80371240；小端 n64：0x3F800000（解混淆后）
    be = data[:4] == b"\x80\x37\x12\x40"
    le = data[:4] == b"\x40\x12\x37\x80"
    if not (be or le):
        return None
    title = _clean(data[0x20:0x40])
    out = ["Nintendo 64 ROM（%s）" % ("大端 z64" if be else "小端 n64")]
    if title:
        out.append("标题: " + title)
    region = _clean(data[0x3E:0x40])
    out.append("区域码: " + (region or "?"))
    crc1, crc2 = struct.unpack(">II", data[0x10:0x18]) if be else struct.unpack("<II", data[0x10:0x18])
    out.append("CRC1: %08X  CRC2: %08X" % (crc1, crc2))
    return "\n".join(out)


def _snes_title(data, base):
    t = _clean(data[base + 0x7FC0:base + 0x7FD5])
    return t or _clean(data[base + 0x7FB0:base + 0x7FBE])


def parse_sfc(data):
    # 无 copier 头，LoROM 常见 0x7FC0 标题
    t = _snes_title(data, 0)
    if not t:
        return None
    out = ["SNES ROM（sfc）"]
    out.append("标题: " + t)
    out.append("ROM 大小: %d KB" % (len(data) // 1024))
    return "\n".join(out)


def parse_smc(data):
    # SMC 带 512B copier 头（0xFD2D31 魔数区）
    if len(data) < 512:
        return None
    base = 512
    t = _snes_title(data, base)
    if not t:
        base = 0
        t = _snes_title(data, 0)
    if not t:
        return None
    out = ["SNES ROM（smc，含 512B copier 头）"]
    out.append("标题: " + t)
    out.append("ROM 大小: %d KB" % (len(data) // 1024))
    return "\n".join(out)


def parse_fds(data):
    if data[:4] != b"FDS\x1a":
        return None
    out = ["Famicom Disk System 镜像（fds）"]
    lic = _clean(data[4:12])
    out.append("许可: " + (lic or "?"))
    disks = data[0x10] if len(data) > 0x10 else 0
    side = data[0x11] if len(data) > 0x11 else 0
    out.append("磁盘数: %d  当前盘侧: %d" % (disks, side))
    out.append("总大小: %d B" % len(data))
    return "\n".join(out)


def parse_cia(data):
    if len(data) < 0x20:
        return None
    hdr = struct.unpack("<IIII", data[0:0x10])
    if hdr[0] > 0x8000:
        return None
    out = ["3DS CIA 安装包"]
    out.append("头大小: %d B" % hdr[0])
    out.append("证书: %d B" % hdr[1])
    out.append("tik 偏移: %d  大小: %d" % (hdr[2], hdr[3]))
    out.append("总大小: %d B" % len(data))
    return "\n".join(out)


def parse_rom(data, filename):
    fn = (filename or "").lower()
    ext = fn.rsplit(".", 1)[-1] if "." in fn else ""
    if ext == "nes":
        r = parse_nes(data)
        if r:
            return r
    if ext in ("gb", "gbc"):
        r = parse_gb(data)
        if r:
            return r
    if ext == "gba":
        r = parse_gba(data)
        if r:
            return r
    if ext == "nds":
        r = parse_nds(data)
        if r:
            return r
    if ext in ("n64", "z64", "v64"):
        r = parse_n64(data)
        if r:
            return r
    if ext == "sfc":
        r = parse_sfc(data)
        if r:
            return r
    if ext == "smc":
        r = parse_smc(data)
        if r:
            return r
    if ext == "fds":
        r = parse_fds(data)
        if r:
            return r
    if ext == "cia":
        r = parse_cia(data)
        if r:
            return r
    for parser in (parse_nes, parse_gb, parse_gba, parse_nds, parse_n64,
                   parse_sfc, parse_smc, parse_fds, parse_cia):
        try:
            r = parser(data)
        except Exception:
            continue
        if r is not None:
            return r
    if ext:
        return "该 ROM 格式（.%s）暂无头解析器；大小 %d B。" % (ext, len(data))
    return "未知游戏 ROM/镜像二进制：%d B" % len(data)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        with open(sys.argv[1], "rb") as f:
            print(parse_rom(f.read(), sys.argv[1]))
