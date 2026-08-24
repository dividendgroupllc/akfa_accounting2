// Copyright (c) 2026, Asadbek and contributors
// For license information, please see license.txt

frappe.query_reports["Aripov Kunlik Qoldiq"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.add_days(frappe.datetime.get_today(), -30),
			"reqd": 1
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 1
		},
		{
			"fieldname": "company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"default": frappe.defaults.get_user_default("Company")
		},
		{
			"fieldname": "currency",
			"label": __("Currency"),
			"fieldtype": "Link",
			"options": "Currency",
			"get_query": function() {
				return { filters: { "name": ["in", ["USD", "UZS"]] } };
			}
		}
	],

	"formatter": function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		// Opening row + bold rows
		if (data.bold) {
			value = "<strong>" + value + "</strong>";
		}

		// Kumulativ qoldiq: musbat bo'lsa qizil (qotib qolgan pul)
		if (column.fieldname === "kumulativ_qoldiq" && flt(data.kumulativ_qoldiq) > 0) {
			value = "<span style='color: #e74c3c; font-weight: bold;'>" + value + "</span>";
		}
		// Kunlik qoldiq: musbat (sochilmagan) sariq, manfiy (carryover sochildi) yashil
		if (column.fieldname === "kunlik_qoldiq" && data.is_opening !== 1) {
			if (flt(data.kunlik_qoldiq) > 0) {
				value = "<span style='color: #e67e22;'>" + value + "</span>";
			} else if (flt(data.kunlik_qoldiq) < 0) {
				value = "<span style='color: #27ae60;'>" + value + "</span>";
			}
		}

		return value;
	}
};
