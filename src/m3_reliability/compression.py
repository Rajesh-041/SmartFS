import zlib

def compress_block(data: bytes) -> bytes:
    """Compresses data using zlib. DEFLATE algorithm."""
    if not data:
        return b""
    return zlib.compress(data)

def decompress_block(data: bytes) -> bytes:
    """Decompresses zlib-compressed data."""
    if not data:
        return b""
    return zlib.decompress(data)
