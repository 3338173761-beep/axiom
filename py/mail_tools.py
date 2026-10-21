# -*- coding: utf-8 -*-
"""mail_tools — 邮件 / 日历 / 通讯录解析（零依赖，Pyodide 标准库）：
  eml / mbox / emlx / ics / vcf
入口：parse_mail(data, filename) -> str|None
"""
import io
import re
import email
from email import policy


def _eml_parse(raw):
    msg = email.message_from_bytes(raw, policy=policy.default)
    out = []
    for k in ("From", "To", "Cc", "Subject", "Date"):
        v = msg.get(k)
        if v:
            out.append("%s: %s" % (k, str(v)))
    body = None
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and body is None:
                try:
                    body = part.get_content().strip()
                except Exception:
                    body = None
    else:
        try:
            body = msg.get_content().strip()
        except Exception:
            body = None
    if body:
        out.append("\n---- 正文 ----\n" + body[:4000])
    return "\n".join(out) if out else None


def parse_eml(data):
    r = _eml_parse(data)
    if r:
        return "eml 邮件\n" + r
    return None


def parse_mbox(data):
    """mbox：按 'From ' 行切分，每封摘要"""
    text = data.decode("utf-8", "replace")
    msgs = re.split(r"\nFrom ", "\n" + text)
    if len(msgs) <= 1:
        return None
    out = ["mbox 邮件存档 · 共 %d 封" % (len(msgs) - 1)]
    for i, m in enumerate(msgs[:50]):
        if not m.strip():
            continue
        hdr = re.search(r"From: ([^\n]+)", m)
        sub = re.search(r"Subject: ([^\n]+)", m)
        dt = re.search(r"Date: ([^\n]+)", m)
        out.append("#%d %s | %s | %s" % (
            i,
            (hdr.group(1).strip() if hdr else "(无发件人)")[:40],
            (sub.group(1).strip() if sub else "(无主题)")[:40],
            (dt.group(1).strip() if dt else "")[:24],
        ))
    if len(msgs) - 1 > 50:
        out.append("… 其余 %d 封省略" % (len(msgs) - 51))
    return "\n".join(out)


def parse_emlx(data):
    """Apple emlx：4 字节邮件长度 + 邮件正文 + 二进制 plist 元数据"""
    if len(data) > 4:
        try:
            size = struct_unpack_le(data[:4])
            if size > 0 and 4 + size <= len(data) and size < len(data):
                r = _eml_parse(data[4:4 + size])
                if r:
                    return "emlx 邮件（Apple Mail）\n" + r
        except Exception:
            pass
    # 无长度头尝试
    r = _eml_parse(data)
    if r:
        return "emlx 邮件（Apple Mail）\n" + r
    return None


def struct_unpack_le(b):
    import struct
    return struct.unpack("<I", b)[0]


def parse_ics(data):
    """iCalendar：VEVENT/VTODO/VALARM 摘要"""
    text = data.decode("utf-8", "replace").replace("\r\n", "\n")
    if "BEGIN:VCALENDAR" not in text.upper():
        return None
    out = ["ics 日历"]
    for comp, label in (("VEVENT", "事件"), ("VTODO", "任务"), ("VALARM", "提醒")):
        blocks = re.findall(r"BEGIN:%s(.*?)END:%s" % (comp, comp), text, re.S)
        if not blocks:
            continue
        out.append("---- %s（%d 条）----" % (label, len(blocks)))
        for b in blocks[:30]:
            def g(k):
                m = re.search(r"^%s[:;](.*)$" % k, b, re.M)
                return m.group(1).strip() if m else ""
            summary = g("SUMMARY") or "(无标题)"
            start = g("DTSTART") or ""
            end = g("DTEND") or ""
            loc = g("LOCATION") or ""
            out.append("- %s | 开始 %s | 结束 %s%s" % (
                summary[:60], start[:19], end[:19], " | 地点 " + loc[:30] if loc else ""))
    return "\n".join(out)


def parse_vcf(data):
    """vCard：姓名/电话/邮箱/组织"""
    text = data.decode("utf-8", "replace").replace("\r\n", "\n")
    cards = re.split(r"(?=BEGIN:VCARD)", text)
    cards = [c for c in cards if "BEGIN:VCARD" in c.upper()]
    if not cards:
        return None
    out = ["vcf 通讯录 · 共 %d 条" % len(cards)]
    for i, c in enumerate(cards[:100]):
        def g(k):
            m = re.search(r"^%s(?:;.*?)?:(.*)$" % k, c, re.M | re.I)
            return m.group(1).strip() if m else ""
        fn = g("FN") or ""
        n = g("N").replace(";", " ").strip()
        tel = g("TEL") or ""
        mail = g("EMAIL") or ""
        org = g("ORG") or ""
        out.append("#%d %s%s | 电话 %s | 邮箱 %s | %s" % (
            i + 1, fn, ("（" + n + "）" if n and not fn else ""),
            tel[:24], mail[:32], org[:24] if org else ""))
    return "\n".join(out)


def parse_mail(data, filename):
    fn = (filename or "").lower()
    for parser, exts in ((parse_eml, (".eml",)), (parse_mbox, (".mbox",)),
                         (parse_emlx, (".emlx",)), (parse_ics, (".ics",)),
                         (parse_vcf, (".vcf",))):
        if fn.endswith(exts):
            r = parser(data)
            if r:
                return r
    for parser in (parse_eml, parse_mbox, parse_emlx, parse_ics, parse_vcf):
        r = parser(data)
        if r:
            return r
    return None


if __name__ == "__main__":
    import sys
    data = open(sys.argv[1], "rb").read()
    print(parse_mail(data, sys.argv[1]))
