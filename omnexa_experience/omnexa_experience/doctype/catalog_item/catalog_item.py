# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CatalogItem(Document):
	def validate(self):
		filters = {"company": self.company, "slug": self.slug}
		if self.name:
			filters["name"] = ["!=", self.name]
		if frappe.get_all("Catalog Item", filters=filters, limit=1):
			frappe.throw(_("Slug must be unique per company."), title=_("Duplicate"))
