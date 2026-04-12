# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime


class Booking(Document):
	def validate(self):
		s = get_datetime(self.start_datetime)
		e = get_datetime(self.end_datetime)
		if s >= e:
			frappe.throw(_("End must be after start."), title=_("Validation"))
		res_company = frappe.db.get_value("Bookable Resource", self.bookable_resource, "company")
		if res_company != self.company:
			frappe.throw(_("Resource belongs to a different company."), title=_("Validation"))
		if self.status == "Confirmed":
			self._assert_no_overlap()

	def _assert_no_overlap(self):
		filters = {
			"bookable_resource": self.bookable_resource,
			"status": "Confirmed",
		}
		if self.name:
			filters["name"] = ["!=", self.name]
		others = frappe.get_all(
			"Booking",
			filters=filters,
			fields=["name", "start_datetime", "end_datetime"],
		)
		s1 = get_datetime(self.start_datetime)
		e1 = get_datetime(self.end_datetime)
		for o in others:
			s2 = get_datetime(o.start_datetime)
			e2 = get_datetime(o.end_datetime)
			if s1 < e2 and s2 < e1:
				frappe.throw(
					_("Slot overlaps with booking {0}").format(o.name), title=_("Availability")
				)
