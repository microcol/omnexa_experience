# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt
"""Inject tenant CSS variable overrides on public website pages (see Experience Tenant Theme)."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
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
	logo = row.get("logo") or row.get("logo_url")
	if logo:
		lines.append(f'  --ox-logo-url: url("{logo}");')
	if not lines:
		return ""
	body = "\n".join(lines)
	return f'<style id="omnexa-experience-tenant-theme">:root {{\n{body}\n}}</style>'


def _brand_links_html(row: dict) -> str:
	parts: list[str] = []
	favicon = row.get("favicon") or row.get("favicon_url")
	if favicon:
		u = escape_html(favicon)
		parts.append(f'<link rel="icon" href="{u}">')
	logo = row.get("logo") or row.get("logo_url")
	if logo:
		u = escape_html(logo)
		parts.append(f'<meta property="og:image" content="{u}">')
	return "".join(parts)


def _head_html_for_row(row: dict) -> str:
	style = _style_block_for_row(row)
	links = _brand_links_html(row)
	if not style and not links:
		return ""
	return HEAD_MARKER + links + style


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
	preview = None
	if getattr(frappe.local, "flags", None):
		preview = frappe.local.flags.get("omnexa_experience_theme_preview_row")
	if preview:
		# The preview row is already a safe dict fetched by SQL in before_request hook.
		return preview
	rows = frappe.db.sql(
		"""
		select primary_color, primary_contrast, background_color, surface_color,
			foreground_color, font_stack_for_web, logo, logo_url, favicon, favicon_url
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

	block = _head_html_for_row(row)
	if not block:
		return {}

	head = context.get("head_html") or ""
	if HEAD_MARKER in head:
		return {}

	return {"head_html": head + block}


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=120, seconds=60, methods=["GET"])
def preview_theme_head(theme: str | None = None, company: str | None = None):
	"""Desk helper: return generated theme head HTML for preview before publish."""
	if not theme or not frappe.db.exists("Experience Tenant Theme", theme):
		frappe.throw(_("Theme not found."), frappe.DoesNotExistError, title=_("Theme"))
	if company and not frappe.db.exists("Company", company):
		frappe.throw(_("A valid company is required."), title=_("Theme"))

	row_list = frappe.db.sql(
		"""
		select name, company, primary_color, primary_contrast, background_color, surface_color,
			foreground_color, font_stack_for_web, logo, logo_url, favicon, favicon_url
		from `tabExperience Tenant Theme`
		where name = %(name)s
		limit 1
		""",
		{"name": theme},
		as_dict=True,
	)
	row = row_list[0] if row_list else None
	if not row:
		frappe.throw(_("Theme not found."), frappe.DoesNotExistError, title=_("Theme"))
	if company and row.get("company") != company:
		frappe.throw(_("Theme does not belong to this company."), title=_("Theme"))

	head_html = _head_html_for_row(row)
	return {
		"theme": row["name"],
		"company": row["company"],
		"head_html": head_html,
		"has_tokens": bool(_style_block_for_row(row)),
		"has_brand_assets": bool(_brand_links_html(row)),
	}
