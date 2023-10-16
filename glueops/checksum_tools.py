import zlib
import hashlib

def string_to_crc32(input_string: str) -> str:
    """Compute CRC32 checksum for a given string and return it in hexadecimal format."""
    # Encode the string to bytes
    data_bytes = input_string.encode('utf-8')
    
    # Compute CRC32 checksum
    checksum = zlib.crc32(data_bytes) & 0xffffffff
    
    # Convert checksum to hexadecimal
    return hex(checksum)

def compute_sha224(input_string: str) -> str:
    """Compute SHA224 checksum for a given string and return it in hexadecimal format."""
    
    sha224_hash = hashlib.sha224()
    sha224_hash.update(text.encode('utf-8'))
    return sha224_hash.hexdigest()
