import argparse
import sys
from src.m1_storage.allocator import GLOBAL_STORAGE

def parse_size(size_str: str) -> int:
    size_str = size_str.upper().strip()
    if size_str.endswith("M"):
        return int(size_str[:-1]) * 1024 * 1024
    elif size_str.endswith("K"):
        return int(size_str[:-1]) * 1024
    elif size_str.endswith("G"):
        return int(size_str[:-1]) * 1024 * 1024 * 1024
    return int(size_str)

def main():
    parser = argparse.ArgumentParser(description="SmartFS Storage Engine CLI")
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    format_parser = subparsers.add_parser("format", help="Format virtual disk image")
    format_parser.add_argument("--disk", default="disk.img", help="Disk file path")
    format_parser.add_argument("--size", default="64M", help="Disk size (e.g., 64M, 16M)")
    format_parser.add_argument("--block-size", type=int, default=4096, help="Block size in bytes")
    format_parser.add_argument("--mode", default="fat", choices=["fat", "inode"], help="Allocation mode")

    args = parser.parse_args()

    if args.command == "format":
        size_bytes = parse_size(args.size)
        sb = GLOBAL_STORAGE.format_disk(
            path=args.disk,
            size_bytes=size_bytes,
            block_size=args.block_size,
            mode=args.mode.upper()
        )
        print(f"[OK] Formatted virtual disk '{args.disk}' ({args.size}, {args.block_size}B blocks, mode={sb.allocation_mode})")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
