import unittest

from akfa_accounting2.akfa_accounting2.doctype.cash_distribution_entry.cash_distribution_entry import (
	round_uzs_distribution_amount,
)


class TestCashDistributionEntry(unittest.TestCase):
	def test_rounds_usd_to_uzs_distribution_to_nearest_thousand(self):
		self.assertEqual(round_uzs_distribution_amount(150018.40), 150000)
		self.assertEqual(round_uzs_distribution_amount(150500), 151000)
