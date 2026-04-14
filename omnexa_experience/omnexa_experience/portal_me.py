# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt
"""
Customer-portal style **/me** reads scoped by ``customer_email`` + ``company``.

Auth (MVP): ``Authorization: Bearer <omnexa_experience_portal_api_token>`` from site config
(common tenant secret for headless portal / BFF). Pair with HTTPS and rate limits.

HTTP (same as other whitelisted methods), e.g.::
  GET /api/v1/method/omnexa_experience.omnexa_experience.portal_me.list_my_web_orders
  GET /api/method/omnexa_experience.omnexa_experience.portal_me.list_my_web_orders

See Docs/Omnexa_Public_API_Reference.md §5–6.
"""

from __future__ import annotations

import secrets

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, flt


def _require_experience_portal_bearer() -> None:
	expected = (frappe.conf.get("omnexa_experience_portal_api_token") or "").strip()
	if not expected:
		frappe.throw(
			_("Set omnexa_experience_portal_api_token in site_config to enable portal /me APIs."),
			title=_("Configuration"),
		)
	raw = frappe.get_request_header("Authorization") or ""
	if not raw.startswith("Bearer "):
		frappe.throw(_("Authorization: Bearer token required."), frappe.PermissionError, title=_("Auth"))
	got = raw[7:].strip()
	if not secrets.compare_digest(got.encode("utf-8"), expected.encode("utf-8")):
		frappe.throw(_("Invalid portal token."), frappe.PermissionError, title=_("Auth"))


def _norm_email(value: str | None) -> str:
	return (value or "").strip().lower()


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=60, seconds=60, methods=["GET"])
def list_my_web_orders(
	company: str | None = None,
	customer_email: str | None = None,
	limit_start: int | str | None = 0,
	limit_page_length: int | str | None = 20,
):
	"""List ``Web Order`` rows for one company + customer email (Draft or submitted)."""
	_require_experience_portal_bearer()
	if not company or not frappe.db.exists("Company", company):
		frappe.throw(_("A valid company is required."), title=_("Orders"))
	email = _norm_email(customer_email)
	if not email or "@" not in email:
		frappe.throw(_("A valid customer_email is required."), title=_("Orders"))

	start = cint(limit_start) or 0
	page = cint(limit_page_length) or 20
	page = min(max(page, 1), 100)

	rows = frappe.db.sql(
		"""
		select name, status, grand_total, sales_invoice, creation, modified
		from `tabWeb Order`
		where company=%(company)s and ifnull(lower(customer_email), '')=%(email)s
		order by modified desc
		limit %(start)s, %(page_len)s
		""",
		{"company": company, "email": email, "start": start, "page_len": page},
		as_dict=True,
	)
	return {"orders": rows, "limit_start": start, "limit_page_length": page}


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=60, seconds=60, methods=["GET"])
def get_my_web_order(
	web_order: str | None = None,
	company: str | None = None,
	customer_email: str | None = None,
):
	"""Return one ``Web Order`` if it belongs to ``company`` and ``customer_email``."""
	_require_experience_portal_bearer()
	if not web_order or not frappe.db.exists("Web Order", web_order):
		frappe.throw(_("Web Order not found."), frappe.DoesNotExistError, title=_("Orders"))
	if not company:
		frappe.throw(_("A valid company is required."), title=_("Orders"))
	email = _norm_email(customer_email)
	if not email or "@" not in email:
		frappe.throw(_("A valid customer_email is required."), title=_("Orders"))

	row_list = frappe.db.sql(
		"""
		select name, company, status, grand_total, sales_invoice, customer_email,
			idempotency_key, creation, modified
		from `tabWeb Order`
		where name=%(name)s and company=%(company)s
			and ifnull(lower(customer_email), '')=%(email)s
		limit 1
		""",
		{"name": web_order, "company": company, "email": email},
		as_dict=True,
	)
	row = row_list[0] if row_list else None
	if not row:
		frappe.throw(_("Web Order not found."), frappe.DoesNotExistError, title=_("Orders"))

	lines = frappe.get_all(
		"Web Order Line",
		filters={"parent": web_order},
		fields=["catalog_item", "qty", "rate", "amount", "tax_amount"],
		ignore_permissions=True,
		order_by="idx asc",
	)
	row["lines"] = lines
	row["grand_total"] = flt(row.get("grand_total"))
	return row


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=60, seconds=60, methods=["GET"])
def list_my_bookings(
	company: str | None = None,
	customer_email: str | None = None,
	limit_start: int | str | None = 0,
	limit_page_length: int | str | None = 30,
):
	"""List ``Booking`` rows for one company + customer email."""
	_require_experience_portal_bearer()
	if not company or not frappe.db.exists("Company", company):
		frappe.throw(_("A valid company is required."), title=_("Bookings"))
	email = _norm_email(customer_email)
	if not email or "@" not in email:
		frappe.throw(_("A valid customer_email is required."), title=_("Bookings"))

	start = cint(limit_start) or 0
	page = cint(limit_page_length) or 30
	page = min(max(page, 1), 100)

	rows = frappe.db.sql(
		"""
		select name, bookable_resource, start_datetime, end_datetime, status,
			hold_expires_at, creation
		from `tabBooking`
		where company=%(company)s and ifnull(lower(customer_email), '')=%(email)s
		order by start_datetime desc
		limit %(start)s, %(page_len)s
		""",
		{"company": company, "email": email, "start": start, "page_len": page},
		as_dict=True,
	)
	return {"bookings": rows, "limit_start": start, "limit_page_length": page}


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=60, seconds=60, methods=["GET"])
def get_my_booking(
	booking: str | None = None,
	company: str | None = None,
	customer_email: str | None = None,
):
	"""Return one ``Booking`` if it belongs to ``company`` and ``customer_email`` (case-insensitive email)."""
	_require_experience_portal_bearer()
	if not booking or not frappe.db.exists("Booking", booking):
		frappe.throw(_("Booking not found."), frappe.DoesNotExistError, title=_("Bookings"))
	if not company or not frappe.db.exists("Company", company):
		frappe.throw(_("A valid company is required."), title=_("Bookings"))
	email = _norm_email(customer_email)
	if not email or "@" not in email:
		frappe.throw(_("A valid customer_email is required."), title=_("Bookings"))

	row_list = frappe.db.sql(
		"""
		select name, company, bookable_resource, start_datetime, end_datetime,
			customer_email, payment_intent, status, hold_expires_at
		from `tabBooking`
		where name=%(name)s and company=%(company)s
			and ifnull(lower(customer_email), '')=%(email)s
		limit 1
		""",
		{"name": booking, "company": company, "email": email},
		as_dict=True,
	)
	row = row_list[0] if row_list else None
	if not row:
		frappe.throw(_("Booking not found."), frappe.DoesNotExistError, title=_("Bookings"))

	return {
		"name": row["name"],
		"company": row["company"],
		"bookable_resource": row["bookable_resource"],
		"start_datetime": row["start_datetime"],
		"end_datetime": row["end_datetime"],
		"customer_email": row.get("customer_email") or "",
		"payment_intent": row.get("payment_intent") or None,
		"status": row["status"],
		"hold_expires_at": row.get("hold_expires_at"),
	}
