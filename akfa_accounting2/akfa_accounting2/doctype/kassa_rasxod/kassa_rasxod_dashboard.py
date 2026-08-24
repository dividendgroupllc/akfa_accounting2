from frappe import _


def get_data():
	return {
		"fieldname": "custom_kassa_rasxod",
		"transactions": [
			{"label": _("Accounting"), "items": ["Journal Entry"]},
		],
	}
