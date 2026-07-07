#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hwpx_image.py — 직인/서명 등 이미지 삽입·교체·삭제 (in-place, 서식 보존).

BinData 등록 + content.hpf manifest + <hp:pic> 앵커 삽입을 한 번에 처리한다.
기준 양식의 MI 로고 <hp:pic> 구조에서 추출한 패턴을 사용하며, 미변경 zip 엔트리는
write_package_preserving으로 원본 그대로 유지한다.

사용법:
  python3 hwpx_image.py list    문서.hwpx
  python3 hwpx_image.py add     문서.hwpx --image 직인.png --anchor "(직인)"
                                [--replace-anchor] [--width-mm 20] [--height-mm 20]
                                --output 결과.hwpx
  python3 hwpx_image.py replace 문서.hwpx --id image2 --image 새직인.png --output 결과.hwpx
  python3 hwpx_image.py remove  문서.hwpx --id image2 [--force] --output 결과.hwpx

규칙:
  - add: --anchor 텍스트가 있는 문단의 런 뒤에 글자취급(treatAsChar) 그림을 넣는다.
    --replace-anchor는 앵커 문구를 지우고 그 자리에 넣는다(양식의 "(직인)" 자리 채움).
    크기 미지정 시 원본 픽셀 크기(96dpi 기준), 한 변만 지정하면 비율 유지.
  - replace: manifest id의 BinData 바이트를 교체하고 참조 <hp:pic>의 원본 크기
    메타(orgSz/imgRect/imgClip/imgDim/scaMatrix)를 새 이미지에 맞춘다(표시 크기 유지).
  - remove: 참조 <hp:pic>·manifest 항목·BinData를 제거한다. 머리말/꼬리말 안 그림
    (KASA MI 로고)은 --force 없이 거부한다.
  - 지원 형식: png/jpg/gif/bmp.
"""
import argparse
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kasa_lib as K  # noqa: E402

HPF = "Contents/content.hpf"
MM = 7200 / 25.4        # HWPUNIT per mm
PX = 7200 // 96         # HWPUNIT per pixel(96dpi) = 75
_PIC_RE = re.compile(r"<hp:pic\b.*?</hp:pic>", re.S)
_T_RE = re.compile(r"<hp:t(?:\s[^>]*)?>(.*?)</hp:t>", re.S)


def image_info(data):
    """(확장자, media-type, 가로px, 세로px) — png/jpg/gif/bmp 헤더 파싱."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", data[16:24])
        return "png", "image/png", w, h
    if data[:3] == b"\xff\xd8\xff":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                          0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return "jpg", "image/jpeg", w, h
            if 0xD0 <= marker <= 0xD9 or marker == 0x01:
                i += 2
                continue
            i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
        raise SystemExit("JPEG 크기 정보를 찾을 수 없습니다.")
    if data[:6] in (b"GIF87a", b"GIF89a"):
        w, h = struct.unpack("<HH", data[6:10])
        return "gif", "image/gif", w, h
    if data[:2] == b"BM":
        w, h = struct.unpack("<ii", data[18:26])
        return "bmp", "image/bmp", w, abs(h)
    raise SystemExit("지원하지 않는 이미지 형식입니다(png/jpg/gif/bmp).")


def _sections(parts):
    return sorted(n for n in parts if re.match(r"Contents/section\d+\.xml$", n))


def _manifest_items(hpf):
    """[(id, href, media-type)] — BinData 이미지 항목만."""
    out = []
    for m in re.finditer(r"<opf:item\b[^>]*/>", hpf):
        tag = m.group(0)
        iid = re.search(r'\bid="([^"]+)"', tag)
        href = re.search(r'\bhref="([^"]+)"', tag)
        mt = re.search(r'\bmedia-type="([^"]+)"', tag)
        if iid and href and href.group(1).startswith("BinData/"):
            out.append((iid.group(1), href.group(1), mt.group(1) if mt else ""))
    return out


def _next_slot(parts, hpf, ext):
    """미사용 (manifest id, BinData href) 쌍을 찾는다."""
    used = {int(n) for n in re.findall(r'\bid="image(\d+)"', hpf)}
    used |= {int(n) for p in parts
             for n in re.findall(r"BinData/image(\d+)\.", p)}
    n = max(used, default=0) + 1
    return f"image{n}", f"BinData/image{n}.{ext}"


def _ref_count(parts, item_id):
    return sum(parts[n].decode("utf-8", "ignore").count(
        f'binaryItemIDRef="{item_id}"') for n in _sections(parts))


def _hf_spans(sec):
    return [(m.start(), m.end()) for m in
            re.finditer(r"<hp:(header|footer)\b.*?</hp:\1>", sec, re.S)]


def _strip_para_lineseg(sec, pos):
    """pos를 품은(가장 안쪽) 문단의 줄위치 캐시를 제거해 한글이 재계산하게 한다."""
    s = sec.rfind("<hp:p ", 0, pos)
    e = sec.find("</hp:p>", pos)
    if s == -1 or e == -1:
        return sec
    e += len("</hp:p>")
    block, _ = K.strip_linesegarray(sec[s:e])
    return sec[:s] + block + sec[e:]


def make_pic(item_id, org_w, org_h, cur_w, cur_h, z_order):
    """기준 양식 MI 로고에서 추출한 패턴의 글자취급(treatAsChar) 인라인 그림."""
    sx, sy = cur_w / org_w, cur_h / org_h
    return (
        f'<hp:pic id="{K.next_id()}" zOrder="{z_order}" numberingType="PICTURE" '
        f'textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" '
        f'dropcapstyle="None" href="" groupLevel="0" instid="{K.next_id()}" '
        f'reverse="0">'
        f'<hp:offset x="0" y="0"/>'
        f'<hp:orgSz width="{org_w}" height="{org_h}"/>'
        f'<hp:curSz width="{cur_w}" height="{cur_h}"/>'
        f'<hp:flip horizontal="0" vertical="0"/>'
        f'<hp:rotationInfo angle="0" centerX="{cur_w // 2}" centerY="{cur_h // 2}" '
        f'rotateimage="1"/>'
        f'<hp:renderingInfo>'
        f'<hc:transMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
        f'<hc:scaMatrix e1="{sx:.6f}" e2="0" e3="0" e4="0" e5="{sy:.6f}" e6="0"/>'
        f'<hc:rotMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
        f'</hp:renderingInfo>'
        f'<hc:img binaryItemIDRef="{item_id}" bright="0" contrast="0" '
        f'effect="REAL_PIC" alpha="0"/>'
        f'<hp:imgRect><hc:pt0 x="0" y="0"/><hc:pt1 x="{org_w}" y="0"/>'
        f'<hc:pt2 x="{org_w}" y="{org_h}"/><hc:pt3 x="0" y="{org_h}"/></hp:imgRect>'
        f'<hp:imgClip left="0" right="{org_w}" top="0" bottom="{org_h}"/>'
        f'<hp:inMargin left="0" right="0" top="0" bottom="0"/>'
        f'<hp:imgDim dimwidth="{org_w}" dimheight="{org_h}"/>'
        f'<hp:effects/>'
        f'<hp:sz width="{cur_w}" widthRelTo="ABSOLUTE" height="{cur_h}" '
        f'heightRelTo="ABSOLUTE" protect="0"/>'
        f'<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" '
        f'allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="PARA" '
        f'vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
        f'<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
        f'<hp:shapeComment>그림</hp:shapeComment>'
        f'</hp:pic>')


def op_list(parts):
    hpf = parts[HPF].decode("utf-8")
    rows = []
    for iid, href, mtype in _manifest_items(hpf):
        size = len(parts.get(href, b""))
        rows.append((iid, href, mtype, size, _ref_count(parts, iid)))
    return rows


def op_add(parts, image_path, anchor, replace_anchor, width_mm, height_mm):
    """앵커 문단에 이미지 삽입. 반환: (additions, 안내문)."""
    with open(image_path, "rb") as f:
        data = f.read()
    ext, mtype, pw, ph = image_info(data)
    if pw <= 0 or ph <= 0:
        raise SystemExit("이미지 크기를 읽을 수 없습니다.")
    hpf = parts[HPF].decode("utf-8")
    item_id, href = _next_slot(parts, hpf, ext)

    org_w, org_h = pw * PX, ph * PX
    if width_mm and height_mm:
        cur_w, cur_h = round(width_mm * MM), round(height_mm * MM)
    elif width_mm:
        cur_w = round(width_mm * MM)
        cur_h = round(cur_w * org_h / org_w)
    elif height_mm:
        cur_h = round(height_mm * MM)
        cur_w = round(cur_h * org_w / org_h)
    else:
        cur_w, cur_h = org_w, org_h

    # 앵커 텍스트가 든 <hp:t> 탐색(문서 순서 첫 매칭)
    hit = None
    for name in _sections(parts):
        sec = parts[name].decode("utf-8")
        for m in _T_RE.finditer(sec):
            if anchor in m.group(1):
                hit = (name, sec, m)
                break
        if hit:
            break
    if not hit:
        raise SystemExit(f"앵커 텍스트 {anchor!r}를 찾을 수 없습니다 — "
                         f"extract_text.py로 원문 표기를 확인하세요.")
    name, sec, m = hit

    run_s = sec.rfind("<hp:run", 0, m.start())
    run_e = sec.find("</hp:run>", m.end())
    if run_s == -1 or run_e == -1:
        raise SystemExit("앵커 런 구조를 해석할 수 없습니다.")
    run_e += len("</hp:run>")
    cp = re.search(r'charPrIDRef="(\d+)"', sec[run_s:m.start()])
    z = max((int(v) for n2 in _sections(parts)
             for v in re.findall(r'zOrder="(\d+)"',
                                 parts[n2].decode("utf-8", "ignore"))),
            default=-1) + 1
    pic_run = (f'<hp:run charPrIDRef="{cp.group(1) if cp else "0"}">'
               f'{make_pic(item_id, org_w, org_h, cur_w, cur_h, z)}</hp:run>')

    if replace_anchor:
        t_new = m.group(0).replace(anchor, "", 1)
        sec = sec[:m.start()] + t_new + sec[m.end():]
        run_e += len(t_new) - len(m.group(0))
    sec = sec[:run_e] + pic_run + sec[run_e:]
    sec = _strip_para_lineseg(sec, run_e)
    parts[name] = sec.encode("utf-8")

    item = (f'<opf:item id="{item_id}" href="{href}" media-type="{mtype}" '
            f'isEmbeded="1"/>')
    parts[HPF] = hpf.replace("</opf:manifest>",
                             item + "</opf:manifest>", 1).encode("utf-8")
    return {href: data}, (f"{item_id} 삽입({pw}×{ph}px → "
                          f"{cur_w / MM:.1f}×{cur_h / MM:.1f}mm, 앵커 {anchor!r})")


def _update_pic_geometry(pic, org_w, org_h):
    """교체된 이미지의 원본 크기 메타를 갱신(표시 크기 hp:sz는 유지)."""
    cw = int(re.search(r'<hp:sz width="(\d+)"', pic).group(1))
    ch = int(re.search(r'<hp:sz width="\d+"[^>]*\bheight="(\d+)"', pic).group(1))
    pic = re.sub(r'<hp:orgSz width="\d+" height="\d+"',
                 f'<hp:orgSz width="{org_w}" height="{org_h}"', pic)
    pic = re.sub(r"<hp:imgRect>.*?</hp:imgRect>",
                 f'<hp:imgRect><hc:pt0 x="0" y="0"/><hc:pt1 x="{org_w}" y="0"/>'
                 f'<hc:pt2 x="{org_w}" y="{org_h}"/><hc:pt3 x="0" y="{org_h}"/>'
                 f"</hp:imgRect>", pic, flags=re.S)
    pic = re.sub(r"<hp:imgClip\b[^/]*/>",
                 f'<hp:imgClip left="0" right="{org_w}" top="0" '
                 f'bottom="{org_h}"/>', pic)
    pic = re.sub(r"<hp:imgDim\b[^/]*/>",
                 f'<hp:imgDim dimwidth="{org_w}" dimheight="{org_h}"/>', pic)
    pic = re.sub(r'<hc:scaMatrix e1="[^"]*"([^/]*)\be5="[^"]*"',
                 f'<hc:scaMatrix e1="{cw / org_w:.6f}"\\1e5="{ch / org_h:.6f}"',
                 pic)
    return pic


def op_replace(parts, item_id, image_path):
    """BinData 바이트 교체 + 참조 pic 크기 메타 갱신. 반환: (additions, removals, 안내문)."""
    with open(image_path, "rb") as f:
        data = f.read()
    ext, mtype, pw, ph = image_info(data)
    hpf = parts[HPF].decode("utf-8")
    entry = next((it for it in _manifest_items(hpf) if it[0] == item_id), None)
    if entry is None:
        raise SystemExit(f"manifest에 {item_id!r}가 없습니다(list로 확인).")
    _, href, _ = entry
    additions, removals = {}, set()
    if href.rsplit(".", 1)[-1].lower() == ext:
        parts[href] = data
    else:  # 형식이 바뀌면 href/media-type도 갱신(참조 id는 그대로)
        new_href = href.rsplit(".", 1)[0] + "." + ext
        removals.add(href)
        parts.pop(href, None)
        additions[new_href] = data
        hpf = hpf.replace(f'href="{href}"', f'href="{new_href}"')
        hpf = re.sub(rf'(<opf:item id="{item_id}"[^>]*media-type=")[^"]*(")',
                     rf"\g<1>{mtype}\g<2>", hpf)
        parts[HPF] = hpf.encode("utf-8")
    org_w, org_h = pw * PX, ph * PX
    n_pics = 0
    for name in _sections(parts):
        sec = parts[name].decode("utf-8")
        out, last = [], 0
        for m in _PIC_RE.finditer(sec):
            out.append(sec[last:m.start()])
            pic = m.group(0)
            if f'binaryItemIDRef="{item_id}"' in pic:
                pic = _update_pic_geometry(pic, org_w, org_h)
                n_pics += 1
            out.append(pic)
            last = m.end()
        out.append(sec[last:])
        new = "".join(out)
        if new != sec:
            parts[name] = new.encode("utf-8")
    return additions, removals, (f"{item_id} 교체({pw}×{ph}px, "
                                 f"참조 pic {n_pics}개 크기 메타 갱신)")


def op_remove(parts, item_id, force=False):
    """참조 pic·manifest·BinData 제거. 반환: (removals, 안내문)."""
    hpf = parts[HPF].decode("utf-8")
    entry = next((it for it in _manifest_items(hpf) if it[0] == item_id), None)
    if entry is None:
        raise SystemExit(f"manifest에 {item_id!r}가 없습니다(list로 확인).")
    _, href, _ = entry
    n_removed = 0
    for name in _sections(parts):
        sec = parts[name].decode("utf-8")
        hf = _hf_spans(sec)
        out, last, positions = [], 0, []
        for m in _PIC_RE.finditer(sec):
            pic = m.group(0)
            if f'binaryItemIDRef="{item_id}"' not in pic:
                continue
            if "<hp:pic" in pic[len("<hp:pic"):]:
                raise SystemExit("remove: 중첩 개체를 품은 그림은 제거할 수 없습니다.")
            if not force and any(s <= m.start() and m.end() <= e for s, e in hf):
                raise SystemExit(f"remove: {item_id}는 머리말/꼬리말 안 그림입니다"
                                 f"(KASA MI 로고 보호) — 의도가 확실하면 --force.")
            out.append(sec[last:m.start()])
            last = m.end()
            positions.append(m.start())
            n_removed += 1
        if not positions:
            continue
        out.append(sec[last:])
        sec = "".join(out)
        for pos in reversed(positions):
            sec = _strip_para_lineseg(sec, min(pos, len(sec) - 1))
        parts[name] = sec.encode("utf-8")
    hpf, _ = re.subn(rf'<opf:item id="{item_id}"[^>]*/>', "", hpf)
    parts[HPF] = hpf.encode("utf-8")
    parts.pop(href, None)
    return {href}, f"{item_id} 제거(pic {n_removed}개, {href})"


def _finish(input_path, output_path, parts, orig, additions=None, removals=None):
    changed = {n: d for n, d in parts.items() if n in orig and orig[n] != d}
    K.write_package_preserving(input_path, output_path, changed,
                               additions=additions, removals=removals)
    K.fix_namespaces(output_path)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="HWPX 이미지(직인/서명) 삽입·교체·삭제")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ls = sub.add_parser("list", help="이미지 manifest·참조 수 나열")
    ls.add_argument("input")

    ad = sub.add_parser("add", help="앵커 문단에 이미지 삽입")
    ad.add_argument("input")
    ad.add_argument("--image", required=True, help="이미지 파일(png/jpg/gif/bmp)")
    ad.add_argument("--anchor", required=True, help="삽입 위치 문단의 텍스트")
    ad.add_argument("--replace-anchor", action="store_true",
                    help="앵커 문구를 지우고 그 자리에 삽입(예: '(직인)' 채움)")
    ad.add_argument("--width-mm", type=float, help="표시 가로(mm)")
    ad.add_argument("--height-mm", type=float, help="표시 세로(mm, 한 변만 주면 비율 유지)")
    ad.add_argument("--output", required=True)

    rp = sub.add_parser("replace", help="BinData 이미지 교체(직인 갱신 등)")
    rp.add_argument("input")
    rp.add_argument("--id", required=True, help="manifest id(예: image1)")
    rp.add_argument("--image", required=True)
    rp.add_argument("--output", required=True)

    rm = sub.add_parser("remove", help="이미지 제거(pic+manifest+BinData)")
    rm.add_argument("input")
    rm.add_argument("--id", required=True)
    rm.add_argument("--force", action="store_true",
                    help="머리말/꼬리말 안 그림(MI 로고)도 제거")
    rm.add_argument("--output", required=True)

    a = ap.parse_args()
    parts, _ = K.read_package(a.input)
    orig = dict(parts)

    if a.cmd == "list":
        rows = op_list(parts)
        if not rows:
            print("이미지 없음")
        for iid, href, mtype, size, refs in rows:
            print(f"{iid}: {href} ({mtype}, {size:,}바이트, 참조 {refs}곳)")
        return
    if a.cmd == "add":
        additions, msg = op_add(parts, a.image, a.anchor, a.replace_anchor,
                                a.width_mm, a.height_mm)
        _finish(a.input, a.output, parts, orig, additions=additions)
    elif a.cmd == "replace":
        additions, removals, msg = op_replace(parts, a.id, a.image)
        _finish(a.input, a.output, parts, orig,
                additions=additions, removals=removals)
    else:  # remove
        removals, msg = op_remove(parts, a.id, force=a.force)
        _finish(a.input, a.output, parts, orig, removals=removals)
    print(f"{msg} → {a.output}")


if __name__ == "__main__":
    main()
