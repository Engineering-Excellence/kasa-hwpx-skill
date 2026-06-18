#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pack.py — 디렉토리를 HWPX로 묶는다(mimetype 무압축·선두).  사용법: python3 pack.py dir/ out.hwpx"""
import sys, zipfile, os
if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    names = []
    for root, _, files in os.walk(src):
        for f in files:
            full = os.path.join(root, f)
            names.append((full, os.path.relpath(full, src).replace(os.sep, "/")))
    names.sort(key=lambda x: (x[1] != "mimetype", x[1]))
    with zipfile.ZipFile(dst, "w") as z:
        for full, rel in names:
            data = open(full, "rb").read()
            if rel == "mimetype":
                zi = zipfile.ZipInfo("mimetype"); zi.compress_type = zipfile.ZIP_STORED
                z.writestr(zi, data)
            else:
                z.writestr(rel, data, zipfile.ZIP_DEFLATED)
    print("묶기 완료 →", dst)
