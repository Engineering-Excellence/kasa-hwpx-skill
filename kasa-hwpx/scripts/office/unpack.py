#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""unpack.py — HWPX(zip)를 디렉토리로 푼다.  사용법: python3 unpack.py in.hwpx outdir/"""
import sys, zipfile, os
if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    os.makedirs(dst, exist_ok=True)
    with zipfile.ZipFile(src) as z:
        z.extractall(dst)
    print("풀기 완료 →", dst)
