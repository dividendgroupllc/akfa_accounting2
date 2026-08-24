# Copyright (c) 2025, Asadbek and contributors
# For license information, please see license.txt

"""
Nachislenie Entry Helpers

Contains helper methods for adding Nachislenie-specific Journal Entry rows.
Used by RasxodProcessor for accrual accounting entries.
"""


class NachislenieMixin:
    """Mixin class providing nachislenie entry creation methods"""

    def _add_nachislenie_payment_entries_with_party(self, je, amount, usd_amount, party_type, party,
                                                     nachislenie_supplier):
        """Add 4-row entries for nachislenie payment with party"""
        # Row 1: Credit Payable with original Party (in party's currency)
        self._add_party_payable_entry(je, party_type, party, amount, usd_amount, credit=True)
        # Row 2: Debit Cash
        self._add_account_entry(je, self.cash_account, debit=amount)
        # Row 3: Credit Cash
        self._add_account_entry(je, self.cash_account, credit=amount)
        # Row 4: Debit Payable with Nachisleniya supplier (in its own currency)
        self._add_party_payable_entry(je, "Supplier", nachislenie_supplier, amount, usd_amount, debit=True)

    def _add_nachislenie_payment_entries_without_party(self, je, amount, usd_amount, nachislenie_supplier):
        """Add 2-row entries for nachislenie payment without party"""
        # Debit Payable with Nachisleniya supplier (in its own currency)
        self._add_party_payable_entry(je, "Supplier", nachislenie_supplier, amount, usd_amount, debit=True)
        # Credit Cash
        self._add_account_entry(je, self.cash_account, credit=amount)

    def _add_nachislenie_accrual_entries(self, je, amount, usd_amount, expense_account,
                                          expense_cost_center, nachislenie_supplier):
        """Add 2-row entries for nachislenie accrual"""
        # Credit Payable with Nachisleniya supplier (in its own currency)
        self._add_party_payable_entry(je, "Supplier", nachislenie_supplier, amount, usd_amount, credit=True)
        # Debit Expense (USD account)
        self._add_account_entry(je, expense_account, debit=usd_amount,
                                cost_center=expense_cost_center, use_usd_rate=True)
