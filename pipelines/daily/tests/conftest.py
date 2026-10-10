# -*- coding: utf-8 -*-
"""pytest 共享配置：让 data/daily 作为包可被导入。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # -> data/