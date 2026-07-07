# -*- coding: utf-8 -*-
"""이미지 삽입·교체·삭제 회귀 — BinData/manifest/pic 일관성, 미변경 엔트리 보존."""
import copy
import os
import struct
import tempfile
import unittest
import zlib

from tests.common import SAMPLE_SPEC, TEMPLATE, K, build_sample, zip_entries
import hwpx_image as HI
from validate import validate_structure


def _png(w, h, color=(255, 0, 0)):
    """외부 의존성 없이 유효한 PNG 생성(테스트용)."""
    def chunk(typ, payload):
        return (struct.pack(">I", len(payload)) + typ + payload
                + struct.pack(">I", zlib.crc32(typ + payload) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(color) * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _spec_with_anchor():
    spec = copy.deepcopy(SAMPLE_SPEC)
    spec["body"].append({"level": "content", "text": "담당자 확인 (직인)"})
    return spec


class TestImageInfo(unittest.TestCase):
    def test_png_size(self):
        self.assertEqual(HI.image_info(_png(12, 34)), ("png", "image/png", 12, 34))

    def test_unknown_rejected(self):
        with self.assertRaises(SystemExit):
            HI.image_info(b"not-an-image")


class TestImageOps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.src = os.path.join(cls.tmp.name, "src.hwpx")
        build_sample(cls.src, _spec_with_anchor())
        cls.png20 = os.path.join(cls.tmp.name, "stamp.png")
        with open(cls.png20, "wb") as f:
            f.write(_png(20, 20))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _add(self, out_name, **kw):
        out = os.path.join(self.tmp.name, out_name)
        parts, _ = K.read_package(self.src)
        orig = dict(parts)
        additions, _msg = HI.op_add(parts, self.png20, "(직인)",
                                    kw.get("replace_anchor", False),
                                    kw.get("width_mm"), kw.get("height_mm"))
        HI._finish(self.src, out, parts, orig, additions=additions)
        return out

    def test_add_registers_bindata_manifest_pic(self):
        out = self._add("added.hwpx", width_mm=20)
        entries = zip_entries(out)
        self.assertIn("BinData/image2.png", entries)
        hpf = entries["Contents/content.hpf"].decode("utf-8")
        self.assertIn('id="image2" href="BinData/image2.png" media-type="image/png"',
                      hpf)
        sec = entries["Contents/section0.xml"].decode("utf-8")
        self.assertIn('binaryItemIDRef="image2"', sec)
        self.assertIn('treatAsChar="1"', sec)
        self.assertEqual(validate_structure(out), [])

    def test_add_preserves_untouched_entries(self):
        out = self._add("preserve.hwpx")
        before, after = zip_entries(self.src), zip_entries(out)
        changed = {n for n in before if before[n] != after.get(n)}
        self.assertEqual(changed, {"Contents/content.hpf", "Contents/section0.xml"})

    def test_add_replace_anchor_removes_text(self):
        out = self._add("replaced.hwpx", replace_anchor=True)
        self.assertNotIn("(직인)", K.extract_text(out))
        self.assertIn('binaryItemIDRef="image2"',
                      zip_entries(out)["Contents/section0.xml"].decode("utf-8"))

    def test_add_missing_anchor_rejected(self):
        parts, _ = K.read_package(self.src)
        with self.assertRaises(SystemExit):
            HI.op_add(parts, self.png20, "(없는앵커)", False, None, None)

    def test_replace_updates_bytes_and_orgsz(self):
        out = self._add("base.hwpx", width_mm=20)
        parts, _ = K.read_package(out)
        orig = dict(parts)
        big = os.path.join(self.tmp.name, "big.png")
        with open(big, "wb") as f:
            f.write(_png(40, 10, color=(0, 0, 255)))
        additions, removals, _msg = HI.op_replace(parts, "image2", big)
        out2 = os.path.join(self.tmp.name, "swapped.hwpx")
        HI._finish(out, out2, parts, orig, additions=additions, removals=removals)
        entries = zip_entries(out2)
        self.assertEqual(entries["BinData/image2.png"], _png(40, 10, color=(0, 0, 255)))
        sec = entries["Contents/section0.xml"].decode("utf-8")
        self.assertIn(f'<hp:orgSz width="{40 * 75}" height="{10 * 75}"', sec)
        self.assertEqual(validate_structure(out2), [])

    def test_replace_template_mi_logo(self):
        parts, _ = K.read_package(TEMPLATE)
        orig = dict(parts)
        additions, removals, _msg = HI.op_replace(parts, "image1", self.png20)
        out = os.path.join(self.tmp.name, "mi.hwpx")
        HI._finish(TEMPLATE, out, parts, orig,
                   additions=additions, removals=removals)
        self.assertEqual(zip_entries(out)["BinData/image1.png"], _png(20, 20))
        self.assertEqual(validate_structure(out), [])

    def test_remove_cleans_pic_manifest_bindata(self):
        out = self._add("toremove.hwpx")
        parts, _ = K.read_package(out)
        orig = dict(parts)
        removals, _msg = HI.op_remove(parts, "image2")
        out2 = os.path.join(self.tmp.name, "removed.hwpx")
        HI._finish(out, out2, parts, orig, removals=removals)
        entries = zip_entries(out2)
        self.assertNotIn("BinData/image2.png", entries)
        self.assertNotIn("image2", entries["Contents/content.hpf"].decode("utf-8"))
        self.assertNotIn('binaryItemIDRef="image2"',
                         entries["Contents/section0.xml"].decode("utf-8"))
        self.assertEqual(validate_structure(out2), [])

    def test_remove_header_logo_needs_force(self):
        parts, _ = K.read_package(TEMPLATE)
        with self.assertRaises(SystemExit):
            HI.op_remove(parts, "image1")
        parts, _ = K.read_package(TEMPLATE)
        orig = dict(parts)
        removals, _msg = HI.op_remove(parts, "image1", force=True)
        out = os.path.join(self.tmp.name, "noforce.hwpx")
        HI._finish(TEMPLATE, out, parts, orig, removals=removals)
        entries = zip_entries(out)
        self.assertNotIn("BinData/image1.png", entries)
        self.assertEqual(validate_structure(out), [])

    def test_list_reports_reference_counts(self):
        out = self._add("list.hwpx")
        parts, _ = K.read_package(out)
        rows = {iid: refs for iid, _h, _m, _s, refs in HI.op_list(parts)}
        self.assertEqual(rows.get("image2"), 1)
        self.assertEqual(rows.get("image1"), 1)  # MI 로고(머리말)


if __name__ == "__main__":
    unittest.main()
