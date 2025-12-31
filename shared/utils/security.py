import hashlib
from typing import Union

def generate_hash(data: Union[bytes, str], algorithm: str = "sha256") -> str:
    """
    Generates a deterministic hash for the given data.
    
    Args:
        data: The data to hash (bytes or string).
        algorithm: The hashing algorithm to use (default: sha256).
        
    Returns:
        The hexadecimal hash string.
    """
    # Ensure data is in bytes
    if isinstance(data, str):
        data = data.encode('utf-8')
    
    hash_obj = hashlib.new(algorithm)
    hash_obj.update(data)
    return hash_obj.hexdigest()

def verify_hash(data: Union[bytes, str], expected_hash: str, algorithm: str = "sha256") -> bool:
    """
    Verifies if the data matches the expected hash.
    """
    return generate_hash(data, algorithm) == expected_hash