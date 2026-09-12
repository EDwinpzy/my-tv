import sys

def check(path):
    src = open(path, encoding='utf-8').read()
    depth = 0
    line = 1
    in_str = None
    in_lc = False
    i = 0
    while i < len(src):
        c = src[i]
        if c == '\n':
            line += 1
            in_lc = False
            i += 1
            continue
        if in_lc:
            i += 1
            continue
        if in_str:
            if c == '\\':
                i += 2
                continue
            if c == in_str:
                in_str = None
            i += 1
            continue
        if c == '/' and i + 1 < len(src) and src[i+1] == '/':
            in_lc = True
            i += 2
            continue
        if c == '/' and i + 1 < len(src) and src[i+1] == '*':
            j = src.find('*/', i + 2)
            end = j if j > 0 else len(src)
            line += src.count('\n', i, end)
            i = end + 2 if j > 0 else len(src)
            continue
        if c in ('"', "'"):
            in_str = c
            i += 1
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth < 0:
                print(f"{path}: EXTRA }} at line {line}")
                return
        i += 1
    status = 'OK' if depth == 0 else f'UNCLOSED depth={depth}'
    print(f"{path}: {status}")

for p in sys.argv[1:]:
    check(p)
