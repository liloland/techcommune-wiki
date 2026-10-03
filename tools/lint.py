#!/usr/bin/env python3
"""Pull-request check: validates every page without building the site. Run:  python3 tools/lint.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build  # noqa: E402

if __name__ == '__main__':
    sys.exit(build.main(['--check'] + sys.argv[1:]))
