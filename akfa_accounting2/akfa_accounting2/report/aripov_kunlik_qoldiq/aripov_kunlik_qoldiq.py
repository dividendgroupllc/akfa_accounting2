# Copyright (c) 2026, Asadbek and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate

from akfa_accounting2.akfa_accounting2.doctype.cash_distribution_entry.cash_distribution_entry import (
	HAMIDULLA_MODES,
)

EPOCH = "1900-01-01"


def execute(filters=None):
	filters = filters or {}
	if not filters.get("from_date"):
		filters["from_date"] = add_days(frappe.utils.today(), -30)
	if not filters.get("to_date"):
		filters["to_date"] = frappe.utils.today()
	return get_columns(), get_data(filters), None, None, None


def get_columns():
	return [
		{"label": _("Sana"), "fieldname": "sana", "fieldtype": "Date", "width": 110},
		{"label": _("Valyuta"), "fieldname": "valyuta", "fieldtype": "Link", "options": "Currency", "width": 80},
		{"label": _("Transfer Kirim"), "fieldname": "transfer_kirim", "fieldtype": "Currency", "options": "valyuta", "width": 140},
		{"label": _("Rasxod Kirim"), "fieldname": "rasxod_kirim", "fieldtype": "Currency", "options": "valyuta", "width": 140},
		{"label": _("Jami Kirim"), "fieldname": "jami_kirim", "fieldtype": "Currency", "options": "valyuta", "width": 150},
		{"label": _("Tarqatilgan"), "fieldname": "tarqatilgan", "fieldtype": "Currency", "options": "valyuta", "width": 150},
		{"label": _("Kunlik Qoldiq"), "fieldname": "kunlik_qoldiq", "fieldtype": "Currency", "options": "valyuta", "width": 150},
		{"label": _("To'plangan Qoldiq"), "fieldname": "kumulativ_qoldiq", "fieldtype": "Currency", "options": "valyuta", "width": 160},
	]


def get_company(filters):
	company = filters.get("company") or frappe.db.get_single_value("Global Defaults", "default_company")
	if not company:
		company = frappe.db.get_value("Company", {}, "name")
	return company


def get_aripov_accounts(company):
	"""Return {account_name: currency} for 1114 (USD) and 1115 (UZS)."""
	mapping = {}
	for number, currency in (("1114", "USD"), ("1115", "UZS")):
		acc = frappe.db.get_value("Account", {"account_number": number, "company": company}, "name")
		if acc:
			mapping[acc] = currency
	return mapping


def get_transfers(company, accounts, start, end):
	"""Internal Transfer (Davron/Azimov → Aripov) inflow by date+currency.
	No custom_is_distributed filter — full history, never disappears."""
	if not accounts:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT pe.posting_date AS sana,
			pe.paid_to_account_currency AS currency,
			SUM(CASE WHEN pe.paid_to_account_currency = 'UZS'
					 THEN pe.received_amount ELSE pe.paid_amount END) AS amount
		FROM `tabPayment Entry` pe
		WHERE pe.payment_type = 'Internal Transfer'
			AND pe.paid_to IN %(accounts)s
			AND pe.company = %(company)s
			AND pe.docstatus = 1
			AND pe.posting_date BETWEEN %(start)s AND %(end)s
		GROUP BY pe.posting_date, pe.paid_to_account_currency
		""",
		{"accounts": list(accounts), "company": company, "start": start, "end": end},
		as_dict=True,
	)
	out = {}
	for r in rows:
		out[(str(r.sana), r.currency)] = flt(r.amount)
	return out


def get_rasxod(start, end):
	"""Hamidulla Kassa Rasxod (investor qopladi) inflow → USD only.
	Mirrors get_cash_distribution_data rasxod logic."""
	rows = frappe.db.sql(
		"""
		SELECT kr.posting_date AS sana, kr.items_data
		FROM `tabKassa Rasxod` kr
		WHERE kr.mode_of_payment IN %(modes)s
			AND kr.docstatus = 1
			AND kr.posting_date BETWEEN %(start)s AND %(end)s
		""",
		{"modes": tuple(HAMIDULLA_MODES.values()), "start": start, "end": end},
		as_dict=True,
	)
	out = {}
	for kr in rows:
		amount_usd = 0
		if kr.items_data:
			try:
				items = json.loads(kr.items_data)
			except (json.JSONDecodeError, TypeError):
				items = []
			for item in items:
				if (
					item.get("rasxod_podochot") == "Расход"
					and not item.get("party")
					and not item.get("party_type")
				):
					amount_usd += flt(item.get("paid_amount_usd"))
		if amount_usd:
			key = (str(kr.sana), "USD")
			out[key] = out.get(key, 0) + amount_usd
	return out


def get_distributed(company, start, end):
	"""Distributed to suppliers (Zavodlar) by date+currency."""
	rows = frappe.db.sql(
		"""
		SELECT cde.posting_date AS sana, cdd.currency AS currency,
			SUM(cdd.amount) AS amount
		FROM `tabCash Distribution Entry` cde
		INNER JOIN `tabCash Distribution Detail` cdd ON cdd.parent = cde.name
		WHERE cde.company = %(company)s
			AND cde.docstatus = 1
			AND cde.posting_date BETWEEN %(start)s AND %(end)s
		GROUP BY cde.posting_date, cdd.currency
		""",
		{"company": company, "start": start, "end": end},
		as_dict=True,
	)
	out = {}
	for r in rows:
		out[(str(r.sana), r.currency)] = flt(r.amount)
	return out


def get_data(filters):
	company = get_company(filters)
	accounts = get_aripov_accounts(company)
	from_date = str(getdate(filters["from_date"]))
	to_date = str(getdate(filters["to_date"]))

	currencies = ["USD", "UZS"]
	if filters.get("currency"):
		currencies = [filters["currency"]]

	# Opening balances (everything strictly before from_date)
	open_end = add_days(from_date, -1)
	opening = {c: 0 for c in currencies}
	for src in (
		get_transfers(company, accounts, EPOCH, open_end),
		get_rasxod(EPOCH, open_end),
	):
		for (sana, cur), amt in src.items():
			if cur in opening:
				opening[cur] += amt
	for (sana, cur), amt in get_distributed(company, EPOCH, open_end).items():
		if cur in opening:
			opening[cur] -= amt

	# Window data
	transfers = get_transfers(company, accounts, from_date, to_date)
	rasxod = get_rasxod(from_date, to_date)
	distributed = get_distributed(company, from_date, to_date)

	# Collect all dates present in window per currency
	per_cur_dates = {c: set() for c in currencies}
	for src in (transfers, rasxod, distributed):
		for (sana, cur) in src.keys():
			if cur in per_cur_dates:
				per_cur_dates[cur].add(sana)

	data = []
	for cur in currencies:
		running = flt(opening[cur])
		# Opening row
		data.append({
			"sana": None,
			"valyuta": cur,
			"transfer_kirim": None,
			"rasxod_kirim": None,
			"jami_kirim": None,
			"tarqatilgan": None,
			"kunlik_qoldiq": None,
			"kumulativ_qoldiq": running,
			"is_opening": 1,
			"bold": 1,
		})
		for sana in sorted(per_cur_dates[cur]):
			t = flt(transfers.get((sana, cur), 0))
			r = flt(rasxod.get((sana, cur), 0))
			d = flt(distributed.get((sana, cur), 0))
			jami = t + r
			kunlik = jami - d
			running += kunlik
			data.append({
				"sana": getdate(sana),
				"valyuta": cur,
				"transfer_kirim": t,
				"rasxod_kirim": r,
				"jami_kirim": jami,
				"tarqatilgan": d,
				"kunlik_qoldiq": kunlik,
				"kumulativ_qoldiq": running,
			})

	return data
