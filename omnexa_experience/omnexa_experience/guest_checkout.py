# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt
"""
Guest checkout: read Web Order + submit (creates ``Sales Invoice`` via ``Web Order.on_submit``).

HTTP:
  ``GET ...guest_checkout.get_guest_web_order``
  ``POST ...guest_checkout.submit_guest_web_order``

Rate limits: GET 60/min/IP; submit POST 20/hour/IP (stricter than cart create).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import flt


def _serialize_web_order_public(wo) -> dict:
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
	out = {
		"name": wo.name,
		"company": wo.company,
		"status": wo.status,
		"docstatus": wo.docstatus,
		"idempotency_key": wo.idempotency_key or "",
		"grand_total": flt(wo.grand_total),
		"lines": lines_out,
		"sales_invoice": wo.sales_invoice or None,
	}
	return out


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=60, seconds=60, methods=["GET"])
def get_guest_web_order(web_order: str | None = None, company: str | None = None):
	"""Return a Web Order if ``company`` matches (draft or submitted)."""
	if not web_order or not frappe.db.exists("Web Order", web_order):
		frappe.throw(_("Web Order not found."), frappe.DoesNotExistError, title=_("Order"))
	if not company or not frappe.db.exists("Company", company):
		frappe.throw(_("A valid company is required."), title=_("Order"))
	wo = frappe.get_doc("Web Order", web_order)
	if wo.company != company:
		frappe.throw(_("Order does not belong to this store."), title=_("Order"))
	return _serialize_web_order_public(wo)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=3600, methods=["POST"])
def submit_guest_web_order(
	web_order: str | None = None,
	company: str | None = None,
	idempotency_key: str | None = None,
):
	"""
	Submit a **Draft** Web Order (checkout). Idempotent: if already submitted, returns the same payload.

	Optional ``idempotency_key``: when the Web Order has an idempotency key set, the caller must
	pass the same value (defense in depth).
	"""
	if not web_order or not frappe.db.exists("Web Order", web_order):
		frappe.throw(_("Web Order not found."), frappe.DoesNotExistError, title=_("Checkout"))
	if not company or not frappe.db.exists("Company", company):
		frappe.throw(_("A valid company is required."), title=_("Checkout"))

	wo = frappe.get_doc("Web Order", web_order)
	if wo.company != company:
		frappe.throw(_("Order does not belong to this store."), title=_("Checkout"))

	if wo.docstatus == 1:
		wo.reload()
		return _serialize_web_order_public(wo)

	if wo.docstatus != 0:
		frappe.throw(_("This order cannot be submitted."), title=_("Checkout"))

	if wo.status != "Draft":
		frappe.throw(_("Only draft carts can be checked out."), title=_("Checkout"))

	doc_key = (wo.idempotency_key or "").strip()
	if doc_key:
		caller_key = (idempotency_key or "").strip()
		if caller_key != doc_key:
			frappe.throw(_("idempotency_key does not match this cart."), title=_("Checkout"))

	wo.flags.ignore_permissions = True
	wo.submit()
	wo.reload()
	return _serialize_web_order_public(wo)
