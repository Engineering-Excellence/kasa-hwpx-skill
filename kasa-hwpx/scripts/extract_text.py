#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_text.py — HWPX에서 텍스트 추출.  사용법: python3 extract_text.py 파일.hwpx"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kasa_lib as K
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    print(K.extract_text(sys.argv[1]))
