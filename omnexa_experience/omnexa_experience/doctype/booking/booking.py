# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime


def _cancel_expired_draft_holds(bookable_resource: str) -> None:
	"""Auto-cancel draft holds whose TTL has passed (frees slot for overlap checks)."""
	now = now_datetime()
	frappe.db.sql(
		"""
		UPDATE `tabBooking`
		SET `status` = 'Cancelled'
		WHERE `bookable_resource` = %s
		  AND `status` = 'Draft'
		  AND `hold_expires_at` IS NOT NULL
		  AND `hold_expires_at` < %s
		""",
		(bookable_resource, now),
	)


class Booking(Document):
	def validate(self):
		s = get_datetime(self.start_datetime)
		e = get_datetime(self.end_datetime)
		if s >= e:
			frappe.throw(_("End must be after start."), title=_("Validation"))
		res_company = frappe.db.get_value("Bookable Resource", self.bookable_resource, "company")
		if res_company != self.company:
			frappe.throw(_("Resource belongs to a different company."), title=_("Validation"))
		if self.status in ("Draft", "Confirmed"):
			_cancel_expired_draft_holds(self.bookable_resource)
			self._assert_no_overlap()

	def _assert_no_overlap(self):
		filters = {
			"bookable_resource": self.bookable_resource,
			"status": ["in", ["Draft", "Confirmed"]],
		}
		if self.name:
			filters["name"] = ["!=", self.name]
		others = frappe.get_all(
			"Booking",
			filters=filters,
			fields=["name", "start_datetime", "end_datetime", "status", "hold_expires_at"],
		)
		now = now_datetime()
		s1 = get_datetime(self.start_datetime)
		e1 = get_datetime(self.end_datetime)
		for o in others:
			if o.status == "Draft":
				exp = o.get("hold_expires_at")
				if exp and get_datetime(exp) < now:
					continue
			s2 = get_datetime(o.start_datetime)
			e2 = get_datetime(o.end_datetime)
			if s1 < e2 and s2 < e1:
				frappe.throw(
					_("Slot overlaps with booking {0}").format(o.name), title=_("Availability")
				)
