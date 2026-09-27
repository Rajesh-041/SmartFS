class SmartFSError(Exception):
    """Base exception class for SmartFS."""
    pass

class InvalidConfigError(SmartFSError):
    """Raised when configuration is invalid or disk format parameters are incorrect."""
    pass

class CorruptDiskError(SmartFSError):
    """Raised when superblock or disk structures are corrupt (e.g., bad magic number)."""
    pass

class DiskFullError(SmartFSError):
    """Raised when no free blocks remain on disk."""
    pass

class ENOENT(SmartFSError):
    """Raised when a specified file or directory path does not exist."""
    pass

class EEXIST(SmartFSError):
    """Raised when creating a file/directory that already exists."""
    pass

class ENOTEMPTY(SmartFSError):
    """Raised when attempting to remove a non-empty directory."""
    pass

class EUSEREXISTS(SmartFSError):
    """Raised when registering a username that already exists."""
    pass

class EAUTHFAILED(SmartFSError):
    """Raised on authentication failure (invalid username or password)."""
    pass

class ESESSIONEXPIRED(SmartFSError):
    """Raised when a user session has expired."""
    pass

class ESESSIONINVALID(SmartFSError):
    """Raised when a session token is invalid or non-existent."""
    pass

class PermissionDenied(SmartFSError):
    """Raised when an operation is disallowed by RBAC or permission bits."""
    pass

class QuotaExceeded(SmartFSError):
    """Raised when a write operation would exceed the user's storage quota."""
    pass

class EDECRYPTFAILED(SmartFSError):
    """Raised when data decryption fails due to key mismatch or corrupted auth tag."""
    pass

class SimulatedCrashError(SmartFSError):
    """Raised during crash injection testing to simulate process interruption."""
    pass
