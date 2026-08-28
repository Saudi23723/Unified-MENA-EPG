#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the real orchestrator on a short cycle, on this branch, twice.

Temporary. It patches only the two pacing constants, so everything else —
the generators, the merge, and the commit-and-push in publish() — is the
code that will run on main.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import timedelta
import build_all_epg as B

B.CYCLE = timedelta(minutes=7)
B.PASSES = 2
print(f"patched: PASSES={B.PASSES} CYCLE={B.CYCLE} branch={os.environ.get('GITHUB_REF_NAME')}")
sys.exit(B.main())
