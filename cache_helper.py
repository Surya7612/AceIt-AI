import redis
import json
import logging
from functools import wraps
from datetime import datetime, timedelta

# Initialize Redis client
redis_client = redis.Redis(host='localhost', port=6379, db=0)

def cache_data(key, data, expiry_seconds=3600):
    """Cache data with Redis"""
    try:
        redis_client.setex(key, expiry_seconds, json.dumps(data))
        return True
    except Exception as e:
        logging.error(f"Cache error: {str(e)}")
        return False

def get_cached_data(key):
    """Retrieve cached data"""
    try:
        data = redis_client.get(key)
        return json.loads(data) if data else None
    except Exception as e:
        logging.error(f"Cache retrieval error: {str(e)}")
        return None

def cache_decorator(expiry_seconds=3600):
    """Decorator for caching function results"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create a cache key from function name and arguments
            key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Try to get cached result
            cached_result = get_cached_data(key)
            if cached_result is not None:
                return cached_result
            
            # If not cached, execute function and cache result
            result = func(*args, **kwargs)
            cache_data(key, result, expiry_seconds)
            return result
        return wrapper
    return decorator
