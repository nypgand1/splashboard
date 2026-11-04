# -*- coding: utf-8 -*-
"""Categorized loggers. Parse gaps stay on synergy.data at DEBUG."""
import logging

budget = logging.getLogger('synergy.live.budget')
auth = logging.getLogger('synergy.live.auth')
build = logging.getLogger('synergy.live.build')
payload = logging.getLogger('synergy.live.payload')
data = logging.getLogger('synergy.data')
unexpected = logging.getLogger('synergy.unexpected')
