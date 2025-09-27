import sys

def main() -> int:
    # Usage: checker in ans out
    if len(sys.argv) != 4:
        print("usage: checker in ans out", file=sys.stderr)
        return 2
    _, _in, _ans, _out = sys.argv
    try:
        with open(_ans, 'rb') as fa, open(_out, 'rb') as fo:
            if fa.read() == fo.read():
                return 0
            return 1
    except Exception as e:
        print(f"checker error: {e}", file=sys.stderr)
        return 3

if __name__ == '__main__':
    raise SystemExit(main())

