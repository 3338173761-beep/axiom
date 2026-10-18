# -*- coding: utf-8 -*-
"""Axiom 自研 Java class 解析器 + JVM 字节码反汇编器（javap 风格）
纯 Python 零依赖，Pyodide(浏览器)/本地通用。覆盖 jar 内多 class。
"""
import struct

# ---------------- JVM 指令表（复用） ----------------
I = {
    0x00: ("nop", 1, 0), 0x01: ("aconst_null", 1, 0), 0x02: ("iconst_m1", 1, 0),
    0x03: ("iconst_0", 1, 0), 0x04: ("iconst_1", 1, 0), 0x05: ("iconst_2", 1, 0),
    0x06: ("iconst_3", 1, 0), 0x07: ("iconst_4", 1, 0), 0x08: ("iconst_5", 1, 0),
    0x09: ("lconst_0", 1, 0), 0x0A: ("lconst_1", 1, 0), 0x0B: ("fconst_0", 1, 0),
    0x0C: ("fconst_1", 1, 0), 0x0D: ("fconst_2", 1, 0), 0x0E: ("dconst_0", 1, 0),
    0x0F: ("dconst_1", 1, 0), 0x10: ("bipush", 2, 1), 0x11: ("sipush", 3, 2),
    0x12: ("ldc", 2, 1), 0x13: ("ldc_w", 3, 3), 0x14: ("ldc2_w", 3, 3),
    0x15: ("iload", 2, 1), 0x16: ("lload", 2, 1), 0x17: ("fload", 2, 1),
    0x18: ("dload", 2, 1), 0x19: ("aload", 2, 1),
    0x1A: ("iload_0", 1, 0), 0x1B: ("iload_1", 1, 0), 0x1C: ("iload_2", 1, 0),
    0x1D: ("iload_3", 1, 0), 0x1E: ("lload_0", 1, 0), 0x1F: ("lload_1", 1, 0),
    0x20: ("lload_2", 1, 0), 0x21: ("lload_3", 1, 0), 0x22: ("fload_0", 1, 0),
    0x23: ("fload_1", 1, 0), 0x24: ("fload_2", 1, 0), 0x25: ("fload_3", 1, 0),
    0x26: ("dload_0", 1, 0), 0x27: ("dload_1", 1, 0), 0x28: ("dload_2", 1, 0),
    0x29: ("dload_3", 1, 0), 0x2A: ("aload_0", 1, 0), 0x2B: ("aload_1", 1, 0),
    0x2C: ("aload_2", 1, 0), 0x2D: ("aload_3", 1, 0), 0x2E: ("iaload", 1, 0),
    0x2F: ("laload", 1, 0), 0x30: ("faload", 1, 0), 0x31: ("daload", 1, 0),
    0x32: ("aaload", 1, 0), 0x33: ("baload", 1, 0), 0x34: ("caload", 1, 0),
    0x35: ("saload", 1, 0), 0x36: ("istore", 2, 1), 0x37: ("lstore", 2, 1),
    0x38: ("fstore", 2, 1), 0x39: ("dstore", 2, 1), 0x3A: ("astore", 2, 1),
    0x3B: ("istore_0", 1, 0), 0x3C: ("istore_1", 1, 0), 0x3D: ("istore_2", 1, 0),
    0x3E: ("istore_3", 1, 0), 0x3F: ("lstore_0", 1, 0), 0x40: ("lstore_1", 1, 0),
    0x41: ("lstore_2", 1, 0), 0x42: ("lstore_3", 1, 0), 0x43: ("fstore_0", 1, 0),
    0x44: ("fstore_1", 1, 0), 0x45: ("fstore_2", 1, 0), 0x46: ("fstore_3", 1, 0),
    0x47: ("dstore_0", 1, 0), 0x48: ("dstore_1", 1, 0), 0x49: ("dstore_2", 1, 0),
    0x4A: ("dstore_3", 1, 0), 0x4B: ("astore_0", 1, 0), 0x4C: ("astore_1", 1, 0),
    0x4D: ("astore_2", 1, 0), 0x4E: ("astore_3", 1, 0), 0x4F: ("iastore", 1, 0),
    0x50: ("lastore", 1, 0), 0x51: ("fastore", 1, 0), 0x52: ("dastore", 1, 0),
    0x53: ("aastore", 1, 0), 0x54: ("bastore", 1, 0), 0x55: ("castore", 1, 0),
    0x56: ("sastore", 1, 0), 0x57: ("pop", 1, 0), 0x58: ("pop2", 1, 0),
    0x59: ("dup", 1, 0), 0x5A: ("dup_x1", 1, 0), 0x5B: ("dup_x2", 1, 0),
    0x5C: ("dup2", 1, 0), 0x5D: ("dup2_x1", 1, 0), 0x5E: ("dup2_x2", 1, 0),
    0x5F: ("swap", 1, 0), 0x60: ("iadd", 1, 0), 0x61: ("ladd", 1, 0),
    0x62: ("fadd", 1, 0), 0x63: ("dadd", 1, 0), 0x64: ("isub", 1, 0),
    0x65: ("lsub", 1, 0), 0x66: ("fsub", 1, 0), 0x67: ("dsub", 1, 0),
    0x68: ("imul", 1, 0), 0x69: ("lmul", 1, 0), 0x6A: ("fmul", 1, 0),
    0x6B: ("dmul", 1, 0), 0x6C: ("idiv", 1, 0), 0x6D: ("ldiv", 1, 0),
    0x6E: ("fdiv", 1, 0), 0x6F: ("ddiv", 1, 0), 0x70: ("irem", 1, 0),
    0x71: ("lrem", 1, 0), 0x72: ("frem", 1, 0), 0x73: ("drem", 1, 0),
    0x74: ("ineg", 1, 0), 0x75: ("lneg", 1, 0), 0x76: ("fneg", 1, 0),
    0x77: ("dneg", 1, 0), 0x78: ("ishl", 1, 0), 0x79: ("lshl", 1, 0),
    0x7A: ("ishr", 1, 0), 0x7B: ("lshr", 1, 0), 0x7C: ("iushr", 1, 0),
    0x7D: ("lushr", 1, 0), 0x7E: ("iand", 1, 0), 0x7F: ("land", 1, 0),
    0x80: ("ior", 1, 0), 0x81: ("lor", 1, 0), 0x82: ("ixor", 1, 0),
    0x83: ("lxor", 1, 0), 0x84: ("iinc", 3, 6), 0x85: ("i2l", 1, 0),
    0x86: ("i2f", 1, 0), 0x87: ("i2d", 1, 0), 0x88: ("l2i", 1, 0),
    0x89: ("l2f", 1, 0), 0x8A: ("l2d", 1, 0), 0x8B: ("f2i", 1, 0),
    0x8C: ("f2l", 1, 0), 0x8D: ("f2d", 1, 0), 0x8E: ("d2i", 1, 0),
    0x8F: ("d2l", 1, 0), 0x90: ("d2f", 1, 0), 0x91: ("i2b", 1, 0),
    0x92: ("i2c", 1, 0), 0x93: ("i2s", 1, 0), 0x94: ("lcmp", 1, 0),
    0x95: ("fcmpl", 1, 0), 0x96: ("fcmpg", 1, 0), 0x97: ("dcmpl", 1, 0),
    0x98: ("dcmpg", 1, 0), 0x99: ("ifeq", 3, 2), 0x9A: ("ifne", 3, 2),
    0x9B: ("iflt", 3, 2), 0x9C: ("ifge", 3, 2), 0x9D: ("ifgt", 3, 2),
    0x9E: ("ifle", 3, 2), 0x9F: ("if_icmpeq", 3, 2), 0xA0: ("if_icmpne", 3, 2),
    0xA1: ("if_icmplt", 3, 2), 0xA2: ("if_icmpge", 3, 2), 0xA3: ("if_icmpgt", 3, 2),
    0xA4: ("if_icmple", 3, 2), 0xA5: ("if_acmpeq", 3, 2), 0xA6: ("if_acmpne", 3, 2),
    0xA7: ("goto", 3, 2), 0xA8: ("jsr", 3, 2), 0xA9: ("ret", 2, 1),
    0xAA: ("tableswitch", -1, 7), 0xAB: ("lookupswitch", -1, 7),
    0xAC: ("ireturn", 1, 0), 0xAD: ("lreturn", 1, 0), 0xAE: ("freturn", 1, 0),
    0xAF: ("dreturn", 1, 0), 0xB0: ("areturn", 1, 0), 0xB1: ("return", 1, 0),
    0xB2: ("getstatic", 3, 3), 0xB3: ("putstatic", 3, 3), 0xB4: ("getfield", 3, 3),
    0xB5: ("putfield", 3, 3), 0xB6: ("invokevirtual", 3, 3), 0xB7: ("invokespecial", 3, 3),
    0xB8: ("invokestatic", 3, 3), 0xB9: ("invokeinterface", 5, 3), 0xBA: ("invokedynamic", 5, 3),
    0xBB: ("new", 3, 3), 0xBC: ("newarray", 2, 1), 0xBD: ("anewarray", 3, 3),
    0xBE: ("arraylength", 1, 0), 0xBF: ("athrow", 1, 0), 0xC0: ("checkcast", 3, 3),
    0xC1: ("instanceof", 3, 3), 0xC2: ("monitorenter", 1, 0), 0xC3: ("monitorexit", 1, 0),
    0xC4: ("wide", -1, 8), 0xC5: ("multianewarray", 4, 4), 0xC6: ("ifnull", 3, 2),
    0xC7: ("ifnonnull", 3, 2), 0xC8: ("goto_w", 5, 4), 0xC9: ("jsr_w", 5, 4),
}

ACC = {
    0x0001: "public", 0x0002: "private", 0x0004: "protected", 0x0008: "static",
    0x0010: "final", 0x0020: "synchronized", 0x0040: "volatile", 0x0080: "transient",
    0x0100: "native", 0x0200: "interface", 0x0400: "abstract", 0x0800: "strictfp",
    0x1000: "synthetic", 0x2000: "annotation", 0x4000: "enum", 0x8000: "module",
}


def accs(flags, is_class=False):
    parts = []
    for b, n in ACC.items():
        if flags & b:
            parts.append(n)
    # 类的 0x20 是 ACC_SUPER（不是 synchronized）
    if is_class and (flags & 0x0020):
        if "synchronized" in parts:
            parts.remove("synchronized")
        parts.append("super")
    return " ".join(parts) if parts else "package"


# ---------------- class 解析器 ----------------
class JavaClass:
    def __init__(self, data):
        self.d = data
        self.pos = 4  # 跳过 magic(CAFEBABE)
        assert data[:4] == b"\xca\xfe\xba\xbe", "不是 Java class 文件"
        self.minor = self.u2()
        self.major = self.u2()
        self.cp = self.parse_cp()
        self.access = self.u2()
        self.this_idx = self.u2()
        self.super_idx = self.u2()
        self.interfaces = [self.u2() for _ in range(self.u2())]
        self.fields = self.parse_members()
        self.methods = self.parse_members()

    def u1(self):
        v = self.d[self.pos]; self.pos += 1
        return v
    def u2(self):
        v = struct.unpack_from(">H", self.d, self.pos)[0]; self.pos += 2
        return v
    def u4(self):
        v = struct.unpack_from(">I", self.d, self.pos)[0]; self.pos += 4
        return v

    def parse_cp(self):
        cp = [None]
        count = self.u2()
        i = 1
        while i < count:
            tag = self.u1()
            if tag == 1:  # UTF8
                ln = self.u2()
                cp.append(("utf8", self.d[self.pos:self.pos + ln].decode("utf-8", "replace")))
                self.pos += ln
            elif tag in (3, 4):
                cp.append(("int/float", self.u4()))
            elif tag in (5, 6):  # long/double 占 2 槽
                cp.append(("long/double", self.u4(), self.u4()))
                cp.append(None)
                i += 1
            elif tag == 7:
                cp.append(("class", self.u2()))
            elif tag == 8:
                cp.append(("string", self.u2()))
            elif tag in (9, 10, 11):
                cp.append(("ref", tag, self.u2(), self.u2()))
            elif tag == 12:
                cp.append(("nat", self.u2(), self.u2()))
            elif tag == 15:
                cp.append(("mh", self.u1(), self.u2()))
            elif tag == 16:
                cp.append(("mt", self.u2()))
            elif tag in (17, 18):
                cp.append(("dyn", tag, self.u2(), self.u2()))
            elif tag == 19:
                cp.append(("module", self.u2()))
            elif tag == 20:
                cp.append(("package", self.u2()))
            else:
                raise ValueError("未知常量池 tag %d @%d" % (tag, self.pos))
            i += 1
        return cp

    def parse_members(self):
        members = []
        for _ in range(self.u2()):
            acc = self.u2()
            name_i = self.u2()
            desc_i = self.u2()
            attrs = self.parse_attrs()
            members.append({"access": acc, "name": self.cp[name_i][1],
                            "desc": self.cp[desc_i][1], "attrs": attrs})
        return members

    def parse_attrs(self):
        attrs = []
        for _ in range(self.u2()):
            name_i = self.u2()
            ln = self.u4()
            name = self.cp[name_i][1]
            info = self.d[self.pos:self.pos + ln]
            self.pos += ln
            attrs.append({"name": name, "info": info})
        return attrs

    def find_attr(self, attrs, name):
        for a in attrs:
            if a["name"] == name:
                return a["info"]
        return None

    def cp_utf8(self, idx):
        try:
            return self.cp[idx][1]
        except Exception:
            return "?"

    def cp_class_name(self, idx):
        try:
            c = self.cp[idx]
            if c[0] == "utf8":
                return c[1]
            if c[0] == "class":
                return self.cp_utf8(c[1])
            return self.cp_utf8(idx)
        except Exception:
            return "#%d" % idx

    def ref_str(self, idx):
        """Fieldref/Methodref/InterfaceMethodref → 类.名称:描述"""
        try:
            _, _, cls_i, nat_i = self.cp[idx]
            cls = self.cp_class_name(cls_i)
            nat = self.cp[nat_i]
            name = self.cp_utf8(nat[1])
            desc = self.cp_utf8(nat[2])
            return "%s.%s:%s" % (cls, name, desc)
        except Exception:
            return "#%d" % idx

    def const_str(self, idx):
        try:
            c = self.cp[idx]
            if c[0] == "string":
                return '"%s"' % self.cp_utf8(c[1])
            if c[0] == "class":
                return "class %s" % self.cp_class_name(c[1])
            if c[0] in ("int/float", "long/double"):
                return str(c[1])
            if c[0] == "ref":
                return self.ref_str(idx)
            if c[0] == "nat":
                return "%s:%s" % (self.cp_utf8(c[1]), self.cp_utf8(c[2]))
            return self.cp_utf8(idx)
        except Exception:
            return "#%d" % idx


def disasm(code, jc):
    out = []
    pc = 0
    n = len(code)
    while pc < n:
        op = code[pc]
        spec = I.get(op)
        if spec is None:
            out.append("    %4d: unknown-0x%02x" % (pc, op))
            pc += 1
            continue
        mnem, length, kind = spec
        if kind == 0:
            out.append("    %4d: %s" % (pc, mnem)); pc += 1
        elif kind == 1:
            out.append("    %4d: %s %d" % (pc, mnem, code[pc + 1])); pc += 2
        elif kind == 2:
            v = struct.unpack_from(">h", code, pc + 1)[0]
            out.append("    %4d: %s %d (-> %d)" % (pc, mnem, v, pc + v)); pc += 3
        elif kind == 3:
            idx = struct.unpack_from(">H", code, pc + 1)[0]
            out.append("    %4d: %s #%d  ; %s" % (pc, mnem, idx, jc.const_str(idx))); pc += 3
        elif kind == 4:
            idx = struct.unpack_from(">H", code, pc + 1)[0]
            dim = code[pc + 3]
            out.append("    %4d: %s #%d dims=%d" % (pc, mnem, idx, dim)); pc += 4
        elif kind == 6:
            iv = code[pc + 1]; cv = code[pc + 2]
            if cv & 0x80: cv -= 0x100
            out.append("    %4d: iinc %d, %d" % (pc, iv, cv)); pc += 3
        elif kind == 7:
            pad = (4 - ((pc + 1) % 4)) % 4
            p = pc + 1 + pad
            if p + 12 > n:
                out.append("    %4d: switch(截断)" % pc); pc += 1; continue
            default = struct.unpack_from(">i", code, p)[0]; p += 4
            lo = struct.unpack_from(">i", code, p)[0]; p += 4
            hi = struct.unpack_from(">i", code, p)[0]; p += 4
            cnt = hi - lo + 1
            labs = []
            for i in range(min(cnt, 100)):
                off = struct.unpack_from(">i", code, p + i * 4)[0]
                labs.append("%d:%d" % (lo + i, pc + off))
            out.append("    %4d: tableswitch default=%d (%s)" % (pc, pc + default, ", ".join(labs[:8])))
            pc = p + cnt * 4
        elif kind == 8:
            op2 = code[pc + 1]
            if op2 == 0x84:
                idx = struct.unpack_from(">H", code, pc + 2)[0]
                cv = struct.unpack_from(">h", code, pc + 4)[0]
                out.append("    %4d: wide iinc %d, %d" % (pc, idx, cv)); pc += 6
            else:
                idx = struct.unpack_from(">H", code, pc + 2)[0]
                out.append("    %4d: wide %s %d" % (pc, I.get(op2, ("?", 0, 0))[0], idx)); pc += 4
        else:
            out.append("    %4d: %s" % (pc, mnem)); pc += 1
    return out


def dump_class(jc, title=""):
    out = []
    if title:
        out.append("# ==== %s ====" % title)
    out.append(".class %s %s" % (accs(jc.access, is_class=True), jc.cp_class_name(jc.this_idx)))
    if jc.super_idx:
        out.append(".super %s" % jc.cp_class_name(jc.super_idx))
    for ix in jc.interfaces:
        out.append(".implements %s" % jc.cp_class_name(ix))
    out.append("")
    out.append("## 常量池字符串")
    seen = 0
    for c in jc.cp:
        if c and c[0] == "utf8" and c[1] and not c[1].startswith(("<", "Code", "LineNumber", "StackMap", "SourceFile", "InnerClasses", "BootstrapMethods", "Exceptions", "Signature", "Deprecated", "Synthetic", "RuntimeVisible", "RuntimeInvisible", "AnnotationDefault", "EnclosingMethod", "ConstantValue", "MethodParameters", "NestHost", "NestMembers")):
            out.append("  %s" % c[1])
            seen += 1
            if seen >= 30:
                break
    out.append("")
    out.append("## 字段")
    for f in jc.fields:
        out.append("  .field %s %s:%s" % (accs(f["access"]), f["name"], f["desc"]))
    out.append("")
    out.append("## 方法")
    for m in jc.methods:
        out.append("")
        out.append(".method %s %s%s" % (accs(m["access"]), m["name"], m["desc"]))
        cinfo = jc.find_attr(m["attrs"], "Code")
        if cinfo:
            max_stack = struct.unpack_from(">H", cinfo, 0)[0]
            max_locals = struct.unpack_from(">H", cinfo, 2)[0]
            code_len = struct.unpack_from(">I", cinfo, 4)[0]
            code = cinfo[8:8 + code_len]
            out.append("  // max_stack=%d max_locals=%d code_len=%d" % (max_stack, max_locals, code_len))
            try:
                out.extend(disasm(code, jc))
            except Exception as e:
                out.append("  // 反汇编失败: %s" % e)
        else:
            out.append("  // abstract/native")
        out.append(".end method")
    return "\n".join(out)


def decompile_java_class(data, filename="input.class"):
    try:
        jc = JavaClass(data)
        return dump_class(jc, filename)
    except Exception as e:
        return "# Java class 解析失败: %s" % e


def decompile_java(data, filename="input.jar"):
    import io, zipfile
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        clazz = [i for i in zf.infolist() if i.filename.endswith(".class")]
        out = ["# JAR 解包：%s · %d 个 .class" % (filename, len(clazz))]
        for ci in clazz[:30]:
            out.append("")
            try:
                out.append(dump_class(JavaClass(zf.read(ci)), ci.filename))
            except Exception as e:
                out.append("# %s 解析失败: %s" % (ci.filename, e))
        if len(clazz) > 30:
            out.append("")
            out.append("（其余 %d 个 class 省略）" % (len(clazz) - 30))
    except Exception as e:
        return "# JAR 解析失败: %s" % e
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    path = sys.argv[1]
    with open(path, "rb") as f:
        data = f.read()
    if path.lower().endswith(".jar"):
        print(decompile_java(data, path))
    else:
        print(decompile_java_class(data, path))
