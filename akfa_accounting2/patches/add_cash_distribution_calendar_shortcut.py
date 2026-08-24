# Copyright (c) 2026, Asadbek and contributors
# For license information, please see license.txt

"""Add a shortcut to the Cash Distribution Kalendar page in the Aripov workspace."""

import json

import frappe

WORKSPACE = "Aripov oynasi"
PAGE = "cash-distribution-calendar"
LABEL = "Cash Distribution Kalendar"


def execute():
	if not frappe.db.exists("Workspace", WORKSPACE):
		return

	ws = frappe.get_doc("Workspace", WORKSPACE)

	# 1) Shortcut child row
	if not any(s.link_to == PAGE and s.type == "Page" for s in ws.shortcuts):
		ws.append("shortcuts", {
			"type": "Page",
			"link_to": PAGE,
			"label": LABEL,
			"color": "Green",
		})

	# 2) Layout block in content JSON
	try:
		content = json.loads(ws.content or "[]")
	except (json.JSONDecodeError, TypeError):
		content = []

	has_block = any(
		b.get("type") == "shortcut" and b.get("data", {}).get("shortcut_name") == LABEL
		for b in content
	)
	if not has_block:
		content.append({
			"id": frappe.generate_hash(length=10),
			"type": "shortcut",
			"data": {"shortcut_name": LABEL, "col": 3},
		})
		ws.content = json.dumps(content)

	ws.save(ignore_permissions=True)
