import re

import frappe


def execute():
	"""Backfill custom_kassa_rasxod on Journal Entries created before the link field existed.

	Older Journal Entries reference their source only in user_remark
	("...Kassa Rasxod {name}..."). Parse that name and populate the new link field
	so the Kassa Rasxod Connections section shows them.
	"""
	if not frappe.db.has_column("Journal Entry", "custom_kassa_rasxod"):
		return

	entries = frappe.get_all(
		"Journal Entry",
		filters={
			"user_remark": ["like", "%Kassa Rasxod %"],
			"custom_kassa_rasxod": ["is", "not set"],
		},
		fields=["name", "user_remark"],
	)

	pattern = re.compile(r"Kassa Rasxod (KR-\S+?)[,.\s]")

	for je in entries:
		match = pattern.search((je.user_remark or "") + " ")
		if not match:
			continue

		kr_name = match.group(1)
		if not frappe.db.exists("Kassa Rasxod", kr_name):
			continue

		frappe.db.set_value(
			"Journal Entry", je.name, "custom_kassa_rasxod", kr_name, update_modified=False
		)
