# Copyright (c) 2025, Asadbek and contributors
# For license information, please see license.txt

"""
Podochot Processor

Handles Podochot prixod (employee returns money) and
Podochot rasxod (employee receives money) Journal Entry creation.
"""

import frappe
from frappe import _

from akfa_accounting2.akfa_accounting2.doctype.kassa_rasxod.services.base_je_creator import (
    BaseJECreator,
)


class PodochotProcessor(BaseJECreator):
    """Processor for Podochot prixod/rasxod Journal Entries"""

    def _employee_payable_account(self):
        """Employee creditor account by cash currency: 2120 (USD), 2121 (UZS)."""
        account_number = "2121" if self.is_multi_currency else "2120"
        account = frappe.db.get_value(
            "Account",
            {"account_number": account_number, "company": self.company},
            "name",
        )
        if not account:
            frappe.throw(
                _("Employee creditor account {0} not found for company {1}").format(
                    account_number, self.company
                )
            )
        return account

    def process_podochot_prixod_item(self, item, idx):
        """
        Process Podochot prixod - Employee returns money to cash
        Creates 2-line JE: Debit Cash, Credit Payable with Employee
        """
        self._set_item_context(item)
        employee = item.get('employee')
        if not employee:
            return

        amount = self._get_amount(item)
        if not amount and not self._get_usd_amount(item):
            return

        izoh = item.get('izoh', '')
        je = self._create_journal_entry()
        je.user_remark = f"Podochot Prixod - Auto-created from Kassa Rasxod {self.doc.name}, Row #{idx}. {izoh}"

        # Debit Cash (money comes in)
        self._add_account_entry(je, self.cash_account, debit=amount)
        # Credit Employee Creditor account (2120 USD / 2121 UZS)
        self._add_account_entry(je, self._employee_payable_account(), credit=amount,
                                party_type="Employee", party=employee)

        je.insert()
        je.submit()

        frappe.msgprint(
            _("Journal Entry {0} created for Podochot Prixod Row #{1}, Employee {2}").format(
                frappe.utils.get_link_to_form("Journal Entry", je.name), idx, employee
            )
        )
        return je.name

    def process_podochot_rasxod_item(self, item, idx):
        """
        Process Podochot rasxod - Employee receives money from cash
        Creates 2-line JE: Debit Payable with Employee, Credit Cash
        """
        self._set_item_context(item)
        employee = item.get('employee')
        if not employee:
            return

        amount = self._get_amount(item)
        if not amount and not self._get_usd_amount(item):
            return

        izoh = item.get('izoh', '')
        je = self._create_journal_entry()
        je.user_remark = f"Podochot Rasxod - Auto-created from Kassa Rasxod {self.doc.name}, Row #{idx}. {izoh}"

        # Debit Employee Creditor account (2120 USD / 2121 UZS)
        self._add_account_entry(je, self._employee_payable_account(), debit=amount,
                                party_type="Employee", party=employee)
        # Credit Cash (money goes out)
        self._add_account_entry(je, self.cash_account, credit=amount)

        je.insert()
        je.submit()

        frappe.msgprint(
            _("Journal Entry {0} created for Podochot Rasxod Row #{1}, Employee {2}").format(
                frappe.utils.get_link_to_form("Journal Entry", je.name), idx, employee
            )
        )
        return je.name
