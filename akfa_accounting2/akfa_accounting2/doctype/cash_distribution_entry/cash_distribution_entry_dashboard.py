from frappe import _


def get_data():
	return {
		"fieldname": "custom_cash_distribution_entry",
		"transactions": [
			{"label": _("Accounting"), "items": ["Journal Entry"]},
		],
	}
