# -*- coding: utf-8 -*-
"""Axiom 二进制反汇编引擎：capstone 反汇编 PE / ELF / Mach-O 可执行文件
架构自动检测：PE(0x10b→x86, 0x20b→x64) / ELF(e_machine) / Mach-O(cputype)
输出：文件头摘要 + 代码段反汇编（前 N 条指令）。
"""
import struct

ARCH_ELF = {
    3: "x86", 8: "mips", 40: "arm", 62: "x86_64", 183: "arm64", 243: "riscv",
}
MACHO_CPU = {7: "x86", 0x01000007: "x86_64", 12: "arm", 0x0100000C: "arm64"}


def detect(data):
    if data[:2] == b"MZ":
        # PE：读 PE 头
        if len(data) < 0x40:
            return None, None, "截断的 PE 文件"
        pe_off = struct.unpack_from("<I", data, 0x3C)[0]
        if data[pe_off:pe_off + 4] != b"PE\x00\x00":
            return None, None, "MZ 但无 PE 签名"
        magic = struct.unpack_from("<H", data, pe_off + 24)[0]
        arch = "x86_64" if magic == 0x20B else ("x86" if magic == 0x10B else "PE-未知")
        # 检测 .NET CLR：optional header 的 DataDirectory[14]（COM Descriptor）
        try:
            opt_size = struct.unpack_from("<H", data, pe_off + 20)[0]
            if magic == 0x20B:
                clr_off = pe_off + 24 + 112 + 14 * 8
            else:
                clr_off = pe_off + 24 + 96 + 14 * 8
            clr_rva, clr_size = struct.unpack_from("<II", data, clr_off)
            if clr_rva and clr_size:
                return "pe-dotnet", arch, None
        except Exception:
            pass
        return "pe", arch, None
    if data[:4] == b"\x7fELF":
        e_machine = struct.unpack_from("<H", data, 18)[0]
        cls = data[4]
        arch = ARCH_ELF.get(e_machine, "elf-%d" % e_machine)
        return "elf", arch, None
    if data[:4] in (b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe"):
        magic = data[:4]
        if magic in (b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf"):
            cputype = struct.unpack_from(">I", data, 4)[0]
        else:
            cputype = struct.unpack_from("<I", data, 4)[0]
        arch = MACHO_CPU.get(cputype, "macho-%x" % cputype)
        return "macho", arch, None
    return None, None, "未识别（不是 PE/ELF/Mach-O）"


def capstone_arch(name):
    from capstone import Cs, CS_ARCH_X86, CS_ARCH_ARM, CS_ARCH_ARM64, CS_ARCH_MIPS, CS_ARCH_RISCV, CS_MODE_32, CS_MODE_64, CS_MODE_ARM, CS_MODE_MIPS32, CS_MODE_RISCV64
    if name == "x86_64":
        return Cs(CS_ARCH_X86, CS_MODE_64)
    if name == "x86":
        return Cs(CS_ARCH_X86, CS_MODE_32)
    if name == "arm64":
        return Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    if name == "arm":
        return Cs(CS_ARCH_ARM, CS_MODE_ARM)
    if name == "mips":
        return Cs(CS_ARCH_MIPS, CS_MODE_MIPS32)
    if name == "riscv":
        return Cs(CS_ARCH_RISCV, CS_MODE_RISCV64)
    return None


def find_code_regions(kind, data, arch):
    """返回 [(偏移, 大小, 标签)] 代码区。"""
    regions = []
    try:
        if kind == "pe":
            pe_off = struct.unpack_from("<I", data, 0x3C)[0]
            nsec = struct.unpack_from("<H", data, pe_off + 6)[0]
            opt = struct.unpack_from("<H", data, pe_off + 20)[0]
            sec_off = pe_off + 24 + opt
            is64 = arch == "x86_64"
            for i in range(min(nsec, 100)):
                base = sec_off + i * 40
                name = data[base:base + 8].rstrip(b"\x00").decode("ascii", "replace")
                vsize = struct.unpack_from("<I", data, base + 8)[0]
                rawsize = struct.unpack_from("<I", data, base + 16)[0]
                rawptr = struct.unpack_from("<I", data, base + 20)[0]
                chars = struct.unpack_from("<I", data, base + 36)[0]
                if chars & 0x20000000 and rawsize > 0:  # 含代码
                    regions.append((rawptr, min(rawsize, vsize or rawsize), name))
        elif kind == "elf":
            cls = data[4]
            if cls == 2:  # 64
                e_phoff = struct.unpack_from("<Q", data, 32)[0]
                e_phentsize = struct.unpack_from("<H", data, 54)[0]
                e_phnum = struct.unpack_from("<H", data, 56)[0]
                for i in range(min(e_phnum, 100)):
                    base = e_phoff + i * e_phentsize
                    p_type = struct.unpack_from("<I", data, base)[0]
                    p_flags = struct.unpack_from("<I", data, base + 4)[0]
                    p_offset = struct.unpack_from("<Q", data, base + 8)[0]
                    p_filesz = struct.unpack_from("<Q", data, base + 32)[0]
                    if p_type == 1 and (p_flags & 5):  # PT_LOAD + R+X
                        regions.append((p_offset, p_filesz, "LOAD(RX)"))
            else:
                e_phoff = struct.unpack_from("<I", data, 28)[0]
                e_phentsize = struct.unpack_from("<H", data, 42)[0]
                e_phnum = struct.unpack_from("<H", data, 44)[0]
                for i in range(min(e_phnum, 100)):
                    base = e_phoff + i * e_phentsize
                    p_type = struct.unpack_from("<I", data, base)[0]
                    p_offset = struct.unpack_from("<I", data, base + 4)[0]
                    p_filesz = struct.unpack_from("<I", data, base + 16)[0]
                    p_flags = struct.unpack_from("<I", data, base + 24)[0]
                    if p_type == 1 and (p_flags & 5):
                        regions.append((p_offset, p_filesz, "LOAD(RX)"))
    except Exception as e:
        return [("ERR", 0, "节表解析失败: %s" % e)]
    return regions


def get_disassembler(arch):
    """优先 capstone（本地/后端），不可用时回退自研 x86 解码器（浏览器内）。"""
    try:
        return ("capstone", capstone_arch(arch))
    except Exception:
        from x86_disasm import X86Decoder
        mode = 64 if arch in ("x86_64", "arm64", "riscv") else 32
        return ("builtin", X86Decoder(mode))


def decompile_binary(data, filename="input.bin", max_insns=800):
    out = []
    kind, arch, err = detect(data)
    if err:
        return "# 无法识别文件格式：%s" % err
    out.append("# 二进制反汇编 · %s · 架构 %s · %d 字节" % (kind.upper(), arch, len(data)))
    if kind == "pe-dotnet":
        out.append("# ⚠ 检测到 .NET CLR 头：这是 .NET 程序集，建议改用 .NET 引擎（dnfile+dncil 输出 CIL）获得更好结果")
        out.append("# 下方为本机 CPU 指令级反汇编（供参考）")
    dis_type, md = get_disassembler(arch)
    if md is None:
        return "\n".join(out) + "\n# 架构 %s 暂不支持" % arch
    if dis_type == "builtin":
        out.append("# 反汇编器：自研 x86 解码器（浏览器内置，覆盖常见指令）")
    else:
        out.append("# 说明：这是汇编级反汇编（不是源码级还原），Windows 桌面版将接入 jadx/CFR/ILSpy 等源码级反编译器")
    regions = find_code_regions(kind, data, arch)
    shown = 0
    for (off, size, label) in regions:
        if shown >= max_insns:
            break
        chunk = data[off:off + min(size, 1 << 20)]
        out.append("")
        out.append("## 代码区 [%s] @0x%x (%d 字节)" % (label, off, size))
        count = 0
        try:
            if dis_type == "capstone":
                for ins in md.disasm(chunk, off):
                    out.append("  0x%x: %-10s %s" % (ins.address, ins.mnemonic, ins.op_str))
                    count += 1
                    shown += 1
                    if shown >= max_insns:
                        break
            else:
                from x86_disasm import disassemble
                mode = 64 if arch in ("x86_64", "arm64", "riscv") else 32
                for (a, m, o) in disassemble(chunk, off, mode, max_insns - shown):
                    if o:
                        out.append("  0x%x: %-10s %s" % (a, m, o))
                    else:
                        out.append("  0x%x: %s" % (a, m))
                    count += 1
                    shown += 1
                    if shown >= max_insns:
                        break
        except Exception as e:
            out.append("  反汇编中断: %s" % e)
        if count == 0:
            out.append("  （该区段无可反汇编内容）")
    if shown >= max_insns:
        out.append("")
        out.append("（指令过多，仅显示前 %d 条）" % max_insns)
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    path = sys.argv[1]
    with open(path, "rb") as f:
        print(decompile_binary(f.read(), path))
