"""
Utility functions for parsing and formatting tags.
"""
from typing import List


def parse_tags(tags_str: str) -> List[str]:
    """
    Parse a comma-separated string of tags into a list.
    
    Args:
        tags_str: Comma-separated tag string (e.g., "python, fastapi, web")
    
    Returns:
        List of cleaned tag strings with whitespace removed
    
    Examples:
        >>> parse_tags("python, fastapi, web")
        ['python', 'fastapi', 'web']
        >>> parse_tags("")
        []
        >>> parse_tags("  tag1  ,  tag2  ")
        ['tag1', 'tag2']
    """
    if not tags_str or not tags_str.strip():
        return []
    
    return [tag.strip() for tag in tags_str.split(',') if tag.strip()]


def join_tags(tags_list: List[str]) -> str:
    """
    Join a list of tags into a comma-separated string.
    
    Args:
        tags_list: List of tag strings
    
    Returns:
        Comma-separated string of tags
    
    Examples:
        >>> join_tags(['python', 'fastapi', 'web'])
        'python, fastapi, web'
        >>> join_tags([])
        ''
        >>> join_tags(['single'])
        'single'
    """
    if not tags_list:
        return ""
    
    return ", ".join(tag.strip() for tag in tags_list if tag.strip())
