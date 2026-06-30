"""Standalone, dependency-light house sketcher.

No LLM, no NLP, no forms — just typed parameters in, PNG + SVG out. This package
is intentionally decoupled from app.visualization so it can be reasoned about and
run on its own.
"""

from .house_sketch import HouseSketch, SketchValidationError, RoomType

__all__ = ["HouseSketch", "SketchValidationError", "RoomType"]
