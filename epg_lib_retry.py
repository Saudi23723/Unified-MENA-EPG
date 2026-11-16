#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Retry wrapper for EPG generation with exponential backoff.
Provides robust error handling for network and source failures.
"""

import time
import sys
from functools import wraps
from typing import Callable, Any, TypeVar, cast

T = TypeVar('T')

# Retry configuration
MAX_RETRIES = 3
INITIAL_WAIT = 2  # seconds
BACKOFF_FACTOR = 2  # exponential backoff
MAX_WAIT = 30  # seconds

# Timeout configuration
DEFAULT_TIMEOUT = 120  # seconds per request
SCRIPT_TIMEOUT = 600  # seconds per EPG script


def retry_on_failure(max_retries: int = MAX_RETRIES, 
                    initial_wait: int = INITIAL_WAIT,
                    backoff_factor: float = BACKOFF_FACTOR,
                    max_wait: int = MAX_WAIT):
    """
    Decorator for functions that should retry on failure with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        initial_wait: Initial wait time in seconds
        backoff_factor: Multiplier for wait time between retries
        max_wait: Maximum wait time in seconds
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            wait_time = initial_wait
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        print(f"✗ {func.__name__} failed after {max_retries} retries")
                        print(f"  Last error: {str(e)}")
                        raise
                    
                    wait_time = min(wait_time * backoff_factor, max_wait)
                    print(f"⚠ {func.__name__} attempt {attempt + 1} failed: {str(e)}")
                    print(f"  Retrying in {wait_time:.1f} seconds...")
                    time.sleep(wait_time)
            
            if last_exception:
                raise last_exception
            return func(*args, **kwargs)
        
        return cast(Callable[..., T], wrapper)
    return decorator


def get_with_retry(url: str, timeout: int = DEFAULT_TIMEOUT, **kwargs) -> Any:
    """
    Fetch URL with retry logic.
    """
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    
    session = requests.Session()
    retry_strategy = Retry(
        total=MAX_RETRIES,
        backoff_factor=BACKOFF_FACTOR,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    try:
        response = session.get(url, timeout=timeout, **kwargs)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        print(f"✗ Failed to fetch {url}: {str(e)}")
        raise
    finally:
        session.close()


def safe_parse_xml(content: bytes, source_name: str = "XML") -> Any:
    """
    Safely parse XML with error handling.
    """
    import xml.etree.ElementTree as ET
    
    try:
        return ET.fromstring(content)
    except ET.ParseError as e:
        print(f"✗ {source_name} parse error: {str(e)}")
        raise
    except Exception as e:
        print(f"✗ {source_name} error: {str(e)}")
        raise


def validate_xml_health(root: Any, min_channels: int = 1, 
                       min_programs: int = 10) -> bool:
    """
    Validate that XML contains expected data.
    """
    if root.tag != "tv":
        print(f"✗ Invalid root element: {root.tag} (expected 'tv')")
        return False
    
    channels = root.findall("channel")
    programs = root.findall("programme")
    
    if len(channels) < min_channels:
        print(f"✗ Too few channels: {len(channels)} (minimum: {min_channels})")
        return False
    
    if len(programs) < min_programs:
        print(f"✗ Too few programs: {len(programs)} (minimum: {min_programs})")
        return False
    
    print(f"✓ XML health check passed: {len(channels)} channels, {len(programs)} programs")
    return True


if __name__ == "__main__":
    print("EPG Retry Library - Import this module to use retry decorators")
