# -*- coding: utf-8 -*-
"""Axiom 自研 Dalvik(DEX) 反汇编器：解析 DEX → .smali 汇编
纯 Python 零依赖，可在 Pyodide(浏览器) 与本地 Python 运行。
输出：类、字段、方法签名 + 逐指令 smali（覆盖常用指令，未知 opcode 保留 hex 占位不崩溃）。
"""
import struct

# ---------- MUTF-8 ----------
def mutf8_decode(data, off):
    """DEX 字符串是 MUTF-8（改进 UTF-8，0xC0 0x80 表示 NUL）。"""
    out = []
    while True:
        b = data[off]
        off += 1
        if b == 0:
            break
        if b < 0x80:
            out.append(chr(b))
        elif b < 0xE0:
            b2 = data[off]; off += 1
            out.append(chr(((b & 0x1F) << 6) | (b2 & 0x3F)))
        elif b < 0xF0:
            b2 = data[off]; off += 1
            b3 = data[off]; off += 1
            out.append(chr(((b & 0x0F) << 12) | ((b2 & 0x3F) << 6) | (b3 & 0x3F)))
        else:
            # surrogate pair
            b2 = data[off]; off += 1
            b3 = data[off]; off += 1
            b4 = data[off]; off += 1
            cp = ((b & 0x07) << 18) | ((b2 & 0x3F) << 12) | ((b3 & 0x3F) << 6) | (b4 & 0x3F)
            if 0x10000 <= cp <= 0x10FFFF:
                cp -= 0x10000
                out.append(chr(0xD800 + (cp >> 10)))
                out.append(chr(0xDC00 + (cp & 0x3FF)))
            else:
                out.append(chr(cp))
    return "".join(out)

def uleb128(data, off):
    result = 0
    shift = 0
    while True:
        b = data[off]; off += 1
        result |= (b & 0x7F) << shift
        if (b & 0x80) == 0:
            break
        shift += 7
    return result, off

def sleb128(data, off):
    result = 0
    shift = 0
    b = 0
    while True:
        b = data[off]; off += 1
        result |= (b & 0x7F) << shift
        shift += 7
        if (b & 0x80) == 0:
            break
    if shift < 32 and (b & 0x40):
        result |= -(1 << shift)
    return result, off

# ---------- Dalvik 指令表（opcode → (格式, 助记符)） ----------
# 格式：10x 12x 11n 11x 10t 20t 21t 21s 21h 21c 22x 22t 22s 22c 23x 22b
#       31t 31i 31c 32x 35c 3rc 51l 52c 53c 54c 55c 56c 57c 45cc 4rcc
INST = {
    0x00: ("10x", "nop"), 0x01: ("12x", "move"), 0x02: ("12x", "move/from16"),
    0x03: ("22x", "move/16"), 0x04: ("12x", "move-wide"), 0x05: ("12x", "move-wide/from16"),
    0x06: ("22x", "move-wide/16"), 0x07: ("12x", "move-object"), 0x08: ("12x", "move-object/from16"),
    0x09: ("22x", "move-object/16"), 0x0A: ("11x", "move-result"), 0x0B: ("11x", "move-result-wide"),
    0x0C: ("11x", "move-result-object"), 0x0D: ("11x", "move-exception"),
    0x0E: ("10x", "return-void"), 0x0F: ("11x", "return"), 0x10: ("11x", "return-wide"),
    0x11: ("11x", "return-object"), 0x12: ("11n", "const/4"), 0x13: ("21s", "const/16"),
    0x14: ("31i", "const"), 0x15: ("21h", "const/high16"), 0x16: ("21s", "const-wide/16"),
    0x17: ("31i", "const-wide/32"), 0x18: ("51l", "const-wide"), 0x19: ("21h", "const-wide/high16"),
    0x1A: ("21c", "const-string"), 0x1B: ("31c", "const-string/jumbo"),
    0x1C: ("21c", "const-class"), 0x1D: ("11x", "monitor-enter"), 0x1E: ("11x", "monitor-exit"),
    0x1F: ("21c", "check-cast"), 0x20: ("22c", "instance-of"), 0x21: ("12x", "array-length"),
    0x22: ("21c", "new-instance"), 0x23: ("31c", "new-array"),
    0x24: ("35c", "filled-new-array"), 0x25: ("3rc", "filled-new-array/range"),
    0x26: ("31t", "fill-array-data"), 0x27: ("11x", "throw"),
    0x28: ("10t", "goto"), 0x29: ("20t", "goto/16"), 0x2A: ("31t", "goto/32"),
    0x2B: ("31t", "packed-switch"), 0x2C: ("31t", "sparse-switch"),
    0x2D: ("23x", "cmpl-float"), 0x2E: ("23x", "cmpg-float"), 0x2F: ("23x", "cmpl-double"),
    0x30: ("23x", "cmpg-double"), 0x31: ("23x", "cmp-long"),
    0x32: ("22t", "if-eq"), 0x33: ("22t", "if-ne"), 0x34: ("22t", "if-lt"),
    0x35: ("22t", "if-ge"), 0x36: ("22t", "if-gt"), 0x37: ("22t", "if-le"),
    0x38: ("21t", "if-eqz"), 0x39: ("21t", "if-nez"), 0x3A: ("21t", "if-ltz"),
    0x3B: ("21t", "if-gez"), 0x3C: ("21t", "if-gtz"), 0x3D: ("21t", "if-lez"),
    0x3E: ("10x", "unused-3e"), 0x3F: ("10x", "unused-3f"), 0x40: ("10x", "unused-40"),
    0x41: ("10x", "unused-41"), 0x42: ("10x", "unused-42"), 0x43: ("10x", "unused-43"),
    0x44: ("23x", "aget"), 0x45: ("23x", "aget-wide"), 0x46: ("23x", "aget-object"),
    0x47: ("23x", "aget-boolean"), 0x48: ("23x", "aget-byte"), 0x49: ("23x", "aget-char"),
    0x4A: ("23x", "aget-short"), 0x4B: ("23x", "aput"), 0x4C: ("23x", "aput-wide"),
    0x4D: ("23x", "aput-object"), 0x4E: ("23x", "aput-boolean"), 0x4F: ("23x", "aput-byte"),
    0x50: ("23x", "aput-char"), 0x51: ("23x", "aput-short"), 0x52: ("22c", "iget"),
    0x53: ("22c", "iget-wide"), 0x54: ("22c", "iget-object"), 0x55: ("22c", "iget-boolean"),
    0x56: ("22c", "iget-byte"), 0x57: ("22c", "iget-char"), 0x58: ("22c", "iget-short"),
    0x59: ("22c", "iput"), 0x5A: ("22c", "iput-wide"), 0x5B: ("22c", "iput-object"),
    0x5C: ("22c", "iput-boolean"), 0x5D: ("22c", "iput-byte"), 0x5E: ("22c", "iput-char"),
    0x5F: ("22c", "iput-short"), 0x60: ("22c", "sget"), 0x61: ("22c", "sget-wide"),
    0x62: ("22c", "sget-object"), 0x63: ("22c", "sget-boolean"), 0x64: ("22c", "sget-byte"),
    0x65: ("22c", "sget-char"), 0x66: ("22c", "sget-short"), 0x67: ("22c", "sput"),
    0x68: ("22c", "sput-wide"), 0x69: ("22c", "sput-object"), 0x6A: ("22c", "sput-boolean"),
    0x6B: ("22c", "sput-byte"), 0x6C: ("22c", "sput-char"), 0x6D: ("22c", "sput-short"),
    0x6E: ("35c", "invoke-virtual"), 0x6F: ("35c", "invoke-super"), 0x70: ("35c", "invoke-direct"),
    0x71: ("35c", "invoke-static"), 0x72: ("35c", "invoke-interface"),
    0x73: ("10x", "unused-73"), 0x74: ("35c", "invoke-virtual/range"),
    0x75: ("3rc", "invoke-super/range"), 0x76: ("3rc", "invoke-direct/range"),
    0x77: ("3rc", "invoke-static/range"), 0x78: ("3rc", "invoke-interface/range"),
    0x79: ("10x", "unused-79"), 0x7A: ("45cc", "invoke-polymorphic"),
    0x7B: ("4rcc", "invoke-polymorphic/range"), 0x7C: ("45cc", "invoke-custom"),
    0x7D: ("4rcc", "invoke-custom/range"), 0x7E: ("10x", "const-method-handle"),
    0x7F: ("10x", "const-method-type"), 0x80: ("10x", "const-method-handle?new?"),
    0x81: ("10x", "const-method-type?new?"),
    0x90: ("23x", "add-int"), 0x91: ("23x", "sub-int"), 0x92: ("23x", "mul-int"),
    0x93: ("23x", "div-int"), 0x94: ("23x", "rem-int"), 0x95: ("23x", "and-int"),
    0x96: ("23x", "or-int"), 0x97: ("23x", "xor-int"), 0x98: ("23x", "shl-int"),
    0x99: ("23x", "shr-int"), 0x9A: ("23x", "ushr-int"), 0x9B: ("23x", "add-long"),
    0x9C: ("23x", "sub-long"), 0x9D: ("23x", "mul-long"), 0x9E: ("23x", "div-long"),
    0x9F: ("23x", "rem-long"), 0xA0: ("23x", "and-long"), 0xA1: ("23x", "or-long"),
    0xA2: ("23x", "xor-long"), 0xA3: ("23x", "shl-long"), 0xA4: ("23x", "shr-long"),
    0xA5: ("23x", "ushr-long"), 0xA6: ("23x", "add-float"), 0xA7: ("23x", "sub-float"),
    0xA8: ("23x", "mul-float"), 0xA9: ("23x", "div-float"), 0xAA: ("23x", "rem-float"),
    0xAB: ("23x", "add-double"), 0xAC: ("23x", "sub-double"), 0xAD: ("23x", "mul-double"),
    0xAE: ("23x", "div-double"), 0xAF: ("23x", "rem-double"), 0xB0: ("12x", "add-int/2addr"),
    0xB1: ("12x", "sub-int/2addr"), 0xB2: ("12x", "mul-int/2addr"),
    0xB3: ("12x", "div-int/2addr"), 0xB4: ("12x", "rem-int/2addr"),
    0xB5: ("12x", "and-int/2addr"), 0xB6: ("12x", "or-int/2addr"),
    0xB7: ("12x", "xor-int/2addr"), 0xB8: ("12x", "shl-int/2addr"),
    0xB9: ("12x", "shr-int/2addr"), 0xBA: ("12x", "ushr-int/2addr"),
    0xBB: ("12x", "add-long/2addr"), 0xBC: ("12x", "sub-long/2addr"),
    0xBD: ("12x", "mul-long/2addr"), 0xBE: ("12x", "div-long/2addr"),
    0xBF: ("12x", "rem-long/2addr"), 0xC0: ("12x", "and-long/2addr"),
    0xC1: ("12x", "or-long/2addr"), 0xC2: ("12x", "xor-long/2addr"),
    0xC3: ("12x", "shl-long/2addr"), 0xC4: ("12x", "shr-long/2addr"),
    0xC5: ("12x", "ushr-long/2addr"), 0xC6: ("12x", "add-float/2addr"),
    0xC7: ("12x", "sub-float/2addr"), 0xC8: ("12x", "mul-float/2addr"),
    0xC9: ("12x", "div-float/2addr"), 0xCA: ("12x", "rem-float/2addr"),
    0xCB: ("12x", "add-double/2addr"), 0xCC: ("12x", "sub-double/2addr"),
    0xCD: ("12x", "mul-double/2addr"), 0xCE: ("12x", "div-double/2addr"),
    0xCF: ("12x", "rem-double/2addr"), 0xD0: ("22b", "add-int/lit16"),
    0xD1: ("22b", "rsub-int"), 0xD2: ("22b", "mul-int/lit16"), 0xD3: ("22b", "div-int/lit16"),
    0xD4: ("22b", "rem-int/lit16"), 0xD5: ("22b", "and-int/lit16"), 0xD6: ("22b", "or-int/lit16"),
    0xD7: ("22b", "xor-int/lit16"), 0xD8: ("22s", "add-int/lit8"), 0xD9: ("22s", "rsub-int/lit8"),
    0xDA: ("22s", "mul-int/lit8"), 0xDB: ("22s", "div-int/lit8"), 0xDC: ("22s", "rem-int/lit8"),
    0xDD: ("22s", "and-int/lit8"), 0xDE: ("22s", "or-int/lit8"), 0xDF: ("22s", "xor-int/lit8"),
    0xE0: ("22s", "shl-int/lit8"), 0xE1: ("22s", "shr-int/lit8"), 0xE2: ("22s", "ushr-int/lit8"),
    0xE3: ("10x", "unused-e3"), 0xE4: ("10x", "unused-e4"),
    0xE5: ("10x", "unused-e5"), 0xE6: ("10x", "unused-e6"),
    0xE7: ("10x", "unused-e7"), 0xE8: ("10x", "unused-e8"),
    0xE9: ("10x", "unused-e9"), 0xEA: ("10x", "unused-ea"),
    0xEB: ("10x", "unused-eb"), 0xEC: ("10x", "unused-ec"),
    0xED: ("10x", "unused-ed"), 0xEE: ("10x", "unused-ee"),
    0xEF: ("10x", "unused-ef"), 0xF0: ("10x", "unused-f0"),
    0xF1: ("10x", "unused-f1"), 0xF2: ("10x", "unused-f2"),
    0xF3: ("10x", "unused-f3"), 0xF4: ("10x", "unused-f4"),
    0xF5: ("10x", "unused-f5"), 0xF6: ("10x", "unused-f6"),
    0xF7: ("10x", "unused-f7"), 0xF8: ("10x", "unused-f8"),
    0xF9: ("10x", "unused-f9"), 0xFA: ("10x", "unused-fa"),
    0xFB: ("10x", "unused-fb"), 0xFC: ("10x", "unused-fc"),
    0xFD: ("10x", "unused-fd"), 0xFE: ("10x", "unused-fe"), 0xFF: ("10x", "unused-ff"),
}

ACCESS_CLASS = {
    0x1: "public", 0x2: "private", 0x4: "protected", 0x8: "static", 0x10: "final",
    0x20: "synchronized", 0x40: "bridge/volatile", 0x80: "varargs/transient",
    0x100: "native", 0x200: "interface", 0x400: "abstract", 0x800: "strict",
    0x1000: "synthetic", 0x2000: "annotation", 0x4000: "enum",
    0x10000: "constructor", 0x20000: "declared-synchronized",
}
def access_str(flags):
    parts = []
    for bit, name in ACCESS_CLASS.items():
        if flags & bit:
            parts.append(name)
    return " ".join(parts) if parts else "package"

# ---------- DEX 解析器 ----------
class DexFile:
    def __init__(self, data):
        self.data = data
        self.parse_header()
        self.strings = self.parse_strings()
        self.types = self.parse_types()
        self.protos = self.parse_protos()
        self.fields = self.parse_fields()
        self.methods = self.parse_methods()
        self.classes = self.parse_classes()

    def u16(self, off): return struct.unpack_from("<H", self.data, off)[0]
    def u32(self, off): return struct.unpack_from("<I", self.data, off)[0]

    def parse_header(self):
        d = self.data
        self.version = d[4:8].decode("ascii", "replace")
        self.string_ids_size = self.u32(56); self.string_ids_off = self.u32(60)
        self.type_ids_size = self.u32(64);  self.type_ids_off = self.u32(68)
        self.proto_ids_size = self.u32(72); self.proto_ids_off = self.u32(76)
        self.field_ids_size = self.u32(80); self.field_ids_off = self.u32(84)
        self.method_ids_size = self.u32(88); self.method_ids_off = self.u32(92)
        self.class_defs_size = self.u32(96); self.class_defs_off = self.u32(100)

    def parse_strings(self):
        out = []
        for i in range(self.string_ids_size):
            off = self.u32(self.string_ids_off + i * 4)
            # 跳过 uleb 长度
            p = off
            while self.data[p] & 0x80:
                p += 1
            p += 1
            out.append(mutf8_decode(self.data, p))
        return out

    def parse_types(self):
        return [self.strings[self.u32(self.type_ids_off + i * 4)] for i in range(self.type_ids_size)]

    def parse_protos(self):
        out = []
        for i in range(self.proto_ids_size):
            base = self.proto_ids_off + i * 12
            shorty = self.strings[self.u32(base)]
            ret = self.types[self.u32(base + 4)]
            params_off = self.u32(base + 8)
            params = []
            if params_off:
                count = self.u32(params_off)
                for j in range(count):
                    # type_list 的条目是 u16（不是 u32）
                    params.append(self.types[self.u16(params_off + 4 + j * 2)])
            out.append((shorty, ret, params))
        return out

    def parse_fields(self):
        out = []
        for i in range(self.field_ids_size):
            base = self.field_ids_off + i * 8
            cls = self.types[self.u16(base)]
            typ = self.types[self.u16(base + 2)]
            name = self.strings[self.u32(base + 4)]
            out.append((cls, name, typ))
        return out

    def parse_methods(self):
        out = []
        for i in range(self.method_ids_size):
            base = self.method_ids_off + i * 8
            cls = self.types[self.u16(base)]
            proto = self.protos[self.u16(base + 2)]
            name = self.strings[self.u32(base + 4)]
            out.append((cls, name, proto))
        return out

    def parse_classes(self):
        out = []
        for i in range(self.class_defs_size):
            base = self.class_defs_off + i * 32
            cls = self.types[self.u32(base)]
            acc = self.u32(base + 4)
            super_idx = self.u32(base + 8)
            super_cls = self.types[super_idx] if super_idx != 0xFFFFFFFF else None
            iface_off = self.u32(base + 12)
            src = self.u32(base + 16)
            class_data_off = self.u32(base + 24)
            static_off = self.u32(base + 28)
            out.append((cls, acc, super_cls, iface_off, src, class_data_off, static_off))
        return out

    def class_data(self, off):
        """返回 (static_fields, instance_fields, direct_methods, virtual_methods)"""
        if off == 0:
            return [], [], [], []
        data = self.data
        p = off
        sfc, p = uleb128(data, p)
        ifc, p = uleb128(data, p)
        dmc, p = uleb128(data, p)
        vmc, p = uleb128(data, p)
        sf = []
        idx = 0
        for _ in range(sfc):
            d, p = uleb128(data, p); idx += d
            acc, p = uleb128(data, p)
            sf.append((self.fields[idx], acc))
        ifl = []
        idx = 0
        for _ in range(ifc):
            d, p = uleb128(data, p); idx += d
            acc, p = uleb128(data, p)
            ifl.append((self.fields[idx], acc))
        dm = []
        idx = 0
        for _ in range(dmc):
            d, p = uleb128(data, p); idx += d
            acc, p = uleb128(data, p)
            code_off, p = uleb128(data, p)
            dm.append((self.methods[idx], acc, code_off))
        vm = []
        idx = 0
        for _ in range(vmc):
            d, p = uleb128(data, p); idx += d
            acc, p = uleb128(data, p)
            code_off, p = uleb128(data, p)
            vm.append((self.methods[idx], acc, code_off))
        return sf, ifl, dm, vm

    def code_item(self, off):
        """返回 (regs, ins, outs, insns_bytes)"""
        d = self.data
        regs = self.u16(off); ins = self.u16(off + 2); outs = self.u16(off + 4)
        tries = self.u16(off + 6); insns_size = self.u32(off + 12)
        insns_off = off + 16
        return regs, ins, outs, insns_size, insns_off

    # ---------- 指令反汇编 ----------
    def disasm_method(self, code_off):
        regs, ins, outs, insns_size, base = self.code_item(code_off)
        d = self.data
        lines = []
        pc = 0
        while pc < insns_size:
            insn_off = base + pc * 2
            op = d[insn_off]
            spec = INST.get(op)
            if spec is None:
                lines.append("    %04x: unknown-0x%02x" % (pc, op))
                pc += 1
                continue
            fmt, mnem = spec
            # 读取并解码各字段
            words = pc
            if fmt == "10x":
                args = ""
                width = 1
            elif fmt == "12x":
                a = (d[insn_off + 1] >> 4) & 0xF; b = d[insn_off + 1] & 0xF
                args = "v%d, v%d" % (a, b); width = 1
            elif fmt == "11n":
                a = (d[insn_off + 1] >> 4) & 0xF
                b = d[insn_off + 1] & 0xF
                if b & 0x8: b -= 0x10
                args = "v%d, #%d" % (a, b); width = 1
            elif fmt == "11x":
                args = "v%d" % d[insn_off + 1]; width = 1
            elif fmt == "10t":
                b = d[insn_off + 1]
                if b & 0x80: b -= 0x100
                args = ":cond_%d" % (pc + b); width = 1
            elif fmt == "20t":
                b = self.u16(insn_off + 2)
                if b & 0x8000: b -= 0x10000
                args = ":cond_%d" % (pc + b); width = 2
            elif fmt == "21t":
                a = d[insn_off + 1]; b = self.u16(insn_off + 2)
                if b & 0x8000: b -= 0x10000
                args = "v%d, :cond_%d" % (a, pc + b); width = 2
            elif fmt == "21s":
                a = d[insn_off + 1]; b = self.u16(insn_off + 2)
                if b & 0x8000: b -= 0x10000
                args = "v%d, #%d" % (a, b); width = 2
            elif fmt == "21h":
                a = d[insn_off + 1]; b = self.u16(insn_off + 2)
                args = "v%d, #%d" % (a, b << 16); width = 2
            elif fmt == "21c":
                a = d[insn_off + 1]; b = self.u16(insn_off + 2)
                args = "v%d, %s" % (a, self.const_ref(op, b)); width = 2
            elif fmt == "22x":
                a = d[insn_off + 1]; b = self.u16(insn_off + 2)
                args = "v%d, v%d" % (a, b); width = 2
            elif fmt == "22t":
                a = (d[insn_off + 1] >> 4) & 0xF; b = d[insn_off + 1] & 0xF
                c = self.u16(insn_off + 2)
                if c & 0x8000: c -= 0x10000
                args = "v%d, v%d, :cond_%d" % (a, b, pc + c); width = 2
            elif fmt == "22s":
                a = (d[insn_off + 1] >> 4) & 0xF; b = d[insn_off + 1] & 0xF
                c = self.u16(insn_off + 2)
                if c & 0x8000: c -= 0x10000
                args = "v%d, v%d, #%d" % (a, b, c); width = 2
            elif fmt == "22c":
                a = (d[insn_off + 1] >> 4) & 0xF; b = d[insn_off + 1] & 0xF
                c = self.u16(insn_off + 2)
                args = "v%d, v%d, %s" % (a, b, self.const_ref(op, c)); width = 2
            elif fmt == "23x":
                a = d[insn_off + 1]; b = d[insn_off + 2]; c = d[insn_off + 3]
                args = "v%d, v%d, v%d" % (a, b, c); width = 2
            elif fmt == "22b":
                a = d[insn_off + 1]; b = d[insn_off + 2]
                c = d[insn_off + 3]
                if c & 0x80: c -= 0x100
                args = "v%d, v%d, #%d" % (a, b, c); width = 2
            elif fmt == "31t":
                a = d[insn_off + 1]; b = self.u32(insn_off + 2)
                if b & 0x80000000: b -= 0x100000000
                if op == 0x26 or op == 0x2B or op == 0x2C:
                    args = "v%d, +%d (data@%d)" % (a, b, pc + b)
                else:
                    args = ":cond_%d" % (pc + b)
                width = 3
            elif fmt == "31i":
                a = d[insn_off + 1]; b = self.u32(insn_off + 2)
                if b & 0x80000000: b -= 0x100000000
                args = "v%d, #%d" % (a, b); width = 3
            elif fmt == "31c":
                a = d[insn_off + 1]; b = self.u32(insn_off + 2)
                args = "v%d, %s" % (a, self.const_ref(op, b)); width = 3
            elif fmt == "32x":
                a = self.u16(insn_off + 2); b = self.u16(insn_off + 4)
                args = "v%d, v%d" % (a, b); width = 3
            elif fmt == "35c":
                n = (d[insn_off + 1] >> 4) & 0xF
                m = self.u16(insn_off + 2)
                regs4 = self.u16(insn_off + 4)
                regs = []
                regs.append(regs4 & 0xF)
                regs.append((regs4 >> 4) & 0xF)
                regs.append((regs4 >> 8) & 0xF)
                regs.append((regs4 >> 12) & 0xF)
                regs.append(d[insn_off + 1] & 0xF if n == 5 else 0)
                reg_list = ", ".join("v%d" % r for r in regs[:n])
                args = "{%s}, %s" % (reg_list, self.method_ref(m)); width = 3
            elif fmt == "3rc":
                n = d[insn_off + 1]; m = self.u16(insn_off + 2); c = self.u16(insn_off + 4)
                regs = ", ".join("v%d" % (c + i) for i in range(n))
                args = "{%s}, %s" % (regs, self.method_ref(m)); width = 3
            elif fmt == "51l":
                a = d[insn_off + 1]
                lo = self.u32(insn_off + 2); hi = self.u32(insn_off + 6)
                val = (hi << 32) | lo
                args = "v%d, #%d" % (a, val); width = 5
            elif fmt == "45cc":
                args = "polymorphic"; width = 4
            elif fmt == "4rcc":
                args = "polymorphic/range"; width = 4
            else:
                args = "?"; width = 1
            # 跳转目标标签
            lines.append("    %04x: %s %s" % (pc, mnem, args))
            pc += width
        return lines

    def const_ref(self, op, idx):
        if op in (0x1A, 0x1B):
            return '"%s"' % self.strings[idx]
        if op in (0x1C, 0x1F, 0x22, 0x23):
            return self.types[idx]
        if op in (0x24, 0x25):
            return self.methods[idx][0] + "->" + self.methods[idx][1]
        # field 访问 0x52-0x6D（iget/iput/sget/sput）
        if 0x52 <= op <= 0x6D:
            f = self.fields[idx]
            return "%s->%s:%s" % (f[0], f[1], f[2])
        # invoke 0x6E-0x78
        if 0x6E <= op <= 0x78:
            return self.method_ref(idx)
        if op in (0x7E, 0x7F, 0x80, 0x81):
            return "proto/type#" + str(idx)
        return "#%d" % idx

    def method_ref(self, idx):
        cls, name, proto = self.methods[idx]
        params = ",".join(proto[2])
        return "%s->%s(%s)%s" % (cls, name, params, proto[1])

    # ---------- 类级输出 ----------
    def dump_class(self, cls_idx):
        cls, acc, super_cls, iface_off, src, cdata_off, static_off = self.classes[cls_idx]
        out = []
        out.append(".class %s %s" % (access_str(acc), cls))
        if super_cls:
            out.append(".super %s" % super_cls)
        if iface_off:
            cnt = self.u32(iface_off)
            for j in range(cnt):
                out.append(".implements %s" % self.types[self.u32(iface_off + 4 + j * 4)])
        sf, ifl, dm, vm = self.class_data(cdata_off)
        for (field, facc) in sf + ifl:
            out.append(".field %s %s:%s" % (access_str(facc), field[1], field[2]))
        for (meth, macc, code_off) in dm + vm:
            cls_n, name, proto = meth
            params = ", ".join(proto[2])
            out.append("")
            out.append(".method %s %s(%s)%s" % (access_str(macc), name, params, proto[1]))
            if code_off:
                regs, ins, outs, _, _ = self.code_item(code_off)
                out.append("    .registers %d" % regs)
                out.append("    .locals %d" % (regs - ins))
                out.extend(self.disasm_method(code_off))
            else:
                out.append("    (abstract/native)")
            out.append(".end method")
        return "\n".join(out)

    def full_dump(self):
        parts = []
        parts.append("# DEX v%s · 类 %d · 方法 %d · 字符串 %d" % (
            self.version, self.class_defs_size, self.method_ids_size, self.string_ids_size))
        for i in range(self.class_defs_size):
            parts.append("")
            parts.append(self.dump_class(i))
        return "\n".join(parts)


def decompile_dex(data):
    dex = DexFile(data)
    return dex.full_dump()


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else r"E:\Axiom\web\test\samples\dex_out\classes.dex"
    with open(path, "rb") as f:
        data = f.read()
    print(decompile_dex(data))
