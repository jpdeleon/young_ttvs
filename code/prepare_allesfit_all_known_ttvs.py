#!/usr/bin/env python
"""
1. read nexsci data
2. get all ttv_flag==1
3. prepare allesfitter args
"""
import sys
from pathlib import Path
import numpy as np
home = Path.home()
sys.path.insert(0, f'{home}/github/research/project/young_ttvs/code')

from utils import *

df = get_nexsci_data()
ttv_hosts = df[df.ttv_flag==1].hostname.unique()
print(ttv_hosts)

outdir = Path(f"{home}/github/research/project/young_ttvs/allesfitter/known_ttvs")
outdir.mkdir(parents=True, exist_ok=True)

fp = outdir.joinpath("ttv_hosts.txt")
np.savetxt(fp, ttv_hosts, fmt="%s")
print(f"saved {fp}")