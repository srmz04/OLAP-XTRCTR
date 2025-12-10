"""
Input validators for DGIS OLAP Scanner
Provides validation and sanitization for user inputs
"""

import re
from typing import Tuple, List


def validate_selection(input_str: str, max_val: int) -> Tuple[bool, List[int], str]:
    """
    Validate and parse selection input (e.g., "1,2,5-10,15")
    
    Args:
        input_str: User input string
        max_val: Maximum allowed value
    
    Returns:
        Tuple of (is_valid, parsed_indices, error_message)
    """
    if not input_str or not input_str.strip():
        return False, [], "Empty input"
    
    try:
        indices = []
        parts = input_str.replace(' ', '').split(',')
        
        for part in parts:
            if '-' in part:
                start, end = map(int, part.split('-'))
                if start > end:
                    return False, [], f"Invalid range: {start}-{end}"
                indices.extend(range(start, end + 1))
            else:
                indices.append(int(part))
        
        # Validate bounds
        for idx in indices:
            if idx < 1 or idx > max_val:
                return False, [], f"Value {idx} out of range (1-{max_val})"
        
        return True, indices, ""
    except ValueError as e:
        return False, [], f"Invalid input: {e}"


def sanitize_search(text: str) -> Tuple[bool, str, str]:
    """
    Sanitize search text to prevent injection
    
    Args:
        text: Raw search text
    
    Returns:
        Tuple of (is_valid, sanitized_text, error_message)
    """
    if not text:
        return True, "", ""
    
    # Remove potentially dangerous characters for MDX
    dangerous_chars = [';', '--', '/*', '*/', 'EXEC', 'DROP', 'DELETE', 'UPDATE', 'INSERT']
    
    sanitized = text.strip()
    for char in dangerous_chars:
        if char.lower() in sanitized.lower():
            return False, "", f"Forbidden pattern detected: {char}"
    
    # Only allow alphanumeric, spaces, and common punctuation
    sanitized = re.sub(r'[^\w\s\-_áéíóúñÁÉÍÓÚÑ]', '', sanitized)
    
    return True, sanitized, ""
