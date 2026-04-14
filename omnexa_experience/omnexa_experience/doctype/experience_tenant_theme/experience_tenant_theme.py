# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import validate_url

_HEX6 = re.compile(r"^#[0-9A-Fa-f]{6}$")
_FONT_STACK_SAFE = re.compile(r"^[a-zA-Z0-9, \-\.'\"]{1,200}$")
_UNSAFE_URL_CHARS = re.compile(r'["\'\\<>\n\r]')
_MAX_ASSET_URL_LEN = 2048

# WCAG 2.2 §1.4.11 (non-text): minimum ~3:1 for UI components; we enforce 3:1 when both primary colors are set.
_MIN_PRIMARY_CONTRAST_RATIO = 3.0


def _hex_to_srgb_channels(hex6: str) -> tuple[float, float, float]:
	r = int(hex6[1:3], 16) / 255.0
	g = int(hex6[3:5], 16) / 255.0
	b = int(hex6[5:7], 16) / 255.0
	return r, g, b


def _linearize(channel: float) -> float:
	return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _relative_luminance(hex6: str) -> float:
	r, g, b = _hex_to_srgb_channels(hex6)
	return 0.2126 * _linearize(r) + 0.7152 * _linearize(g) + 0.0722 * _linearize(b)


def _contrast_ratio(fg_hex: str, bg_hex: str) -> float:
	l1 = _relative_luminance(fg_hex)
	l2 = _relative_luminance(bg_hex)
	light, dark = max(l1, l2), min(l1, l2)
	return (light + 0.05) / (dark + 0.05)


def _norm_hex(label: str, value: str | None) -> str | None:
	if not (value or "").strip():
		return None
	v = value.strip()
	if not _HEX6.match(v):
		frappe.throw(_("{0} must be a #RRGGBB hex color.").format(label), title=_("Theme"))
	return v


def _norm_font_stack(value: str | None) -> str | None:
	if not (value or "").strip():
		return None
	v = value.strip()
	if len(v) > 200 or not _FONT_STACK_SAFE.match(v):
		frappe.throw(
			_("Font stack may only contain letters, digits, commas, spaces, hyphens, and quotes (max 200)."),
			title=_("Theme"),
		)
	return v


def _norm_asset_url(label: str, value: str | None) -> str | None:
	if not (value or "").strip():
		return None
	v = value.strip()
	if len(v) > _MAX_ASSET_URL_LEN:
		frappe.throw(
			_("{0} must be at most {1} characters.").format(label, _MAX_ASSET_URL_LEN),
			title=_("Theme"),
		)
	if _UNSAFE_URL_CHARS.search(v):
		frappe.throw(
			_("{0} must not contain quotes, backslashes, angle brackets, or newlines.").format(label),
			title=_("Theme"),
		)
	if not validate_url(v, valid_schemes=("https", "http")):
		frappe.throw(_("{0} must be a valid http(s) URL.").format(label), title=_("Theme"))
	return v


class ExperienceTenantTheme(Document):
	def validate(self):
		self.primary_color = _norm_hex(_("Primary"), self.primary_color)
		self.primary_contrast = _norm_hex(_("Primary contrast"), self.primary_contrast)
		self.background_color = _norm_hex(_("Background"), self.background_color)
		self.surface_color = _norm_hex(_("Surface"), self.surface_color)
		self.foreground_color = _norm_hex(_("Foreground"), self.foreground_color)
		self.font_stack_for_web = _norm_font_stack(self.font_stack_for_web)
		self.logo_url = _norm_asset_url(_("Logo URL"), self.logo_url)
		self.favicon_url = _norm_asset_url(_("Favicon URL"), self.favicon_url)
		if self.primary_color and self.primary_contrast:
			ratio = _contrast_ratio(self.primary_contrast, self.primary_color)
			if ratio + 1e-9 < _MIN_PRIMARY_CONTRAST_RATIO:
				frappe.throw(
					_(
						"Primary and Primary contrast must reach at least {0}:1 contrast (WCAG non-text baseline). Current: {1:.2f}:1."
					).format(_MIN_PRIMARY_CONTRAST_RATIO, ratio),
					title=_("Theme"),
				)

	def before_save(self):
		if self.apply_to_public_site:
			# Single active theme per site (public bundle).
			frappe.db.sql(
				"""
				update `tabExperience Tenant Theme`
				set apply_to_public_site = 0
				where coalesce(apply_to_public_site, 0) = 1
					and name != %(name)s
				""",
				{"name": self.name or ""},
			)
