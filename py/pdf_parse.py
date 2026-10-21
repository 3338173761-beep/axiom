# -*- coding: utf-8 -*-
"""pdf_parse — 自研 PDF 解析器（零依赖）：
页数 / Info 元数据 / FlateDecode 正文文本流有限提取。
入口：parse_pdf(data) -> str|None
"""
import re
import zlib


def _esc(s):
    return (s.replace(b"\\(", b"(").replace(b"\\)", b")")
             .replace(b"\\\\", b"\\").replace(b"\\n", b"\n").replace(b"\\r", b"\r"))


def parse_pdf(data):
    if data[:5] != b"%PDF-":
        return None
    ver = data[5:8].decode("latin1", "replace")
    out = ["PDF 文档（版本 %s）" % ver, "大小: %d 字节" % len(data)]

    pages = 0
    info = {}
    text_parts = []
    font_enc = False

    # 对象扫描：按 "N 0 obj ... endobj" 切段（stream 按 /Length 截取，不依赖 endstream 文本，
    # 避免压缩流内偶然出现 endstream 字节序列导致提前截断）
    for mo in re.finditer(rb"(\d+) 0 obj", data):
        start = mo.end()
        em = re.search(rb"endobj", data[start:])
        if not em:
            break
        seg = data[start:start + em.start()]
        # 字典 << >>
        dct = b""
        di = seg.find(b"<<")
        if di >= 0:
            depth = 0
            i = di
            while i < len(seg):
                if seg[i:i + 2] == b"<<":
                    depth += 1
                    i += 2
                elif seg[i:i + 2] == b">>":
                    depth -= 1
                    if depth == 0:
                        dct = seg[di:i + 2]
                        break
                    i += 2
                else:
                    i += 1
        # stream
        stm = b""
        si = seg.find(b"stream")
        if si >= 0:
            rest = seg[si + 6:]
            if rest[:2] == b"\r\n":
                rest = rest[2:]
            elif rest[:1] in (b"\r", b"\n"):
                rest = rest[1:]
            mlen = re.search(rb"/Length\s+(\d+)", dct)
            slen = int(mlen.group(1)) if mlen else None
            if slen is not None:
                stm = rest[:slen]
            else:
                ei = rest.find(b"endstream")
                stm = rest[:ei] if ei >= 0 else rest

        try:
            d = dct.decode("latin1")
        except Exception:
            d = ""
        cm = re.search(r"/Count\s+(\d+)", d)
        if cm and "/Pages" in d:
            pages = max(pages, int(cm.group(1)))
        if re.search(r"/Type\s*/Page[^s]", d):
            pages = max(pages, 1)
        for key, label in (("Title", "标题"), ("Author", "作者"), ("Subject", "主题"),
                           ("Keywords", "关键词"), ("Creator", "创建程序"), ("Producer", "生产者")):
            m = re.search(r"/%s\s*\(([^()\\]*(?:\\.[^()\\]*)*)\)" % key, d)
            if m:
                info[label] = _esc(m.group(1)).decode("latin1", "replace")
                break
        if stm:
            try:
                dec = zlib.decompress(stm)
                font_enc = font_enc or (b"/Font" in dct and b"Identity" in dct)
            except Exception:
                dec = None
            if dec:
                t = bytearray()
                for mt in re.finditer(rb"\(([^()\\]*(?:\\.[^()\\]*)*)\)\s*Tj", dec):
                    t += _esc(mt.group(1))
                for mt in re.finditer(rb"\[(.*?)\]\s*TJ", dec, re.S):
                    for st2 in re.finditer(rb"\(([^()\\]*(?:\\.[^()\\]*)*)\)", mt.group(1)):
                        t += _esc(st2.group(1))
                    t += b" "
                if t:
                    text_parts.append(bytes(t).decode("latin1", "replace"))

    out.append("页数: %d" % pages)
    for k, v in info.items():
        out.append("%s: %s" % (k, v))
    body = "".join(text_parts)
    if body:
        out.append("提取文本（有限）: " + body[:600] + (" …" if len(body) > 600 else ""))
    elif font_enc:
        out.append("正文文本流：使用自定义字体编码，文本无法直接还原（可识别结构/元数据）")
    else:
        out.append("正文文本流：未提取到可解码文本（可能为压缩变体或图像型 PDF）")
    return "\n".join(out)
