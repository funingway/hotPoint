from hotspot.sources.base import BaseSource, RateLimiter

SOURCE_REGISTRY: dict[str, type[BaseSource]] = {}


def register_source(cls):
    SOURCE_REGISTRY[cls.name] = cls
    return cls
