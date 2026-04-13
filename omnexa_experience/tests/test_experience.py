# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt

import hashlib
import hmac
import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from omnexa_experience.omnexa_experience.payment_webhook import process_payment_intent_webhook


class TestOmnexaExperience(FrappeTestCase):
	def setUp(self):
		super().setUp()
		self._ensure_geo()
		self.company = self._create_company("OMNX-EXP")

	def _ensure_geo(self):
		if not frappe.db.exists("Currency", "EGP"):
			frappe.get_doc(
				{"doctype": "Currency", "currency_name": "EGP", "symbol": "E£", "enabled": 1}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Country", "Egypt"):
			frappe.get_doc(
				{"doctype": "Country", "country_name": "Egypt", "code": "EG"}
			).insert(ignore_permissions=True)

	def _create_company(self, abbr: str):
		if frappe.db.exists("Company", {"abbr": abbr}):
			return frappe.db.get_value("Company", {"abbr": abbr}, "name")
		doc = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": f"Test Co {abbr}",
				"abbr": abbr,
				"default_currency": "EGP",
				"country": "Egypt",
				"status": "Active",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _catalog(self, slug="sku-1"):
		c = frappe.new_doc("Catalog Item")
		c.company = self.company
		c.slug = slug
		c.title_en = "Item"
		c.title_ar = "صنف"
		c.item_type = "product"
		c.published = 1
		c.insert(ignore_permissions=True)
		return c.name

	def test_web_order_idempotency_key_unique(self):
		ci = self._catalog("sku-idem")
		wo1 = frappe.new_doc("Web Order")
		wo1.company = self.company
		wo1.idempotency_key = "idem-1"
		wo1.append("lines", {"catalog_item": ci, "qty": 1, "rate": 10})
		wo1.insert(ignore_permissions=True)
		wo2 = frappe.new_doc("Web Order")
		wo2.company = self.company
		wo2.idempotency_key = "idem-1"
		wo2.append("lines", {"catalog_item": ci, "qty": 1, "rate": 5})
		with self.assertRaises(frappe.ValidationError):
			wo2.insert(ignore_permissions=True)

	def test_booking_overlap_rejected(self):
		res = frappe.new_doc("Bookable Resource")
		res.company = self.company
		res.resource_name = "Room A"
		res.slot_duration_minutes = 60
		res.insert(ignore_permissions=True)
		start = now_datetime()
		end = add_to_date(start, hours=1)
		b1 = frappe.new_doc("Booking")
		b1.company = self.company
		b1.bookable_resource = res.name
		b1.start_datetime = start
		b1.end_datetime = end
		b1.status = "Confirmed"
		b1.insert(ignore_permissions=True)
		b2 = frappe.new_doc("Booking")
		b2.company = self.company
		b2.bookable_resource = res.name
		b2.start_datetime = add_to_date(start, minutes=30)
		b2.end_datetime = add_to_date(end, minutes=30)
		b2.status = "Confirmed"
		with self.assertRaises(frappe.ValidationError):
			b2.insert(ignore_permissions=True)

	def _create_payment_intent(self):
		intent = frappe.new_doc("Payment Intent")
		intent.company = self.company
		intent.amount = 100
		intent.currency = "EGP"
		intent.insert(ignore_permissions=True)
		return intent

	def test_payment_webhook_updates_payment_intent_status(self):
		intent = self._create_payment_intent()
		payload = {
			"payment_intent": intent.name,
			"status": "succeeded",
			"provider_reference": "txn-001",
		}
		raw = json.dumps(payload, sort_keys=True)
		secret = "test-secret"
		signature = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
		result = process_payment_intent_webhook(
			event_id="evt-pay-1",
			payload=payload,
			received_signature=signature,
			secret=secret,
		)
		self.assertEqual(result["status"], "processed")
		intent.reload()
		self.assertEqual(intent.status, "succeeded")
		self.assertEqual(intent.client_secret_ref, "txn-001")

	def test_payment_webhook_duplicate_event_is_idempotent(self):
		intent = self._create_payment_intent()
		payload = {"payment_intent": intent.name, "status": "processing"}
		process_payment_intent_webhook(event_id="evt-pay-dup", payload=payload)
		result = process_payment_intent_webhook(event_id="evt-pay-dup", payload=payload)
		self.assertEqual(result["status"], "duplicate")
