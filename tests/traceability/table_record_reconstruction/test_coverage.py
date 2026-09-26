"""Restricted v14 record repair, offline only.

@covers AC-1701 — unchanged candidates/rejections, real-v13 seam, no filename/gold inference
@covers AC-1702 — independent labels, generic names, scales, variable record counts, two target rows
@covers AC-1703 — prose/headers/real span/ambiguous continuation/missing start negative fixtures
@covers AC-1704 — immutable OCR tuple and count assertions, shifted rows, strict HTML, escaped text
@covers AC-1705 — NaN/IDs/geometry/record bounds, idempotence, atomic later-row failure
@covers AC-1706 — 20-case frozen replay, three old controls, official scoring seam, regression logs
"""
