"""
documents/generation/document_styles.py
Visual style constants for generated Word documents (Rule 12).

Plain data (RGB tuples, point sizes, inch margins) so this module has no python-docx
import; docx_generator converts these into docx objects.
"""

from __future__ import annotations

# Colours as (r, g, b).
INK = (0x1A, 0x1A, 0x2E)       # titles / primary headings
SUBHEAD = (0x33, 0x33, 0x55)   # H3
MUTED = (0x88, 0x88, 0x88)     # date line
RULE = (0xCC, 0xCC, 0xCC)      # horizontal rule

# Font sizes (points).
SIZE_TITLE = 20
SIZE_H1 = 15
SIZE_H2 = 13
SIZE_H3 = 11
SIZE_SECTION = 12
SIZE_DATE = 9
SIZE_RULE = 8

# Page margins (inches).
MARGIN_TOP = 1
MARGIN_BOTTOM = 1
MARGIN_LEFT = 1.2
MARGIN_RIGHT = 1.2
