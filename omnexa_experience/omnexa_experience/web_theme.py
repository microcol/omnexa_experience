# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt
"""Inject tenant CSS variable overrides on public website pages (see Experience Tenant Theme)."""

from __future__ import annotations

import frappe
from frappe.utils import escape_html

HEAD_MARKER = "<!-- omnexa-experience-tenant-head -->"


def _style_block_for_row(row: dict) -> str:
	lines: list[str] = []
	if row.get("primary_color"):
		lines.append(f"  --ox-primary: {row['primary_color']};")
	if row.get("primary_contrast"):
		lines.append(f"  --ox-primary-contrast: {row['primary_contrast']};")
	if row.get("background_color"):
		lines.append(f"  --ox-bg: {row['background_color']};")
	if row.get("surface_color"):
		lines.append(f"  --ox-surface: {row['surface_color']};")
	if row.get("foreground_color"):
		lines.append(f"  --ox-fg: {row['foreground_color']};")
	if row.get("font_stack_for_web"):
		lines.append(f"  --ox-font-sans: {row['font_stack_for_web']};")
	if row.get("logo_url"):
		lines.append(f'  --ox-logo-url: url("{row["logo_url"]}");')
	if not lines:
		return ""
	body = "\n".join(lines)
	return f'<style id="omnexa-experience-tenant-theme">:root {{\n{body}\n}}</style>'


def _brand_links_html(row: dict) -> str:
	parts: list[str] = []
	if row.get("favicon_url"):
		u = escape_html(row["favicon_url"])
		parts.append(f'<link rel="icon" href="{u}">')
	if row.get("logo_url"):
		u = escape_html(row["logo_url"])
		parts.append(f'<meta property="og:image" content="{u}">')
	return "".join(parts)


def get_active_public_theme_name() -> str | None:
	"""Name of the row with ``apply_to_public_site`` set, if any (most recently modified)."""
	if not frappe.db.table_exists("Experience Tenant Theme"):
		return None
	row = frappe.db.sql(
		"""
		select name from `tabExperience Tenant Theme`
		where ifnull(apply_to_public_site, 0) = 1
		order by modified desc
		limit 1
		""",
		as_dict=False,
	)
	return row[0][0] if row else None


def _get_active_theme_row() -> dict | None:
	if not frappe.db.table_exists("Experience Tenant Theme"):
		return None
	rows = frappe.db.sql(
		"""
		select primary_color, primary_contrast, background_color, surface_color,
			foreground_color, font_stack_for_web, logo_url, favicon_url
		from `tabExperience Tenant Theme`
		where ifnull(apply_to_public_site, 0) = 1
		order by modified desc
		limit 1
		""",
		as_dict=True,
	)
	return rows[0] if rows else None


def update_website_context(context: dict):
	"""Frappe hook: merge token overrides into ``head_html`` (after ``design_tokens.css``)."""
	if getattr(frappe.local, "flags", None) and frappe.local.flags.get("skip_omnexa_experience_theme"):
		return {}

	if not frappe.db.table_exists("Experience Tenant Theme"):
		return {}

	row = _get_active_theme_row()
	if not row:
		return {}

	style = _style_block_for_row(row)
	links = _brand_links_html(row)
	if not style and not links:
		return {}

	head = context.get("head_html") or ""
	if HEAD_MARKER in head:
		return {}

	return {"head_html": head + HEAD_MARKER + links + style}
