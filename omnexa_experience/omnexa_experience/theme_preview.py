# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt

from __future__ import annotations

import secrets

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

_PREVIEW_TOKEN_TTL_SECONDS = 10 * 60
_CACHE_PREFIX = "omnexa_experience:theme_preview:"


def _cache_key(token: str) -> str:
	return f"{_CACHE_PREFIX}{token}"


def _read_preview_row(theme: str) -> dict | None:
	rows = frappe.db.sql(
		"""
		select name, company, primary_color, primary_contrast, background_color, surface_color,
			foreground_color, font_stack_for_web, logo, logo_url, favicon, favicon_url
		from `tabExperience Tenant Theme`
		where name=%s
		limit 1
		""",
		(theme,),
		as_dict=True,
	)
	return rows[0] if rows else None


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=60, methods=["POST"])
def create_theme_preview_token(theme: str | None = None, company: str | None = None):
	"""Create a short-lived token to preview a theme on public URLs.

	Requires a logged-in Desk user with permission to read the DocType row.
	"""
	if frappe.session.user == "Guest":
		frappe.throw(_("Login required."), frappe.PermissionError, title=_("Theme"))
	if not theme or not frappe.db.exists("Experience Tenant Theme", theme):
		frappe.throw(_("Theme not found."), frappe.DoesNotExistError, title=_("Theme"))
	if company and not frappe.db.exists("Company", company):
		frappe.throw(_("A valid company is required."), title=_("Theme"))

	row = _read_preview_row(theme)
	if not row:
		frappe.throw(_("Theme not found."), frappe.DoesNotExistError, title=_("Theme"))
	if company and row.get("company") != company:
		frappe.throw(_("Theme does not belong to this company."), title=_("Theme"))

	# Permission check: use standard read permission on this DocType.
	frappe.has_permission("Experience Tenant Theme", ptype="read", doc=frappe.get_doc("Experience Tenant Theme", theme), throw=True)

	token = secrets.token_urlsafe(24)
	frappe.cache().set_value(
		_cache_key(token),
		{"theme": row["name"], "company": row["company"]},
		expires_in_sec=_PREVIEW_TOKEN_TTL_SECONDS,
	)
	return {
		"token": token,
		"ttl_seconds": _PREVIEW_TOKEN_TTL_SECONDS,
		"query": {"ox_theme_preview": row["name"], "ox_preview_token": token},
	}


def before_request_theme_preview():
	"""Enable theme preview for this request if valid query params are present."""
	theme = (frappe.form_dict.get("ox_theme_preview") or "").strip()
	token = (frappe.form_dict.get("ox_preview_token") or "").strip()
	if not theme and not token:
		return
	if not theme or not token:
		frappe.throw(_("Theme preview token required."), frappe.PermissionError, title=_("Theme"))

	payload = frappe.cache().get_value(_cache_key(token)) or {}
	if not payload or payload.get("theme") != theme:
		frappe.throw(_("Invalid or expired theme preview token."), frappe.PermissionError, title=_("Theme"))

	row = _read_preview_row(theme)
	if not row:
		frappe.throw(_("Theme not found."), frappe.DoesNotExistError, title=_("Theme"))

	# Attach row dict to request flags; web_theme.update_website_context will use it.
	if not getattr(frappe.local, "flags", None):
		frappe.local.flags = {}
	frappe.local.flags["omnexa_experience_theme_preview_row"] = row

