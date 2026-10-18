"""Fritzing breadboard sketches from code.

Placement is "this pin goes into that hole": hole and pin coordinates come
from the parts' own SVGs, every plug is checked to land on its hole, and the
nets traced through the strips are compared with the schematic. lint checks
the same nets against what Fritzing actually drew.
"""
