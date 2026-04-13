# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from omnexa_accounting.utils.party import get_or_create_web_guest_customer


class WebOrder(Document):
	def validate(self):
		self._validate_idempotency()
		self._validate_line_companies()
		self._set_line_amounts()

	def on_submit(self):
		if self.sales_invoice:
			return
		si = frappe.new_doc("Sales Invoice")
		si.company = self.company
		si.currency = frappe.db.get_value("Company", self.company, "default_currency")
		si.customer = get_or_create_web_guest_customer(self.company)
		si.posting_date = frappe.utils.today()
		for row in self.lines or []:
			ci_name = row.catalog_item
			slug = frappe.db.get_value("Catalog Item", ci_name, "slug") or ci_name
			si.append(
				"items",
				{
					"item_code": slug,
					"qty": row.qty,
					"rate": row.rate,
					"amount": row.amount,
				},
			)
		si.insert(ignore_permissions=True)
		si.submit()
		self.db_set("sales_invoice", si.name, update_modified=False)

	def _validate_line_companies(self):
		for row in self.lines or []:
			if not row.catalog_item:
				continue
			if frappe.db.get_value("Catalog Item", row.catalog_item, "company") != self.company:
				frappe.throw(
					_("Row {0}: Catalog Item must belong to the same company.").format(row.idx),
					title=_("Company"),
				)

	def _validate_idempotency(self):
		if not self.idempotency_key:
			return
		filters = {"company": self.company, "idempotency_key": self.idempotency_key}
		if self.name:
			filters["name"] = ["!=", self.name]
		if frappe.get_all("Web Order", filters=filters, limit=1):
			frappe.throw(_("Duplicate Idempotency Key for this company."), title=_("Idempotency"))

	def _set_line_amounts(self):
		total = 0
		for row in self.lines or []:
			row.amount = flt(row.qty) * flt(row.rate)
			row.tax_amount = flt(row.tax_amount)
			total += flt(row.amount) + flt(row.tax_amount)
		self.grand_total = total
