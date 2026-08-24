app_name = "akfa_accounting2"
app_title = "akfa_accounting2"
app_publisher = "Asadbek"
app_description = "akfa_accounting2"
app_email = "asadbek.backend@gmail.com"
app_license = "mit"

doctype_js = {
	"Payment Entry": "public/js/payment_entry.js",
	"Travel Request": "public/js/travel_request.js",
	"Expense Claim": "public/js/expense_claim.js",
	"Kassa Rasxod": [
		"public/js/kassa_rasxod/state.js",
		"public/js/kassa_rasxod/loaders.js",
		"public/js/kassa_rasxod/calc.js",
		"public/js/kassa_rasxod/render.js",
		"public/js/kassa_rasxod/handlers.js",
	],
}

app_include_js = ["/assets/akfa_accounting2/js/pwa_init.js"]

fixtures = [
	{
		"dt": "Custom Field",
		"filters": [["dt", "in", ["Payment Entry", "Vehicle", "Travel Request", "Employee Advance", "Expense Claim", "Project", "Expense Claim Detail", "Customer", "Journal Entry"]]],
	},
	{
		"dt": "Property Setter",
		"filters": [["doc_type", "in", ["Project", "Vehicle", "Travel Request", "Expense Claim", "Expense Claim Detail", "Payment Entry", "Employee Group"]]],
	},
	{
		"dt": "List View Settings",
		"filters": [["name", "in", ["Payment Entry"]]],
	},
	{
		"dt": "Print Format",
		"filters": [["module", "=", "akfa_accounting2"]],
	},
	{
		"dt": "Workspace",
		"filters": [["module", "=", "akfa_accounting2"]],
	},
]

permission_query_conditions = {
	"Trip Master": "akfa_accounting2.akfa_accounting2.doctype.trip_master.trip_master.get_permission_query_conditions",
}

has_permission = {
	"Trip Master": "akfa_accounting2.akfa_accounting2.doctype.trip_master.trip_master.has_permission",
}

doc_events = {
	"Payment Entry": {
		"validate": "akfa_accounting2.validations.payment_entry.validate_payment_entry",
		"before_submit": "akfa_accounting2.validations.payment_entry.block_internal_transfer_submit",
	},
	"Expense Claim": {
		"validate": "akfa_accounting2.validations.expense_claim.validate_trip_membership",
	},
	"Employee Advance": {
		"on_submit": "akfa_accounting2.events.employee_advance.auto_create_payment_entry",
	}
}

on_login = "akfa_accounting2.events.login_redirect.redirect_employee"
