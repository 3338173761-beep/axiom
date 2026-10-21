# -*- coding: utf-8 -*-
"""iso_tools — ISO9660 光盘镜像解析（零依赖）：
卷描述符（PVD）元数据 + 根目录/子目录树遍历（文件列表 + 大小）。
入口：parse_iso(data) -> str|None
"""
import struct


def _iso_str(b):
    return b.rstrip(b" \x00").decode("latin1", "replace")


def _drec(data, off):
    """目录记录（DR）：返回 (name, flags, LBA, size) 或 None"""
    ln = data[off]
    if ln < 33:
        return None
    flags = data[off + 25]
    lba = struct.unpack("<I", data[off + 2:off + 6])[0]
    size = struct.unpack("<I", data[off + 10:off + 14])[0]
    nlen = data[off + 32]
    name = _iso_str(data[off + 33:off + 33 + nlen])
    return (name, flags, lba, size)


def _walk(data, lba, depth, out, budget):
    """遍历一个目录扇区（含续接扇区），列出其子目录与文件"""
    if depth > 8 or budget[0] <= 0:
        return
    sector = lba * 2048
    chain = []
    seen = set()
    guard = 0
    cur = sector
    while cur + 2048 <= len(data) and cur not in seen and guard < 64:
        seen.add(cur)
        chain.append(cur)
        # 续接：目录记录尾部会带 ext 记录（28 字节，LBA 续接）。简化：同扇区内找有效记录后继续
        guard += 1
        # ISO9660 多扇区目录用记录续接字段（offset 27, 4 字节 BE LBA）
        blk = data[cur:cur + 2048]
        # 找第一条记录判断是否有续接（记录 0 的 ext 字段）
        if blk[0] >= 33:
            ext_lba = struct.unpack(">I", blk[27:31])[0]
            if ext_lba:
                cur = ext_lba * 2048
                continue
        break
    for sec in chain:
        off = 0
        while off + 33 <= 2048 and budget[0] > 0:
            ln = data[sec + off]
            if ln == 0:
                break
            dr = _drec(data, sec + off)
            off += ln
            if dr is None:
                break
            name, flags, lba, size = dr
            if name in ("", "\x00", "\x01"):
                continue
            is_dir = flags & 0x02
            prefix = "  " * (depth + 1)
            if is_dir:
                budget[0] -= 1
                out.append("%s[目录] %s/" % (prefix, name))
                _walk(data, lba, depth + 1, out, budget)
            else:
                budget[0] -= 1
                out.append("%s%s（%d 字节）" % (prefix, name, size))


def parse_iso(data):
    if len(data) < 16 * 2048 + 6:
        return None
    if data[32769:32774] != b"CD001":
        return None
    out = ["ISO9660 光盘镜像", "大小: %d 字节（%d 个 2KB 扇区）" % (len(data), len(data) // 2048)]
    pvd = data[16 * 2048:(16 + 1) * 2048]
    out.append("系统: %s" % _iso_str(pvd[8:40]))
    out.append("卷标: %s" % _iso_str(pvd[40:72]))
    out.append("卷集: %s" % _iso_str(pvd[190:318]))
    out.append("出版: %s" % _iso_str(pvd[318:446]))
    out.append("程序: %s" % _iso_str(pvd[574:606]))
    root = pvd[156:190]
    if root[0]:
        rname, rflags, rlba, rsize = _drec(pvd, 156)
        out.append("根目录: %s（%d 字节）" % (rname, rsize))
        budget = [240]
        _walk(data, rlba, 0, out, budget)
        if budget[0] <= 0:
            out.append("… 列表截断（条目过多）")
    return "\n".join(out)
