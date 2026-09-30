#!/usr/bin/env bash
set -e

cd /tmp/xv6-riscv
cp /mnt/c/Users/imjar/SmartFS/smartfs_xv6.c user/smartfs.c

python3 - <<'PY'
from pathlib import Path
p = Path('/tmp/xv6-riscv/Makefile')
text = p.read_text()
if '$U/_smartfs\\' not in text:
    old = '\t$U/_sync\\\n\nfs.img:'
    new = '\t$U/_sync\\\n\t$U/_smartfs\\\n\nfs.img:'
    if old not in text:
        raise SystemExit('Expected UPROGS block not found')
    text = text.replace(old, new, 1)
    p.write_text(text)
PY

grep -n '_smartfs' /tmp/xv6-riscv/Makefile
make
