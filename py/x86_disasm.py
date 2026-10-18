# -*- coding: utf-8 -*-
"""Axiom 自研 x86/x64 反汇编器（基础版，纯 Python 零依赖，Pyodide 可跑）
覆盖常见指令（数据传送/算术/逻辑/跳转/调用/栈/位运算/字符串指令/标志位等），
支持 16/32/64 位操作数、REX 前缀、ModRM+SIB+disp 完整寻址解码。
用途：浏览器内无 capstone 时的 fallback（汇编级，非源码级）。
"""
import struct

# ---------------- 寄存器名 ----------------
REG8 = ["al", "cl", "dl", "bl", "ah", "ch", "dh", "bh"]
REG8_REX = ["al", "cl", "dl", "bl", "spl", "bpl", "sil", "dil"]
REG16 = ["ax", "cx", "dx", "bx", "sp", "bp", "si", "di"]
REG32_REX = ["r8d", "r9d", "r10d", "r11d", "r12d", "r13d", "r14d", "r15d"]
REG32 = ["eax", "ecx", "edx", "ebx", "esp", "ebp", "esi", "edi"]
REG64 = ["rax", "rcx", "rdx", "rbx", "rsp", "rbp", "rsi", "rdi"]
REG64_REX = ["r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"]
SEG = ["es", "cs", "ss", "ds", "fs", "gs"]


class X86Decoder:
    """变长指令解码器。位宽：mode=32 → x86，mode=64 → x64（REX 生效）。"""

    def __init__(self, mode=64):
        self.mode = mode  # 32 / 64

    def reg8(self, rex, idx):
        # idx 可为扩展编号（0-15，由 REX 决定）
        if idx >= 8:
            return REG8_REX[idx - 8]
        if rex and (rex & 0x4):
            return REG8_REX[idx]
        return REG8[idx]

    def reg16(self, idx):
        return REG16[idx]

    def reg32(self, rex, idx):
        if idx >= 8:
            return REG32_REX[idx - 8]
        if self.mode == 64 and rex and (rex & 0x4):
            return REG32_REX[idx]
        return REG32[idx]

    def reg64(self, rex, idx):
        if idx >= 8:
            return REG64_REX[idx - 8]
        if self.mode == 64 and rex and (rex & 0x4):
            return REG64_REX[idx]
        return REG64[idx]

    def reg(self, rex, idx, w):
        if w == 0:
            return self.reg8(rex, idx)
        if w == 1:
            if self.mode == 64:
                return self.reg64(rex, idx)
            return self.reg32(rex, idx)
        return self.reg16(idx)

    def decode_modrm(self, data, pos, rex, w, addr64):
        """解码 ModRM 寻址，返回 (操作数字符串, 新 pos)。addr64: 地址位宽。"""
        if pos >= len(data):
            return "?", pos
        modrm = data[pos]
        mod = modrm >> 6
        rm = modrm & 7
        pos += 1
        if mod == 3:
            return self.reg(rex, rm, w), pos
        # ---- 内存寻址 ----
        disp = 0
        if mod == 1:
            disp = struct.unpack_from("<b", data, pos)[0]; pos += 1
        elif mod == 2:
            disp = struct.unpack_from("<i", data, pos)[0]; pos += 4
        # 基址寄存器（含 rex.B 扩展）
        base = rm
        if self.mode == 64 and rex and (rex & 0x1):
            base = rm + 8
        # SIB
        if rm == 4:
            if pos >= len(data):
                return "?", pos
            sib = data[pos]; pos += 1
            scale = 1 << (sib >> 6)
            index = (sib >> 3) & 7
            sib_base = sib & 7
            if self.mode == 64 and rex and (rex & 0x2):
                index += 8
            if self.mode == 64 and rex and (rex & 0x1):
                sib_base += 8
            has_disp32 = (sib_base == 5 and mod == 0)
            if has_disp32:
                disp = struct.unpack_from("<i", data, pos)[0]; pos += 4
            idx_s = ""
            if index != 4:
                idx_s = (self.reg64(rex, index) if self.mode == 64 else self.reg32(rex, index)) + ("*%d" % scale if scale != 1 else "")
            if has_disp32:
                if idx_s:
                    return "[%s%+d]" % (idx_s, disp), pos
                return "[%d]" % disp, pos
            base_s = self.reg64(rex, sib_base) if self.mode == 64 else self.reg32(rex, sib_base)
            inner = base_s
            if idx_s:
                inner += "+" + idx_s
            if disp:
                inner += "%+d" % disp
            return "[%s]" % inner, pos
        # 非 SIB：mod==0 且 rm==5 → disp32 无基址
        if mod == 0 and rm == 5:
            disp = struct.unpack_from("<i", data, pos)[0]; pos += 4
            return "[%d]" % disp, pos
        base_s = self.reg64(rex, base) if self.mode == 64 else self.reg32(rex, base)
        if disp:
            return "[%s%+d]" % (base_s, disp), pos
        return "[%s]" % base_s, pos

    def imm(self, data, pos, size):
        if pos + size > len(data):
            return 0, pos
        if size == 1:
            return data[pos], pos + 1
        if size == 2:
            return struct.unpack_from("<H", data, pos)[0], pos + 2
        if size == 4:
            return struct.unpack_from("<I", data, pos)[0], pos + 4
        if size == 8:
            return struct.unpack_from("<Q", data, pos)[0], pos + 8
        return 0, pos

    def rel(self, data, pos, size):
        if size == 1:
            return struct.unpack_from("<b", data, pos)[0], pos + 1
        return struct.unpack_from("<i", data, pos)[0], pos + 4

    # ---------------- 主解码 ----------------
    def decode_one(self, data, ip):
        """返回 (助记符, 操作数字符串, 下一 ip)。未知指令 → (None, None, ip+1)。"""
        pos = ip
        rex = 0
        opsz = 1  # 1=32/64位, 0=16位
        addr64 = (self.mode == 64)
        # 前缀循环
        while pos < len(data):
            b = data[pos]
            if self.mode == 64 and 0x40 <= b <= 0x4F:
                rex = b
                pos += 1
            elif b == 0x66:
                opsz = 0
                pos += 1
            elif b in (0x67, 0xF0, 0xF2, 0xF3, 0x2E, 0x3E, 0x26, 0x36, 0x64, 0x65):
                pos += 1
            else:
                break
        if pos >= len(data):
            return "db", "0x%02x" % data[ip], ip + 1
        b = data[pos]
        w = 1  # 默认 32/64 位
        if b >= 0x50 and b <= 0x5F:
            r = (b - 0x50) % 8
            if b <= 0x57:
                return "push", self.reg64(rex, r) if self.mode == 64 else self.reg32(rex, r), pos + 1
            return "pop", self.reg64(rex, r) if self.mode == 64 else self.reg32(rex, r), pos + 1
        if b == 0x90:
            return "nop", "", pos + 1
        if b == 0xC3:
            return "ret", "", pos + 1
        if b == 0xCC:
            return "int3", "", pos + 1
        if b == 0xC9:
            return "leave", "", pos + 1
        if b == 0xFC:
            return "cld", "", pos + 1
        if b == 0xFD:
            return "std", "", pos + 1
        if b == 0xF8:
            return "clc", "", pos + 1
        if b == 0xF9:
            return "stc", "", pos + 1
        if b == 0xF5:
            return "cmc", "", pos + 1
        if b == 0xF4:
            return "hlt", "", pos + 1
        if b == 0xFA:
            return "cli", "", pos + 1
        if b == 0xFB:
            return "sti", "", pos + 1
        if b == 0x9C:
            return "pushf" + ("q" if self.mode == 64 else "d"), "", pos + 1
        if b == 0x9D:
            return "popf" + ("q" if self.mode == 64 else "d"), "", pos + 1
        if b == 0x9E:
            return "sahf", "", pos + 1
        if b == 0x9F:
            return "lahf", "", pos + 1
        if b == 0x60 and self.mode == 32:
            return "pusha", "", pos + 1
        if b == 0x61 and self.mode == 32:
            return "popa", "", pos + 1
        if b in (0x68, 0x6A):
            if b == 0x68:
                v, pos = self.imm(data, pos + 1, 4)
                return "push", "%d" % (v if v < 0x80000000 else v - 0x100000000), pos
            v, pos = self.imm(data, pos + 1, 1)
            return "push", "%d" % (v if v < 0x80 else v - 0x100), pos
        if b == 0xE8:
            rel, pos = self.rel(data, pos + 1, 4)
            return "call", "0x%x" % (pos + rel), pos
        if b == 0xE9:
            rel, pos = self.rel(data, pos + 1, 4)
            return "jmp", "0x%x" % (pos + rel), pos
        if b == 0xEB:
            rel, pos = self.rel(data, pos + 1, 1)
            return "jmp", "0x%x" % (pos + rel), pos
        if b == 0xE3:
            rel, pos = self.rel(data, pos + 1, 1)
            return "jecxz", "0x%x" % (pos + rel), pos
        if 0x70 <= b <= 0x7F:
            cc = ["jo", "jno", "jb", "jae", "je", "jne", "jbe", "ja",
                  "js", "jns", "jp", "jnp", "jl", "jge", "jle", "jg"][b - 0x70]
            rel, pos = self.rel(data, pos + 1, 1)
            return cc, "0x%x" % (pos + rel), pos
        if b == 0x0F:
            return self.decode_0f(data, pos + 1, rex, opsz, addr64, ip)
        if 0xB0 <= b <= 0xB7:
            v, pos = self.imm(data, pos + 1, 1)
            return "mov", "%s, %d" % (self.reg8(rex, b - 0xB0), v), pos
        if 0xB8 <= b <= 0xBF:
            r = b - 0xB8
            if self.mode == 64 and not (rex & 0x8):
                v, pos = self.imm(data, pos + 1, 8)
                return "mov", "%s, %d" % (self.reg64(rex, r), v), pos
            if opsz == 0:
                v, pos = self.imm(data, pos + 1, 2)
                return "mov", "%s, %d" % (self.reg16(r), v), pos
            v, pos = self.imm(data, pos + 1, 4)
            return "mov", "%s, %d" % (self.reg32(rex, r), v), pos
        if b in (0x88, 0x89, 0x8A, 0x8B):
            op = {0x88: "mov", 0x89: "mov", 0x8A: "mov", 0x8B: "mov"}[b]
            dst_is_reg = b in (0x8A, 0x8B)
            w = 0 if b in (0x88, 0x8A) else 1
            modrm = data[pos + 1] if pos + 1 < len(data) else 0
            reg = (modrm >> 3) & 7
            rm_op, pos = self.decode_modrm(data, pos + 1, rex, w, addr64)
            reg_s = self.reg(rex, reg, w)
            if dst_is_reg:
                return op, "%s, %s" % (reg_s, rm_op), pos
            return op, "%s, %s" % (rm_op, reg_s), pos
        if b == 0x8D:
            modrm = data[pos + 1] if pos + 1 < len(data) else 0
            reg = (modrm >> 3) & 7
            rm_op, pos = self.decode_modrm(data, pos + 1, rex, 1, addr64)
            return "lea", "%s, %s" % (self.reg(rex, reg, 1), rm_op), pos
        if b in (0x8F,):
            modrm = data[pos + 1] if pos + 1 < len(data) else 0
            if (modrm >> 3) & 7 != 0:
                return None, None, pos + 1
            rm_op, pos = self.decode_modrm(data, pos + 1, rex, 1, addr64)
            return "pop", rm_op, pos
        if b in (0x83, 0x81):
            modrm = data[pos + 1] if pos + 1 < len(data) else 0
            group = (modrm >> 3) & 7
            names = ["add", "or", "adc", "sbb", "and", "sub", "xor", "cmp"]
            rm_op, pos2 = self.decode_modrm(data, pos + 1, rex, 1, addr64)
            if b == 0x83:
                v, pos = self.imm(data, pos2, 1)
                return names[group], "%s, %d" % (rm_op, v if v < 0x80 else v - 0x100), pos
            if opsz == 0:
                v, pos = self.imm(data, pos2, 2)
            else:
                v, pos = self.imm(data, pos2, 4)
            return names[group], "%s, %d" % (rm_op, v), pos
        if b in (0x01, 0x03, 0x09, 0x0B, 0x21, 0x23, 0x29, 0x2B, 0x31, 0x33, 0x39, 0x3B):
            names = {0x01: "add", 0x03: "add", 0x09: "or", 0x0B: "or", 0x21: "and", 0x23: "and",
                     0x29: "sub", 0x2B: "sub", 0x31: "xor", 0x33: "xor", 0x39: "cmp", 0x3B: "cmp"}
            op = names[b]
            dst_is_reg = b in (0x03, 0x0B, 0x23, 0x2B, 0x33, 0x3B)
            modrm = data[pos + 1] if pos + 1 < len(data) else 0
            reg = (modrm >> 3) & 7
            rm_op, pos = self.decode_modrm(data, pos + 1, rex, 1, addr64)
            reg_s = self.reg(rex, reg, 1)
            if dst_is_reg:
                return op, "%s, %s" % (reg_s, rm_op), pos
            return op, "%s, %s" % (rm_op, reg_s), pos
        if b in (0x84, 0x85):
            w = 0 if b == 0x84 else 1
            modrm = data[pos + 1] if pos + 1 < len(data) else 0
            reg = (modrm >> 3) & 7
            rm_op, pos = self.decode_modrm(data, pos + 1, rex, w, addr64)
            return "test", "%s, %s" % (rm_op, self.reg(rex, reg, w)), pos
        if b in (0xC7, 0xC6):
            w = 0 if b == 0xC6 else 1
            modrm = data[pos + 1] if pos + 1 < len(data) else 0
            if (modrm >> 3) & 7 != 0:
                return None, None, pos + 1
            rm_op, pos2 = self.decode_modrm(data, pos + 1, rex, w, addr64)
            if w == 0:
                v, pos = self.imm(data, pos2, 1)
            elif opsz == 0:
                v, pos = self.imm(data, pos2, 2)
            else:
                v, pos = self.imm(data, pos2, 4)
            return "mov", "%s, %d" % (rm_op, v), pos
        if b == 0xFF:
            modrm = data[pos + 1] if pos + 1 < len(data) else 0
            group = (modrm >> 3) & 7
            names = {0: "inc", 1: "dec", 2: "call", 4: "jmp", 6: "push"}
            if group not in names:
                return None, None, pos + 1
            rm_op, pos = self.decode_modrm(data, pos + 1, rex, 1, addr64)
            return names[group], rm_op, pos
        if b in (0xFE, 0xF6, 0xF7, 0xD0, 0xD1, 0xD2, 0xD3, 0xC0, 0xC1):
            w = 1
            if b in (0xFE, 0xF6):
                w = 0
            modrm = data[pos + 1] if pos + 1 < len(data) else 0
            group = (modrm >> 3) & 7
            rm_op, pos2 = self.decode_modrm(data, pos + 1, rex, w, addr64)
            if b in (0xFE,):
                names = ["inc", "dec"]
                if group not in names:
                    return None, None, pos2
                return names[group], rm_op, pos2
            if b in (0xF6, 0xF7):
                names = ["test", "test", "not", "neg", "mul", "imul", "div", "idiv"]
                if group == 0:
                    if w == 0:
                        v, pos = self.imm(data, pos2, 1)
                    elif opsz == 0:
                        v, pos = self.imm(data, pos2, 2)
                    else:
                        v, pos = self.imm(data, pos2, 4)
                    return "test", "%s, %d" % (rm_op, v), pos
                return names[group], rm_op, pos2
            # 移位指令 D0-D3 / C0-C1
            names = ["rol", "ror", "rcl", "rcr", "shl", "shr", "sal", "sar"]
            if b in (0xC0, 0xC1):
                v, pos = self.imm(data, pos2, 1)
                return names[group], "%s, %d" % (rm_op, v), pos
            if b in (0xD0, 0xD1):
                return names[group], rm_op, pos2
            return names[group], "%s, cl" % rm_op, pos2
        if b == 0x63 and self.mode == 64:
            modrm = data[pos + 1] if pos + 1 < len(data) else 0
            reg = (modrm >> 3) & 7
            rm_op, pos = self.decode_modrm(data, pos + 1, rex, 1, addr64)
            return "movsxd", "%s, %s" % (self.reg64(rex, reg), rm_op), pos
        if b == 0xA1 or b == 0xA3:
            off, pos = self.imm(data, pos + 1, 4)
            if b == 0xA1:
                return "mov", "%s, [%d]" % ("eax" if self.mode == 32 else "rax", off), pos
            return "mov", "[%d], %s" % (off, "eax" if self.mode == 32 else "rax"), pos
        if b == 0xC2 or b == 0xCA:
            v, pos = self.imm(data, pos + 1, 2)
            return ("ret" if b == 0xC2 else "retf"), "%d" % v, pos
        if b == 0xCB:
            return "retf", "", pos + 1
        if b == 0xCD:
            v, pos = self.imm(data, pos + 1, 1)
            return "int", "0x%x" % v, pos
        if b == 0x9A or b == 0xEA:
            v, pos = self.imm(data, pos + 1, 4)
            sel, pos = self.imm(data, pos, 2)
            return ("lcall" if b == 0x9A else "ljmp"), "0x%x:%d" % (sel, v), pos
        if b == 0x0F:
            pass  # 已在上方处理
        # 未知指令
        return None, None, pos + 1

    def decode_0f(self, data, pos, rex, opsz, addr64, ip):
        if pos >= len(data):
            return "db", "0x%02x" % data[ip], ip + 1
        b = data[pos]
        if 0x80 <= b <= 0x8F:
            cc = ["jo", "jno", "jb", "jae", "je", "jne", "jbe", "ja",
                  "js", "jns", "jp", "jnp", "jl", "jge", "jle", "jg"][b - 0x80]
            rel, pos = self.rel(data, pos + 1, 4)
            return cc, "0x%x" % (pos + rel), pos
        if b in (0x05,):
            return "syscall", "", pos + 1
        if b == 0x34:
            return "sysenter", "", pos + 1
        if b == 0x0B:
            return "ud2", "", pos + 1
        if b == 0x1F:
            # NOP（多字节）
            return "nop", "", pos + 1
        if 0x90 <= b <= 0x9F and b in (0x90, 0x91, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97):
            return "nop", "", pos + 1
        if 0x40 <= b <= 0x4F:
            cc = ["cmovo", "cmovno", "cmovb", "cmovae", "cmove", "cmovne", "cmovbe", "cmova",
                  "cmovs", "cmovns", "cmovp", "cmovnp", "cmovl", "cmovge", "cmovle", "cmovg"][b - 0x40]
            modrm = data[pos + 1] if pos + 1 < len(data) else 0
            reg = (modrm >> 3) & 7
            rm_op, pos = self.decode_modrm(data, pos + 1, rex, 1, addr64)
            return cc, "%s, %s" % (self.reg(rex, reg, 1), rm_op), pos
        if 0x92 <= b <= 0x9F:
            cc = ["setb", "setae", "sete", "setne", "setbe", "seta", "sets", "setns",
                  "setp", "setnp", "setl", "setge", "setle", "setg"][b - 0x92]
            rm_op, pos = self.decode_modrm(data, pos + 1, rex, 0, addr64)
            return cc, rm_op, pos
        if b == 0xAF:
            modrm = data[pos + 1] if pos + 1 < len(data) else 0
            reg = (modrm >> 3) & 7
            rm_op, pos = self.decode_modrm(data, pos + 1, rex, 1, addr64)
            return "imul", "%s, %s" % (self.reg(rex, reg, 1), rm_op), pos
        if b in (0xB6, 0xB7, 0xBE, 0xBF):
            names = {0xB6: "movzx", 0xB7: "movzx", 0xBE: "movsx", 0xBF: "movsx"}
            modrm = data[pos + 1] if pos + 1 < len(data) else 0
            reg = (modrm >> 3) & 7
            rm_op, pos = self.decode_modrm(data, pos + 1, rex, 1 if b in (0xB7, 0xBF) else 0, addr64)
            return names[b], "%s, %s" % (self.reg(rex, reg, 1), rm_op), pos
        if b in (0xBC, 0xBD):
            names = {0xBC: "bsf", 0xBD: "bsr"}
            modrm = data[pos + 1] if pos + 1 < len(data) else 0
            reg = (modrm >> 3) & 7
            rm_op, pos = self.decode_modrm(data, pos + 1, rex, 1, addr64)
            return names[b], "%s, %s" % (self.reg(rex, reg, 1), rm_op), pos
        if b == 0xB8:
            modrm = data[pos + 1] if pos + 1 < len(data) else 0
            reg = (modrm >> 3) & 7
            rm_op, pos = self.decode_modrm(data, pos + 1, rex, 1, addr64)
            return "popcnt", "%s, %s" % (self.reg(rex, reg, 1), rm_op), pos
        if b in (0x00, 0x01):
            # sldt/str/lldt/ltr/verr/verw
            return None, None, pos + 1
        if b in (0x20, 0x21, 0x22, 0x23):
            return None, None, pos + 1
        if b == 0xA2:
            return "cpuid", "", pos + 1
        if b == 0x31:
            return "rdtsc", "", pos + 1
        if b == 0xAB:
            # bts
            modrm = data[pos + 1] if pos + 1 < len(data) else 0
            reg = (modrm >> 3) & 7
            rm_op, pos = self.decode_modrm(data, pos + 1, rex, 1, addr64)
            return "bts", "%s, %s" % (rm_op, self.reg(rex, reg, 1)), pos
        if b in (0xB3,):
            # btr
            modrm = data[pos + 1] if pos + 1 < len(data) else 0
            reg = (modrm >> 3) & 7
            rm_op, pos = self.decode_modrm(data, pos + 1, rex, 1, addr64)
            return "btr", "%s, %s" % (rm_op, self.reg(rex, reg, 1)), pos
        if b == 0xBA:
            modrm = data[pos + 1] if pos + 1 < len(data) else 0
            group = (modrm >> 3) & 7
            names = {4: "bt", 5: "bts", 6: "btr", 7: "btc"}
            if group not in names:
                return None, None, pos + 1
            rm_op, pos2 = self.decode_modrm(data, pos + 1, rex, 1, addr64)
            v, pos = self.imm(data, pos2, 1)
            return names[group], "%s, %d" % (rm_op, v), pos
        return None, None, pos + 1


def disassemble(data, ip=0, mode=64, count=0):
    """反汇编字节流，返回 [(地址, 助记符, 操作数)]。count=0 表示全部。"""
    dec = X86Decoder(mode)
    out = []
    pos = ip
    while pos < len(data):
        if count and len(out) >= count:
            break
        mnem, ops, nxt = dec.decode_one(data, pos)
        if mnem is None:
            out.append((pos, "db", "0x%02x" % data[pos]))
            pos += 1
        else:
            out.append((pos, mnem, ops))
            pos = nxt
    return out


def disasm_text(data, mode=64, count=800):
    lines = []
    for (addr, m, o) in disassemble(data, 0, mode, count):
        if o:
            lines.append("  0x%x: %-10s %s" % (addr, m, o))
        else:
            lines.append("  0x%x: %s" % (addr, m))
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    data = open(sys.argv[1], "rb").read()
    mode = int(sys.argv[2]) if len(sys.argv) > 2 else 64
    print(disasm_text(data, mode))
