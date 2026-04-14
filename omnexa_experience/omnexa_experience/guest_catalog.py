# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt
"""
Guest-safe catalog reads and draft cart (Web Order in ``Draft``).

HTTP (catalog): ``guest_catalog.list_published_catalog_items``, ``get_published_catalog_item``.  
HTTP (cart): ``guest_catalog.create_guest_cart_web_order``.  
HTTP (checkout): ``guest_checkout.get_guest_web_order``, ``guest_checkout.submit_guest_web_order``.  
HTTP (booking): ``guest_booking.*`` (resources, blocks, create, get, cancel).

Rate limits: catalog GET 60/min/IP; cart POST 30/hour/IP (optional ``customer_email`` on cart); checkout POST 20/hour/IP; booking POSTs as documented in ``guest_booking``.
See Docs/Omnexa_Public_API_Reference.md §2–2.2; Omnexa_Master_Checklist §G.9.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, flt, validate_email_address


def _norm_optional_customer_email(value: str | None) -> str | None:
	"""Return normalized lowercase email or ``None``; throw if non-empty but invalid."""
	if not (value or "").strip():
		return None
	v = value.strip()
	if not validate_email_address(v, throw=False):
		frappe.throw(_("customer_email is not valid."), title=_("Cart"))
	return v.lower()


def _parse_lines_arg(lines: Any) -> list[dict[str, Any]]:
	if lines is None:
		return []
	if isinstance(lines, str):
		lines = lines.strip()
		if not lines:
			return []
		try:
			parsed = json.loads(lines)
		except json.JSONDecodeError:
			frappe.throw(_("Invalid lines JSON."), title=_("Cart"))
	else:
		parsed = lines
	if not isinstance(parsed, list):
		frappe.throw(_("lines must be a JSON array."), title=_("Cart"))
	return parsed


def _serialize_draft_web_order(wo) -> dict[str, Any]:
	lines_out = []
	for row in wo.lines or []:
		lines_out.append(
			{
				"catalog_item": row.catalog_item,
				"qty": flt(row.qty),
				"rate": flt(row.rate),
				"amount": flt(row.amount),
				"tax_amount": flt(row.tax_amount),
			}
		)
	return {
		"name": wo.name,
		"company": wo.company,
		"status": wo.status,
		"idempotency_key": wo.idempotency_key or "",
		"customer_email": (wo.customer_email or "").strip(),
		"grand_total": flt(wo.grand_total),
		"lines": lines_out,
	}


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=60, seconds=60, methods=["GET"])
def list_published_catalog_items(
	company: str | None = None,
	limit_start: int | str | None = 0,
	limit_page_length: int | str | None = 20,
):
	"""
	Return published catalog rows for one company (tenant-scoped storefront).

	:param company: Company name (Link target).
	"""
	if not company or not frappe.db.exists("Company", company):
		frappe.throw(_("A valid company is required."), title=_("Catalog"))

	start = cint(limit_start) or 0
	page = cint(limit_page_length) or 20
	page = min(max(page, 1), 100)

	rows = frappe.get_all(
		"Catalog Item",
		filters={"company": company, "published": 1},
		fields=["name", "slug", "title_en", "title_ar", "item_type"],
		limit_start=start,
		limit_page_length=page,
		order_by="modified desc",
		ignore_permissions=True,
	)

	return {"items": rows, "limit_start": start, "limit_page_length": page}


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=60, seconds=60, methods=["GET"])
def get_published_catalog_item(company: str | None = None, slug: str | None = None):
	"""Return one published catalog row by ``slug`` within ``company``."""
	if not company or not frappe.db.exists("Company", company):
		frappe.throw(_("A valid company is required."), title=_("Catalog"))
	if not (slug and str(slug).strip()):
		frappe.throw(_("slug is required."), title=_("Catalog"))
	slug = str(slug).strip()
	row = frappe.db.get_value(
		"Catalog Item",
		{"company": company, "slug": slug, "published": 1},
		["name", "slug", "title_en", "title_ar", "item_type"],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("Catalog item not found."), frappe.DoesNotExistError, title=_("Catalog"))
	return row


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=3600, methods=["POST"])
def create_guest_cart_web_order(
	company: str | None = None,
	idempotency_key: str | None = None,
	lines: Any = None,
	customer_email: str | None = None,
):
	"""
	Create a **Draft** ``Web Order`` (guest cart) or return an existing one for the same
	``company`` + ``idempotency_key``.

	Optional ``customer_email`` (validated) is stored on the Web Order for **portal /me** lists.
	On idempotent retry: if the cart has no email yet, the first non-empty ``customer_email`` is saved;
	if the cart already has an email and a different one is sent, the request is rejected.

	``lines``: JSON array of ``{ "catalog_item": "<Catalog Item name>", "qty": n, "rate": n, "tax_amount"?: n }``.
	Catalog items must be **published** and belong to ``company``. Max 50 lines.
	"""
	if not company or not frappe.db.exists("Company", company):
		frappe.throw(_("A valid company is required."), title=_("Cart"))
	key = (idempotency_key or "").strip()
	if not key:
		frappe.throw(_("idempotency_key is required."), title=_("Cart"))

	existing = frappe.db.get_value(
		"Web Order",
		{"company": company, "idempotency_key": key},
		"name",
	)
	if existing:
		wo = frappe.get_doc("Web Order", existing)
		if wo.docstatus != 0 or wo.status != "Draft":
			frappe.throw(_("Cart cannot be modified."), title=_("Cart"))
		email_new = _norm_optional_customer_email(customer_email)
		if email_new:
			stored = (wo.customer_email or "").strip().lower()
			if not stored:
				wo.customer_email = email_new
				wo.save(ignore_permissions=True)
			elif stored != email_new:
				frappe.throw(
					_("This cart is already linked to another customer email."),
					title=_("Cart"),
				)
		return _serialize_draft_web_order(wo)

	parsed = _parse_lines_arg(lines)
	if not parsed:
		frappe.throw(_("At least one line is required."), title=_("Cart"))
	if len(parsed) > 50:
		frappe.throw(_("Too many lines."), title=_("Cart"))

	wo = frappe.new_doc("Web Order")
	wo.company = company
	wo.idempotency_key = key
	wo.status = "Draft"
	wo.customer_email = _norm_optional_customer_email(customer_email) or None

	for raw in parsed:
		if not isinstance(raw, dict):
			frappe.throw(_("Each line must be an object."), title=_("Cart"))
		ci = (raw.get("catalog_item") or "").strip()
		if not ci:
			frappe.throw(_("catalog_item is required on each line."), title=_("Cart"))
		if not frappe.db.exists("Catalog Item", ci):
			frappe.throw(_("Unknown catalog item: {0}").format(ci), title=_("Cart"))
		pub, ci_co = frappe.db.get_value("Catalog Item", ci, ["published", "company"])
		if not pub:
			frappe.throw(_("Item is not available: {0}").format(ci), title=_("Cart"))
		if ci_co != company:
			frappe.throw(_("Item does not belong to this store."), title=_("Cart"))
		qty = flt(raw.get("qty"))
		rate = flt(raw.get("rate"))
		if qty <= 0:
			frappe.throw(_("Quantity must be positive."), title=_("Cart"))
		if rate < 0:
			frappe.throw(_("Rate cannot be negative."), title=_("Cart"))
		wo.append(
			"lines",
			{
				"catalog_item": ci,
				"qty": qty,
				"rate": rate,
				"tax_amount": flt(raw.get("tax_amount")),
			},
		)

	wo.insert(ignore_permissions=True)
	return _serialize_draft_web_order(wo)
