# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class PaymentIntent(Document):
	def validate(self):
		if self.web_order and frappe.db.get_value("Web Order", self.web_order, "company") != self.company:
			frappe.throw(_("Web Order must belong to the same company."), title=_("Validation"))
