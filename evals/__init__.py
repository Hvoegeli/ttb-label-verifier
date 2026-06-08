"""Deterministic evaluation corpus for the distilled-spirits rule engine.

This package holds a labeled set of single-mutation "mutant" labels (each a known
deviation from a compliant baseline) plus the expected verdict for each. It is the
CI half of the eval plan: it exercises the rule engine directly with no Claude call,
so it is free, instant, and reproducible. The companion manual eval (real bottle
photos run through the live vision model) tests the extraction step separately.
"""
