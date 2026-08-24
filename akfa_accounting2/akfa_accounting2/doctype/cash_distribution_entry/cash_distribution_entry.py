# Copyright (c) 2025, Asadbek and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

# Account number constants
ARIPOV_ACCOUNTS = ['1114', '1115']
HAMIDULLA_MODES = {
	'USD': 'Наличный USD H',
	'UZS': 'Наличный UZS H'
}
UZS_DISTRIBUTION_ROUNDING_FACTOR = 1000


def round_uzs_distribution_amount(amount):
	"""Round UZS distribution amounts to the nearest 1,000 UZS."""
	amount = flt(amount)
	return flt(((amount + (UZS_DISTRIBUTION_ROUNDING_FACTOR / 2)) // UZS_DISTRIBUTION_ROUNDING_FACTOR) * UZS_DISTRIBUTION_ROUNDING_FACTOR)


def get_exchange_rate_with_fallback(posting_date):
	"""Get exchange rate for the posting date with fallback to latest available rate"""
	exchange_rate = frappe.db.get_value(
		"Currency Exchange",
		{"from_currency": "USD", "to_currency": "UZS", "date": posting_date},
		"exchange_rate"
	)
	
	if not exchange_rate:
		latest_rate = frappe.db.sql("""
			SELECT exchange_rate
			FROM `tabCurrency Exchange`
			WHERE from_currency = 'USD'
				AND to_currency = 'UZS'
				AND date <= %s
			ORDER BY date DESC
			LIMIT 1
		""", (posting_date,), as_dict=True)
		
		if latest_rate:
			exchange_rate = latest_rate[0].exchange_rate
	
	return flt(exchange_rate) or 1


class CashDistributionEntry(Document):
	def validate(self):
		self.validate_exchange_rate()
		self.validate_supplier_group()
		self.set_party_currency()
		self.set_distribution_accounts()
		self.calculate_totals()
		self.validate_difference()

	def validate_supplier_group(self):
		"""Only suppliers in the 'Zavodlar' supplier group are allowed"""
		for row in self.distribution_details:
			if row.supplier:
				group = frappe.db.get_value("Supplier", row.supplier, "supplier_group")
				if group != "Zavodlar":
					frappe.throw(
						_("Supplier {0} is not in the 'Zavodlar' supplier group").format(row.supplier)
					)

	def validate_exchange_rate(self):
		"""Check if exchange rate exists for the posting date.
		If not found for exact date, use the most recent available rate.
		"""
		exchange_rate = frappe.db.get_value(
			"Currency Exchange",
			{"from_currency": "USD", "to_currency": "UZS", "date": self.posting_date},
			"exchange_rate"
		)

		# If not found, get the most recent rate before or on posting date
		if not exchange_rate:
			latest_rate = frappe.db.sql("""
				SELECT exchange_rate, date
				FROM `tabCurrency Exchange`
				WHERE from_currency = 'USD'
					AND to_currency = 'UZS'
					AND date <= %s
				ORDER BY date DESC
				LIMIT 1
			""", (self.posting_date,), as_dict=True)
			
			if latest_rate:
				exchange_rate = latest_rate[0].exchange_rate
				frappe.msgprint(
					_("Using exchange rate from {0} (rate: {1})").format(
						frappe.utils.formatdate(latest_rate[0].date),
						exchange_rate
					),
					alert=True
				)

		if not exchange_rate:
			frappe.throw(
				_("No Currency Exchange rate found for USD to UZS. Please add an exchange rate first.")
			)

	def set_party_currency(self):
		"""Set party_currency from the Supplier's billing currency"""
		for row in self.distribution_details:
			if row.supplier:
				party_currency = frappe.db.get_value("Supplier", row.supplier, "default_currency")
				if party_currency:
					row.party_currency = party_currency

	def set_distribution_accounts(self):
		"""Set creditors account based on party_currency (supplier's main currency)"""
		for row in self.distribution_details:
			if row.party_currency and self.company:
				account_number = "2110" if row.party_currency == "USD" else "2111"
				creditors_account = frappe.db.get_value(
					"Account",
					{"account_number": account_number, "company": self.company},
					"name"
				)
				if creditors_account:
					row.creditors_account = creditors_account

	def calculate_totals(self):
		"""Calculate totals based on new business logic:
		ARIPOV TOTAL = Internal Transfers + Hamidulla Rasxod + Qabul (Receive)
		"""
		# Internal Transfers TO ARIPOV
		self.internal_transfers_usd = sum(
			flt(t.amount) for t in self.transfer_items
			if t.currency == "USD"
		)
		self.internal_transfers_uzs = sum(
			flt(t.amount) for t in self.transfer_items
			if t.currency == "UZS"
		)

		# Hamidulla Kassa Rasxod (investor qopladi, converted to USD)
		self.hamidulla_rasxod_usd = sum(flt(r.amount_usd) for r in self.rasxod_items)

		# Payment Entry Receive TO ARIPOV (money received directly into Aripov cash)
		self.receive_total_usd = sum(
			flt(r.amount) for r in self.receive_items
			if r.currency == "USD"
		)
		self.receive_total_uzs = sum(
			flt(r.amount) for r in self.receive_items
			if r.currency == "UZS"
		)

		# ARIPOV TOTAL = Internal Transfers + Hamidulla Rasxod + Receive
		self.aripov_total_usd = (
			flt(self.internal_transfers_usd)
			+ flt(self.hamidulla_rasxod_usd)
			+ flt(self.receive_total_usd)
		)
		self.aripov_total_uzs = flt(self.internal_transfers_uzs) + flt(self.receive_total_uzs)

		# Total Distributed (from distribution_details)
		self.total_distributed_usd = sum(
			flt(item.amount) for item in self.distribution_details
			if item.currency == "USD"
		)
		self.total_distributed_uzs = sum(
			flt(item.amount) for item in self.distribution_details
			if item.currency == "UZS"
		)

		# Difference = Aripov Total - Distributed (must be >= 0)
		self.difference_usd = flt(self.aripov_total_usd) - flt(self.total_distributed_usd)
		self.difference_uzs = flt(self.aripov_total_uzs) - flt(self.total_distributed_uzs)

		# Day's exchange rate (shown on form near distribution grid)
		self.kurs = flt(get_exchange_rate_with_fallback(self.posting_date))

		# Keep legacy fields for backward compatibility
		self.total_received_usd = self.aripov_total_usd
		self.total_received_uzs = self.aripov_total_uzs

	def validate_difference(self):
		"""Ensure total distributed doesn't exceed Aripov total"""
		if self.docstatus == 1:
			# Round to 2 decimals: distributed amounts are entered at currency precision,
			# while Aripov totals carry full conversion precision (avoid false rounding errors)
			if flt(self.difference_usd, 2) < 0:
				frappe.throw(
					_("USD: Total Distributed ({0}) cannot exceed Aripov Total ({1}). Difference: {2}").format(
						self.total_distributed_usd, self.aripov_total_usd, self.difference_usd
					)
				)
			if flt(self.difference_uzs, 2) < 0:
				frappe.throw(
					_("UZS: Total Distributed ({0}) cannot exceed Aripov Total ({1}). Difference: {2}").format(
						self.total_distributed_uzs, self.aripov_total_uzs, self.difference_uzs
					)
				)

	def on_submit(self):
		"""Create Journal Entry and mark Kassa Rasxod as distributed"""
		self.create_distribution_journal_entry()
		self.mark_kassa_rasxod_as_distributed()
		self.mark_payment_entries_as_distributed()
		self.mark_receive_payment_entries_as_distributed()

	def on_cancel(self):
		"""Cancel linked Journal Entry and unmark distributed items"""
		self.cancel_distribution_journal_entry()
		self.unmark_kassa_rasxod()
		self.unmark_payment_entries()
		self.unmark_receive_payment_entries()

	def create_distribution_journal_entry(self):
		"""Create a single Journal Entry for all distributions.
		
		Logic:
		- Credit Aripov accounts (1114 USD, 1115 UZS) - money going out
		- Debit Creditors accounts (2110 USD, 2111 UZS) - supplier debt recorded
		- Creditors account selected based on supplier's currency (party_currency)
		"""
		if not self.distribution_details:
			return
		
		# Get exchange rate (with fallback to latest)
		exchange_rate = get_exchange_rate_with_fallback(self.posting_date)
		
		company_currency = frappe.db.get_value("Company", self.company, "default_currency")
		
		# Get Aripov accounts
		aripov_usd_account = frappe.db.get_value(
			"Account", {"account_number": "1114", "company": self.company}, "name"
		)
		aripov_uzs_account = frappe.db.get_value(
			"Account", {"account_number": "1115", "company": self.company}, "name"
		)

		# OFIS account (2112) absorbs any shortfall so Aripov cash never goes negative.
		# 2112 is a Payable account, so the JE row needs the supplier linked to it.
		ofis_account = frappe.db.get_value(
			"Account", {"account_number": "2112", "company": self.company}, "name"
		)
		ofis_supplier = frappe.db.get_value(
			"Party Account", {"parenttype": "Supplier", "account": ofis_account}, "parent"
		) if ofis_account else None

		# Aripov cash balances BEFORE this JE (account currency: 1114 in USD, 1115 in UZS)
		from erpnext.accounts.utils import get_balance_on
		avail_usd = flt(get_balance_on(account=aripov_usd_account, date=self.posting_date)) if aripov_usd_account else 0
		avail_uzs = flt(get_balance_on(account=aripov_uzs_account, date=self.posting_date)) if aripov_uzs_account else 0

		# Calculate totals by payment currency
		total_usd_distributed = sum(
			flt(item.amount) for item in self.distribution_details if item.currency == "USD"
		)
		total_uzs_distributed = sum(
			flt(item.amount) for item in self.distribution_details if item.currency == "UZS"
		)
		
		if total_usd_distributed == 0 and total_uzs_distributed == 0:
			return
		
		# Create Journal Entry
		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Journal Entry"
		je.posting_date = self.posting_date
		je.company = self.company
		je.multi_currency = 1
		je.user_remark = _("Cash Distribution Entry: {0}").format(self.name)
		je.custom_cash_distribution_entry = self.name
		
		# Calculate exchange rates for JE
		usd_exchange_rate = flt(exchange_rate) if company_currency == "UZS" else 1
		uzs_exchange_rate = 1 if company_currency == "UZS" else (1 / flt(exchange_rate) if exchange_rate else 1)
		
		# Credit Aripov cash up to its available balance; route the shortfall to 2112.
		shortfall_usd_total = 0  # combined shortfall credited to 2112 (in USD)

		# Hamidulla rasxod (investor qopladi) — bu real Aripov kassasi EMAS (notional
		# kirim). Shuning uchun uni har doim OFIS 2112 (USD) ga kreditlaymiz; Aripov
		# 1114 esa faqat real USD (transfer + receive) qismini qoplaydi. Shunda kunlik
		# Aripov kassasi 0 ga keladi, minusда osilib qolmaydi.
		ofis_from_hamidulla = (
			min(flt(self.hamidulla_rasxod_usd), total_usd_distributed)
			if total_usd_distributed > 0 else 0
		)

		# Row 1: Credit Aripov USD account (real qism, mavjud balansgacha)
		if total_usd_distributed > 0 and aripov_usd_account:
			real_usd_needed = total_usd_distributed - ofis_from_hamidulla
			credit_1114 = min(real_usd_needed, max(avail_usd, 0))
			if credit_1114 > 0:
				je.append("accounts", {
					"account": aripov_usd_account,
					"account_currency": "USD",
					"exchange_rate": usd_exchange_rate,
					"debit_in_account_currency": 0,
					"credit_in_account_currency": credit_1114,
				})
			# OFIS 2112 = notional Hamidulla + (real yetmasa) qolgan shortfall
			shortfall_usd_total += ofis_from_hamidulla + (real_usd_needed - credit_1114)

		# Row 2: Credit Aripov UZS account (capped at available UZS balance)
		if total_uzs_distributed > 0 and aripov_uzs_account:
			credit_1115 = min(total_uzs_distributed, max(avail_uzs, 0))
			if credit_1115 > 0:
				je.append("accounts", {
					"account": aripov_uzs_account,
					"account_currency": "UZS",
					"exchange_rate": uzs_exchange_rate,
					"debit_in_account_currency": 0,
					"credit_in_account_currency": credit_1115,
				})
			shortfall_uzs = total_uzs_distributed - credit_1115
			if shortfall_uzs > 0:
				# Convert UZS shortfall to USD at the posting date rate (2112 is a USD account)
				shortfall_usd_total += flt(shortfall_uzs) / flt(exchange_rate) if exchange_rate else 0

		# Shortfall row: Credit 2112 (Creditors OFIS, USD)
		if shortfall_usd_total > 0:
			if not ofis_account:
				frappe.throw(_("Account 2112 (Creditors OFIS) not found"))
			if not ofis_supplier:
				frappe.throw(_("No Supplier is linked to account {0}").format(ofis_account))
			je.append("accounts", {
				"account": ofis_account,
				"party_type": "Supplier",
				"party": ofis_supplier,
				"account_currency": "USD",
				"exchange_rate": usd_exchange_rate,
				"debit_in_account_currency": 0,
				"credit_in_account_currency": shortfall_usd_total,
			})

		# Group distributions by supplier and party_currency
		# Key: (supplier, party_currency, payment_currency)
		supplier_groups = {}
		for item in self.distribution_details:
			if flt(item.amount) <= 0:
				continue
			key = (item.supplier, item.party_currency or item.currency, item.currency)
			if key not in supplier_groups:
				supplier_groups[key] = 0
			supplier_groups[key] += flt(item.amount)
		
		# Rows 3+: Debit Creditors accounts for each supplier
		for (supplier, party_currency, payment_currency), amount in supplier_groups.items():
			# Determine creditors account based on supplier's currency
			creditors_account_number = "2110" if party_currency == "USD" else "2111"
			creditors_account = frappe.db.get_value(
				"Account", {"account_number": creditors_account_number, "company": self.company}, "name"
			)
			
			if not creditors_account:
				frappe.throw(_("Creditors Account ({0}) not found").format(creditors_account_number))
			
			# Convert amount if payment currency differs from supplier currency
			if payment_currency != party_currency:
				if payment_currency == "UZS" and party_currency == "USD":
					# Pay in UZS, supplier is USD → convert UZS to USD
					amount_in_party_currency = flt(amount) / flt(exchange_rate)
				elif payment_currency == "USD" and party_currency == "UZS":
					# Pay in USD, supplier is UZS → convert USD to UZS
					amount_in_party_currency = round_uzs_distribution_amount(flt(amount) * flt(exchange_rate))
				else:
					amount_in_party_currency = amount
			else:
				amount_in_party_currency = amount
			
			# Calculate exchange rate for this entry
			if party_currency == company_currency:
				party_exchange_rate = 1
			elif party_currency == "USD" and company_currency == "UZS":
				party_exchange_rate = flt(exchange_rate)
			elif party_currency == "UZS" and company_currency == "USD":
				party_exchange_rate = 1 / flt(exchange_rate) if exchange_rate else 1
			else:
				party_exchange_rate = 1
			
			je.append("accounts", {
				"account": creditors_account,
				"party_type": "Supplier",
				"party": supplier,
				"account_currency": party_currency,
				"exchange_rate": party_exchange_rate,
				"debit_in_account_currency": amount_in_party_currency,
				"credit_in_account_currency": 0,
			})
		
		je.insert()
		je.submit()
		
		# Save JE reference
		frappe.db.set_value("Cash Distribution Entry", self.name, "journal_entry", je.name)
		frappe.msgprint(_("Journal Entry created: {0}").format(je.name))

	def cancel_distribution_journal_entry(self):
		"""Cancel linked Journal Entry"""
		je_names = frappe.db.get_value("Cash Distribution Entry", self.name, "journal_entry")
		if je_names:
			for je_name in je_names.split(", "):
				je_name = je_name.strip()
				if frappe.db.exists("Journal Entry", je_name):
					je = frappe.get_doc("Journal Entry", je_name)
					if je.docstatus == 1:
						je.cancel()
			frappe.msgprint(_("Journal Entries cancelled"))

	def mark_kassa_rasxod_as_distributed(self):
		"""Mark Hamidulla Rasxod entries as distributed"""
		for item in self.rasxod_items:
			if item.kassa_rasxod:
				frappe.db.set_value("Kassa Rasxod", item.kassa_rasxod, "custom_is_distributed", 1)

	def unmark_kassa_rasxod(self):
		"""Unmark Kassa Rasxod when cancelled"""
		for item in self.rasxod_items:
			if item.kassa_rasxod:
				frappe.db.set_value("Kassa Rasxod", item.kassa_rasxod, "custom_is_distributed", 0)

	def mark_payment_entries_as_distributed(self):
		"""Mark Internal Transfer Payment Entries as distributed"""
		for item in self.transfer_items:
			if item.payment_entry:
				frappe.db.set_value("Payment Entry", item.payment_entry, "custom_is_distributed", 1)

	def unmark_payment_entries(self):
		"""Unmark Payment Entries when this document is cancelled"""
		for item in self.transfer_items:
			if item.payment_entry:
				frappe.db.set_value("Payment Entry", item.payment_entry, "custom_is_distributed", 0)

	def mark_receive_payment_entries_as_distributed(self):
		"""Mark direct Receive Payment Entries (into Aripov) as distributed"""
		for item in self.receive_items:
			if item.payment_entry:
				frappe.db.set_value("Payment Entry", item.payment_entry, "custom_is_distributed", 1)

	def unmark_receive_payment_entries(self):
		"""Unmark Receive Payment Entries when this document is cancelled"""
		for item in self.receive_items:
			if item.payment_entry:
				frappe.db.set_value("Payment Entry", item.payment_entry, "custom_is_distributed", 0)


def get_account_by_number(account_number, company):
	"""Get account name by account number and company"""
	return frappe.db.get_value(
		"Account",
		{"account_number": account_number, "company": company},
		"name"
	)


@frappe.whitelist()
def get_cash_distribution_data(posting_date, company):
	"""Fetch all data for Cash Distribution Entry

	Now fetches both USD and UZS account balances,
	and converts Hamidulla UZS expenses to USD.
	"""

	# Get exchange rate for UZS → USD conversion (with fallback to latest)
	exchange_rate = get_exchange_rate_with_fallback(posting_date)

	# 1. Get Internal Transfers (Davron → Aripov) for BOTH accounts
	aripov_usd_account = get_account_by_number("1114", company)
	aripov_uzs_account = get_account_by_number("1115", company)
	aripov_accounts = [acc for acc in [aripov_usd_account, aripov_uzs_account] if acc]

	transfer_items = []
	if aripov_accounts:
		transfer_items = frappe.db.sql("""
			SELECT
				pe.name as payment_entry,
				pe.paid_to_account_currency as currency,
				pe.paid_amount as amount,
				pe.paid_from as source_account
			FROM `tabPayment Entry` pe
			WHERE pe.posting_date = %s
				AND pe.payment_type = 'Internal Transfer'
				AND pe.paid_to IN %s
				AND pe.company = %s
				AND pe.docstatus = 1
				AND IFNULL(pe.custom_is_distributed, 0) = 0
			ORDER BY pe.name
		""", (posting_date, aripov_accounts, company), as_dict=True)

	# 2b. Get direct Receive payments INTO Aripov (payment_type = 'Receive').
	# These are NOT internal transfers — money received straight into Aripov cash
	# from a customer/party. Uses received_amount (amount landed in the Aripov account,
	# in the account's own currency).
	receive_items = []
	if aripov_accounts:
		receive_items = frappe.db.sql("""
			SELECT
				pe.name as payment_entry,
				pe.party_type as party_type,
				pe.party as party,
				pe.paid_to_account_currency as currency,
				pe.received_amount as amount,
				pe.paid_from as source_account
			FROM `tabPayment Entry` pe
			WHERE pe.posting_date = %s
				AND pe.payment_type = 'Receive'
				AND pe.paid_to IN %s
				AND pe.company = %s
				AND pe.docstatus = 1
				AND IFNULL(pe.custom_is_distributed, 0) = 0
			ORDER BY pe.name
		""", (posting_date, aripov_accounts, company), as_dict=True)

	# 3. Get Hamidulla Kassa Rasxod (BOTH USD and UZS modes)
	# Only sum items where rasxod_podochot == "Расход" AND party / party_type are empty
	# (party-bound expenses are recorded elsewhere, not as Hamidulla rasxod).
	# items_data stores per-item paid_amount_usd already converted to USD on save.
	rasxod_items = []
	kr_rows = frappe.db.sql("""
		SELECT kr.name, kr.posting_date, kr.items_data
		FROM `tabKassa Rasxod` kr
		WHERE kr.posting_date = %s
			AND kr.mode_of_payment IN %s
			AND kr.docstatus = 1
			AND IFNULL(kr.custom_is_distributed, 0) = 0
		ORDER BY kr.posting_date
	""", (posting_date, tuple(HAMIDULLA_MODES.values())), as_dict=True)

	for kr in kr_rows:
		amount_usd = 0
		if kr.items_data:
			try:
				items = json.loads(kr.items_data)
			except (json.JSONDecodeError, TypeError):
				items = []
			for item in items:
				if (item.get("rasxod_podochot") == "Расход"
						and not item.get("party")
						and not item.get("party_type")):
					amount_usd += flt(item.get("paid_amount_usd"))
		if amount_usd:
			rasxod_items.append({
				"kassa_rasxod": kr.name,
				"posting_date": kr.posting_date,
				"amount_usd": amount_usd,
			})

	# 4. Get BOTH account balances
	from erpnext.accounts.utils import get_balance_on
	aripov_usd_balance = get_balance_on(account=aripov_usd_account, date=posting_date) if aripov_usd_account else 0
	aripov_uzs_balance = get_balance_on(account=aripov_uzs_account, date=posting_date) if aripov_uzs_account else 0

	# 5. Get per-category customer payment totals (informational)
	category_items = []
	for cat in frappe.get_all("Customer Category", pluck="name"):
		customers = frappe.get_all(
			"Customer",
			filters={"custom_customer_category": cat},
			pluck="name",
		)
		total_usd = total_uzs = 0
		if customers:
			rows = frappe.db.sql("""
				SELECT
					pe.paid_to_account_currency AS currency,
					SUM(CASE WHEN pe.paid_to_account_currency = 'UZS'
							 THEN pe.received_amount ELSE pe.paid_amount END) AS total
				FROM `tabPayment Entry` pe
				WHERE pe.posting_date = %s
					AND pe.payment_type = 'Receive'
					AND pe.party_type = 'Customer'
					AND pe.party IN %s
					AND pe.company = %s
					AND pe.docstatus = 1
				GROUP BY pe.paid_to_account_currency
			""", (posting_date, tuple(customers), company), as_dict=True)
			for r in rows:
				if r.currency == "USD":
					total_usd = flt(r.total)
				elif r.currency == "UZS":
					total_uzs = flt(r.total)
		if total_usd or total_uzs:
			category_items.append({
				"category": cat,
				"total_usd": total_usd,
				"total_uzs": total_uzs,
			})

	return {
		"transfer_items": transfer_items,
		"receive_items": receive_items,
		"rasxod_items": rasxod_items,
		"category_items": category_items,
		"aripov_usd_balance": aripov_usd_balance or 0,
		"aripov_uzs_balance": aripov_uzs_balance or 0,
		"exchange_rate": exchange_rate
	}


# Keep the old function for backward compatibility
@frappe.whitelist()
def get_payment_entries(posting_date, company):
	"""Legacy function - kept for backward compatibility"""

	usd_davron_account = get_account_by_number("1110", company)
	uzs_davron_account = get_account_by_number("1111", company)
	usd_aripov_account = get_account_by_number("1114", company)
	uzs_aripov_account = get_account_by_number("1115", company)

	davron_accounts = []
	if usd_davron_account:
		davron_accounts.append(usd_davron_account)
	if uzs_davron_account:
		davron_accounts.append(uzs_davron_account)

	if not davron_accounts:
		frappe.throw(_("No Davron kassa accounts (1110, 1111) found in Company {0}").format(company))

	payment_entries = frappe.db.sql("""
		SELECT
			IFNULL(pe.custom_tranzaksiya_turi, 'No Type') as tranzaksiya_turi,
			pe.paid_to_account_currency as currency,
			CASE
				WHEN pe.paid_to_account_currency = 'USD' THEN %s
				ELSE %s
			END as source_account,
			CASE
				WHEN pe.paid_to_account_currency = 'UZS' THEN SUM(pe.received_amount)
				ELSE SUM(pe.paid_amount)
			END as total_amount,
			COUNT(*) as pe_count
		FROM `tabPayment Entry` pe
		WHERE pe.posting_date = %s
			AND pe.payment_type = 'Receive'
			AND pe.paid_to IN %s
			AND pe.company = %s
			AND pe.docstatus = 1
			AND IFNULL(pe.custom_is_distributed, 0) = 0
		GROUP BY pe.custom_tranzaksiya_turi, pe.paid_to_account_currency
		ORDER BY pe.paid_to_account_currency, pe.custom_tranzaksiya_turi
	""", (usd_aripov_account, uzs_aripov_account, posting_date, davron_accounts, company), as_dict=True)

	return {
		"payment_entries": payment_entries
	}


@frappe.whitelist()
def get_hamidulla_rasxod_detail(kassa_rasxod_names):
	"""Per-item breakdown that forms the Hamidulla Rasxod (USD) total.

	For each linked Kassa Rasxod, parse items_data and return only the "Расход"
	items with no party (investor-covered expenses), exposing where the total
	comes from: schet (cost_center / Счёт), tip1 (category / Тип 1), the native
	amount + its currency, the exchange rate (kurs) and the USD equivalent.
	"""
	if isinstance(kassa_rasxod_names, str):
		try:
			kassa_rasxod_names = json.loads(kassa_rasxod_names)
		except (json.JSONDecodeError, TypeError):
			kassa_rasxod_names = [kassa_rasxod_names] if kassa_rasxod_names else []

	if not kassa_rasxod_names:
		return []

	rows = frappe.db.sql("""
		SELECT name, mode_of_payment, items_data
		FROM `tabKassa Rasxod`
		WHERE name IN %s
	""", (tuple(kassa_rasxod_names),), as_dict=True)

	usd_mode = HAMIDULLA_MODES.get("USD")
	detail = []
	for kr in rows:
		is_usd = kr.mode_of_payment == usd_mode
		currency = "USD" if is_usd else "UZS"
		try:
			items = json.loads(kr.items_data or "[]")
		except (json.JSONDecodeError, TypeError):
			items = []
		for item in items:
			if (item.get("rasxod_podochot") == "Расход"
					and not item.get("party")
					and not item.get("party_type")):
				amount = flt(item.get("paid_amount_usd")) if is_usd else flt(item.get("paid_amount_uzs"))
				detail.append({
					"kassa_rasxod": kr.name,
					"schet": item.get("cost_center") or "",
					"tip1": item.get("category") or "",
					"amount": amount,
					"currency": currency,
					"kurs": flt(item.get("currency_exchange_rate")),
					"amount_usd": flt(item.get("paid_amount_usd")),
				})
	return detail


@frappe.whitelist()
def get_calendar_status(month, year, company=None):
	"""Per-day cash-distribution closure status for a month.

	Har kun uchun: Aripov kassaga tushган INFLOW (Internal Transfer + Receive +
	Hamidulla rasxod) taqsimlanганmi. Undistributed (custom_is_distributed=0)
	qolgan bo'lsa — kun "yopilmagan" (red). Hammasi taqsimlangan + o'sha kunда
	CDE bor bo'lsa — "yopilgan" (green). Faoliyat bo'lmasa — neutral.
	"""
	import calendar as _calendar

	month = int(month)
	year = int(year)
	if not company:
		company = (
			frappe.db.get_single_value("Global Defaults", "default_company")
			or frappe.db.get_value("Company", {}, "name")
		)

	last_day = _calendar.monthrange(year, month)[1]
	start = f"{year:04d}-{month:02d}-01"
	end = f"{year:04d}-{month:02d}-{last_day:02d}"

	aripov_usd = get_account_by_number("1114", company)
	aripov_uzs = get_account_by_number("1115", company)
	aripov_accounts = [a for a in [aripov_usd, aripov_uzs] if a]

	days = {}

	def _day(ds):
		return days.setdefault(ds, {"undist_usd": 0.0, "undist_uzs": 0.0, "hamidulla": 0.0})

	# Undistributed transfers + receives into Aripov
	if aripov_accounts:
		rows = frappe.db.sql(
			"""
			SELECT posting_date AS pd, paid_to_account_currency AS ccy,
				   SUM(CASE WHEN paid_to_account_currency='UZS' THEN received_amount ELSE paid_amount END) AS amt
			FROM `tabPayment Entry`
			WHERE payment_type IN ('Internal Transfer', 'Receive')
			  AND paid_to IN %(acc)s AND company = %(co)s AND docstatus = 1
			  AND IFNULL(custom_is_distributed, 0) = 0
			  AND posting_date BETWEEN %(s)s AND %(e)s
			GROUP BY posting_date, paid_to_account_currency
			""",
			{"acc": tuple(aripov_accounts), "co": company, "s": start, "e": end},
			as_dict=True,
		)
		for r in rows:
			rec = _day(str(r.pd))
			if r.ccy == "USD":
				rec["undist_usd"] += flt(r.amt)
			else:
				rec["undist_uzs"] += flt(r.amt)

	# Undistributed Hamidulla rasxod (Kassa Rasxod, faqat "Расход" party'siz itemlar)
	kr_rows = frappe.db.sql(
		"""
		SELECT posting_date AS pd, items_data
		FROM `tabKassa Rasxod`
		WHERE mode_of_payment IN %(modes)s AND docstatus = 1
		  AND IFNULL(custom_is_distributed, 0) = 0
		  AND posting_date BETWEEN %(s)s AND %(e)s
		""",
		{"modes": tuple(HAMIDULLA_MODES.values()), "s": start, "e": end},
		as_dict=True,
	)
	for kr in kr_rows:
		usd = 0.0
		try:
			items = json.loads(kr.items_data or "[]")
		except (json.JSONDecodeError, TypeError):
			items = []
		for it in items:
			if (it.get("rasxod_podochot") == "Расход"
					and not it.get("party") and not it.get("party_type")):
				usd += flt(it.get("paid_amount_usd"))
		if usd:
			rec = _day(str(kr.pd))
			rec["undist_usd"] += usd
			rec["hamidulla"] += usd

	# Days with a submitted CDE
	cde_days = {
		str(d) for d in frappe.get_all(
			"Cash Distribution Entry",
			filters={"docstatus": 1, "company": company, "posting_date": ["between", [start, end]]},
			pluck="posting_date",
		)
	}

	out = {}
	for day in range(1, last_day + 1):
		ds = f"{year:04d}-{month:02d}-{day:02d}"
		rec = days.get(ds)
		has_cde = ds in cde_days
		if rec and (rec["undist_usd"] > 0.01 or rec["undist_uzs"] > 0.01):
			status = "red"
		elif has_cde:
			status = "green"
		else:
			status = "neutral"
		out[ds] = {
			"status": status,
			"undist_usd": round(rec["undist_usd"], 2) if rec else 0,
			"undist_uzs": round(rec["undist_uzs"], 2) if rec else 0,
			"hamidulla": round(rec["hamidulla"], 2) if rec else 0,
			"has_cde": has_cde,
		}
	return out
