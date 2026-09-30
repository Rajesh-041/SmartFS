from pathlib import Path
text = Path('/tmp/xv6-riscv/Makefile').read_text()
for pattern in ['        $U/_sync\\\n', '        $U/_sync\\r\n', 'UPROGS+=', 'UPROGS=\\']:
    print(repr(pattern), pattern in text)
idx = text.find('$U/_sync')
print('IDX', idx)
print(repr(text[idx-40:idx+120]))
