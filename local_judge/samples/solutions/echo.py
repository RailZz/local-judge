import sys

def main() -> None:
    data = sys.stdin.buffer.read()
    sys.stdout.buffer.write(data)

if __name__ == "__main__":
    main()

