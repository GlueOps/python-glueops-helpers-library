import zlib

def string_to_crc32(input_string):
    """Compute CRC32 checksum for a given string and return it in hexadecimal format."""
    # Encode the string to bytes
    data_bytes = input_string.encode('utf-8')
    
    # Compute CRC32 checksum
    checksum = zlib.crc32(data_bytes) & 0xffffffff
    
    # Convert checksum to hexadecimal
    return hex(checksum)
