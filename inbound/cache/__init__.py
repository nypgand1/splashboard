# -*- coding: utf-8 -*-
"""Three orthogonal in-memory caches sharing SingleflightGroup: CatalogCache, FrameStore, LiveCache."""
from inbound.cache.singleflight import SingleflightGroup

__all__ = ['SingleflightGroup']
