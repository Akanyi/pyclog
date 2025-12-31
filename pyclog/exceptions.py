# pyclog/exceptions.py

class ClogError(Exception):
    """Base exception for pyclog operations."""
    pass

class InvalidClogFileError(ClogError):
    """Raised when the file is not a valid .clog file (e.g., magic bytes mismatch)."""
    pass

class UnsupportedCompressionError(ClogError):
    """Raised when an unsupported compression algorithm is encountered."""
    pass

class ClogReadError(ClogError):
    """Raised when an error occurs during reading from a .clog file."""
    pass

class ClogWriteError(ClogError):
    """Raised when an error occurs during writing to a .clog file."""
    pass
