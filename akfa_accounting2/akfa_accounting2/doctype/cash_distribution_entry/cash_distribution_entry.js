// Copyright (c) 2025, Asadbek and contributors
// For license information, please see license.txt

frappe.ui.form.on("Cash Distribution Entry", {
	setup(frm) {
		// Only allow suppliers in the "Zavodlar" supplier group
		frm.set_query("supplier", "distribution_details", function() {
			return { filters: { supplier_group: "Zavodlar" } };
		});
	},

	refresh(frm) {
		// Add custom button to fetch data
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Fetch Data"), function() {
				frm.trigger("fetch_all_data");
			});
		}

		// Grid footer: USD Ekvivalent jami (mavjud hujjatlar uchun ham)
		render_usd_ekvivalent_total(frm);

		// Hamidulla Rasxod tafsiloti (drill-down) tugmasi
		render_hamidulla_detail(frm);

		// Show link to Journal Entries if exists
		if (frm.doc.journal_entry) {
			frm.add_custom_button(__("View Journal Entries"), function() {
				let entries = frm.doc.journal_entry.split(", ");
				if (entries.length === 1) {
					frappe.set_route("Form", "Journal Entry", entries[0]);
				} else {
					frappe.set_route("List", "Journal Entry", {
						name: ["in", entries]
					});
				}
			});
		}
	},

	posting_date(frm) {
		if (frm.doc.posting_date && frm.doc.company) {
			frm.trigger("fetch_all_data");
		}
	},

	company(frm) {
		// Clear balances when company changes
		frm.set_value("aripov_usd_balance", 0);
		frm.set_value("aripov_uzs_balance", 0);
	},

	fetch_all_data(frm) {
		if (!frm.doc.posting_date || !frm.doc.company) {
			frappe.msgprint(__("Please select Posting Date and Company first"));
			return;
		}

		frappe.call({
			method: "akfa_accounting2.akfa_accounting2.doctype.cash_distribution_entry.cash_distribution_entry.get_cash_distribution_data",
			args: {
				posting_date: frm.doc.posting_date,
				company: frm.doc.company
			},
			freeze: true,
			freeze_message: __("Fetching Data..."),
			callback: function(r) {
				if (r.message) {
					// Set account balances
					frm.set_value("aripov_usd_balance", r.message.aripov_usd_balance || 0);
					frm.set_value("aripov_uzs_balance", r.message.aripov_uzs_balance || 0);
					frm.set_value("kurs", r.message.exchange_rate || 0);

					// Clear existing items
					frm.clear_table("transfer_items");
					frm.clear_table("receive_items");
					frm.clear_table("rasxod_items");
					frm.clear_table("category_summary");

					// 2. Populate Internal Transfers
					if (r.message.transfer_items && r.message.transfer_items.length > 0) {
						r.message.transfer_items.forEach(function(item) {
							let row = frm.add_child("transfer_items");
							row.payment_entry = item.payment_entry;
							row.currency = item.currency;
							row.amount = item.amount;
							row.source_account = item.source_account;
						});
					}

					// 2b. Populate direct Receive payments into Aripov
					if (r.message.receive_items && r.message.receive_items.length > 0) {
						r.message.receive_items.forEach(function(item) {
							let row = frm.add_child("receive_items");
							row.payment_entry = item.payment_entry;
							row.party_type = item.party_type;
							row.party = item.party;
							row.currency = item.currency;
							row.amount = item.amount;
							row.source_account = item.source_account;
						});
					}

					// 3. Populate Hamidulla Kassa Rasxod (all converted to USD)
					if (r.message.rasxod_items && r.message.rasxod_items.length > 0) {
						r.message.rasxod_items.forEach(function(item) {
							let row = frm.add_child("rasxod_items");
							row.posting_date = item.posting_date;
							row.kassa_rasxod = item.kassa_rasxod;
							row.amount_usd = item.amount_usd;
						});
					}

					// 4. Populate Category Summary (informational)
					if (r.message.category_items && r.message.category_items.length > 0) {
						r.message.category_items.forEach(function(item) {
							let row = frm.add_child("category_summary");
							row.category = item.category;
							row.total_usd = item.total_usd;
							row.total_uzs = item.total_uzs;
						});
					}

					frm.refresh_field("transfer_items");
					frm.refresh_field("receive_items");
					frm.refresh_field("rasxod_items");
					frm.refresh_field("category_summary");
					frm.trigger("calculate_totals");
					render_hamidulla_detail(frm);

					// Show summary
					let transfer_count = (r.message.transfer_items || []).length;
					let receive_count = (r.message.receive_items || []).length;
					let rasxod_count = (r.message.rasxod_items || []).length;
					frappe.show_alert({
						message: __("Data fetched: {0} transfers, {1} receive, {2} rasxod entries", [transfer_count, receive_count, rasxod_count]),
						indicator: "green"
					});
				}
			}
		});
	},

	// Legacy function for backward compatibility
	fetch_payment_entries(frm) {
		frm.trigger("fetch_all_data");
	},

	calculate_totals(frm) {
		// Internal Transfers TO ARIPOV
		let internal_transfers_usd = 0;
		let internal_transfers_uzs = 0;
		(frm.doc.transfer_items || []).forEach(function(item) {
			if (item.currency === "USD") {
				internal_transfers_usd += flt(item.amount);
			} else if (item.currency === "UZS") {
				internal_transfers_uzs += flt(item.amount);
			}
		});
		frm.set_value("internal_transfers_usd", internal_transfers_usd);
		frm.set_value("internal_transfers_uzs", internal_transfers_uzs);

		// Hamidulla Kassa Rasxod (all converted to USD)
		let hamidulla_rasxod_usd = 0;
		(frm.doc.rasxod_items || []).forEach(function(item) {
			hamidulla_rasxod_usd += flt(item.amount_usd);
		});
		frm.set_value("hamidulla_rasxod_usd", hamidulla_rasxod_usd);

		// Payment Entry Receive TO ARIPOV
		let receive_total_usd = 0;
		let receive_total_uzs = 0;
		(frm.doc.receive_items || []).forEach(function(item) {
			if (item.currency === "USD") {
				receive_total_usd += flt(item.amount);
			} else if (item.currency === "UZS") {
				receive_total_uzs += flt(item.amount);
			}
		});
		frm.set_value("receive_total_usd", receive_total_usd);
		frm.set_value("receive_total_uzs", receive_total_uzs);

		// ARIPOV TOTAL = Internal Transfers + Hamidulla Rasxod + Receive
		let aripov_total_usd = internal_transfers_usd + hamidulla_rasxod_usd + receive_total_usd;
		let aripov_total_uzs = internal_transfers_uzs + receive_total_uzs;
		frm.set_value("aripov_total_usd", aripov_total_usd);
		frm.set_value("aripov_total_uzs", aripov_total_uzs);

		// Total Distributed (from distribution_details)
		let total_distributed_usd = 0;
		let total_distributed_uzs = 0;
		(frm.doc.distribution_details || []).forEach(function(item) {
			if (item.currency === "USD") {
				total_distributed_usd += flt(item.amount);
			} else if (item.currency === "UZS") {
				total_distributed_uzs += flt(item.amount);
			}
		});
		frm.set_value("total_distributed_usd", total_distributed_usd);
		frm.set_value("total_distributed_uzs", total_distributed_uzs);

		// Grid footer: USD Ekvivalent ustuni jami (UZS ham konvert qilingan)
		render_usd_ekvivalent_total(frm);

		// Difference = Aripov Total - Distributed (must be >= 0)
		frm.set_value("difference_usd", aripov_total_usd - total_distributed_usd);
		frm.set_value("difference_uzs", aripov_total_uzs - total_distributed_uzs);

		// Keep legacy fields for backward compatibility
		frm.set_value("total_received_usd", aripov_total_usd);
		frm.set_value("total_received_uzs", aripov_total_uzs);
	}
});

frappe.ui.form.on("Cash Distribution Detail", {
	supplier(frm, cdt, cdn) {
		let row = frappe.get_doc(cdt, cdn);
		if (row.supplier && frm.doc.company) {
			// Fetch party_currency from the Supplier's billing currency
			frappe.call({
				method: "frappe.client.get_value",
				args: {
					doctype: "Supplier",
					filters: { name: row.supplier },
					fieldname: "default_currency"
				},
				callback: function(r) {
					if (r.message && r.message.default_currency) {
						frappe.model.set_value(cdt, cdn, "party_currency", r.message.default_currency);

						// Set creditors account based on party_currency
						let account_number = r.message.default_currency === "USD" ? "2110" : "2111";
						frappe.call({
							method: "frappe.client.get_value",
							args: {
								doctype: "Account",
								filters: {
									account_number: account_number,
									company: frm.doc.company
								},
								fieldname: "name"
							},
							callback: function(acc_r) {
								if (acc_r.message) {
									frappe.model.set_value(cdt, cdn, "creditors_account", acc_r.message.name);
								}
							}
						});
					}
				}
			});
		}
	},

	currency(frm, cdt, cdn) {
		let row = frappe.get_doc(cdt, cdn);

		// If currency changed and amount exists, recalculate USD equivalent
		if (flt(row.amount) > 0) {
			if (row.currency === "UZS") {
				convert_uzs_to_usd(frm, cdt, cdn, row.amount);
			} else if (row.currency === "USD") {
				// USD to USD - same value
				frappe.model.set_value(cdt, cdn, "usd_ekvivalent", row.amount);
			}
		}

		frm.trigger("calculate_totals");
	},

	amount(frm, cdt, cdn) {
		let row = frappe.get_doc(cdt, cdn);
		let amount = flt(row.amount);

		if (amount <= 0) {
			frappe.model.set_value(cdt, cdn, "usd_ekvivalent", 0);
			frm.trigger("calculate_totals");
			return;
		}

		if (row.currency === "UZS") {
			// UZS amount entered, convert to USD
			convert_uzs_to_usd(frm, cdt, cdn, amount);
		} else if (row.currency === "USD") {
			// USD to USD - same value
			frappe.model.set_value(cdt, cdn, "usd_ekvivalent", amount);
		}

		frm.trigger("calculate_totals");
	},

	distribution_details_add(frm, cdt, cdn) {
		// Default to USD
		frappe.model.set_value(cdt, cdn, "currency", "USD");
	},

	distribution_details_remove(frm) {
		frm.trigger("calculate_totals");
	}
});

function render_hamidulla_detail(frm) {
	// "Hamidulla Rasxod (USD)" summasi qayerdan shakllanganini ko'rsatuvchi
	// ochib-yopiladigan (drill-down) jadval.
	let field = frm.get_field("hamidulla_rasxod_detail");
	if (!field || !field.$wrapper) return;

	let $wrapper = field.$wrapper;
	$wrapper.empty();

	let kr_names = (frm.doc.rasxod_items || [])
		.map((r) => r.kassa_rasxod)
		.filter(Boolean);
	if (!kr_names.length) return;

	let $btn = $(
		`<button class="btn btn-xs btn-default" style="margin:2px 0 8px;">` +
			__("Hamidulla rasxod tafsilotini ko'rsatish") +
			` <span class="hd-arrow">▼</span></button>`
	);
	let $box = $(`<div class="hamidulla-detail-box" style="display:none;"></div>`);
	$wrapper.append($btn).append($box);

	let loaded = false;
	$btn.on("click", function () {
		if ($box.is(":visible")) {
			$box.hide();
			$btn.find(".hd-arrow").text("▼");
			return;
		}
		$box.show();
		$btn.find(".hd-arrow").text("▲");
		if (loaded) return;
		frappe.call({
			method: "akfa_accounting2.akfa_accounting2.doctype.cash_distribution_entry.cash_distribution_entry.get_hamidulla_rasxod_detail",
			args: { kassa_rasxod_names: JSON.stringify(kr_names) },
			callback: function (r) {
				$box.html(build_hamidulla_table(r.message || []));
				loaded = true;
			},
		});
	});
}

function build_hamidulla_table(rows) {
	if (!rows.length) {
		return `<div class="text-muted" style="padding:8px;">${__("Ma'lumot yo'q")}</div>`;
	}
	const cell = "padding:6px 8px;border:1px solid #e5e5e5;";
	let total_usd = 0;
	let body = "";
	rows.forEach(function (r) {
		total_usd += flt(r.amount_usd);
		let amt = format_number(r.amount, null, r.currency === "USD" ? 2 : 0);
		body +=
			`<tr>` +
			`<td style="${cell}">${frappe.utils.escape_html(r.kassa_rasxod || "")}</td>` +
			`<td style="${cell}">${frappe.utils.escape_html(r.schet || "")}</td>` +
			`<td style="${cell}">${frappe.utils.escape_html(r.tip1 || "")}</td>` +
			`<td style="${cell}text-align:right;">${amt}</td>` +
			`<td style="${cell}text-align:center;">${frappe.utils.escape_html(r.currency || "")}</td>` +
			`<td style="${cell}text-align:right;">${format_number(r.kurs)}</td>` +
			`<td style="${cell}text-align:right;color:#2e7d32;">${format_currency(r.amount_usd, "USD")}</td>` +
			`</tr>`;
	});
	return (
		`<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:12px;">` +
		`<thead><tr style="background:#f5f5f5;">` +
		`<th style="${cell}text-align:left;">Kassa Rasxod</th>` +
		`<th style="${cell}text-align:left;">Счёт</th>` +
		`<th style="${cell}text-align:left;">Тип 1</th>` +
		`<th style="${cell}text-align:right;">Сумма</th>` +
		`<th style="${cell}text-align:center;">Валюта</th>` +
		`<th style="${cell}text-align:right;">Курс</th>` +
		`<th style="${cell}text-align:right;">$ qiymati</th>` +
		`</tr></thead>` +
		`<tbody>${body}</tbody>` +
		`<tfoot><tr style="background:#f5f5f5;font-weight:bold;">` +
		`<td colspan="6" style="${cell}text-align:right;">${__("Jami (USD)")}</td>` +
		`<td style="${cell}text-align:right;color:#2e7d32;">${format_currency(total_usd, "USD")}</td>` +
		`</tr></tfoot>` +
		`</table></div>`
	);
}

function render_usd_ekvivalent_total(frm) {
	let field = frm.fields_dict.distribution_details;
	let grid = field && field.grid;
	if (!grid || !grid.wrapper) return;

	let total = 0;
	(frm.doc.distribution_details || []).forEach(function(item) {
		total += flt(item.usd_ekvivalent);
	});

	let $footer = grid.wrapper.find(".grid-footer");
	if (!$footer.length) return;

	let $el = $footer.find(".usd-ekv-total");
	if (!$el.length) {
		$el = $("<div class='usd-ekv-total' style='text-align:right; font-weight:bold; padding:6px 10px; color:#2c3e50;'></div>");
		$footer.append($el);
	}
	$el.html(__("USD Ekvivalent jami: {0}", [format_currency(total, "USD")]));
}

function convert_uzs_to_usd(frm, cdt, cdn, uzs_amount) {
	// Convert UZS to USD
	frappe.call({
		method: "akfa_accounting2.akfa_accounting2.api.payment_entry_api.get_daily_exchange_rates",
		args: {
			date: frm.doc.posting_date
		},
		callback: function(r) {
			if (r.message && r.message.usd_to_uzs) {
				let exchange_rate = flt(r.message.usd_to_uzs);
				if (exchange_rate > 0) {
					let usd_amount = flt(uzs_amount / exchange_rate, 2);

					// Set USD equivalent
					frappe.model.set_value(cdt, cdn, "usd_ekvivalent", usd_amount);

					frappe.show_alert({
						message: __("{0} UZS → {1} USD (Kurs: {2})", [
							format_number(uzs_amount),
							format_number(usd_amount, null, 2),
							format_number(exchange_rate)
						]),
						indicator: "green"
					}, 5);

					frm.trigger("calculate_totals");
				}
			} else {
				frappe.msgprint({
					title: __("Kurs topilmadi"),
					message: __("{0} sanasi uchun valyuta kursi mavjud emas.", [frm.doc.posting_date]),
					indicator: "red"
				});
			}
		}
	});
}
