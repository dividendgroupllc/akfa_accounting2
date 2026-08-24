// Cash Distribution Kalendar — har kun "yopilgan" (yashil) yoki "yopilmagan/osilib
// qolgan" (qizil). Aripov inflow (transfer + receive + hamidulla rasxod) o'sha kunда
// to'liq taqsimlanган bo'lsa yashil; undistributed qolsa qizil.

frappe.pages["cash-distribution-calendar"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Cash Distribution Kalendar"),
		single_column: true,
	});

	const today = frappe.datetime.now_date();
	const MONTHS = [
		"01 - Yanvar", "02 - Fevral", "03 - Mart", "04 - Aprel", "05 - May", "06 - Iyun",
		"07 - Iyul", "08 - Avgust", "09 - Sentabr", "10 - Oktabr", "11 - Noyabr", "12 - Dekabr",
	];
	const WEEK = ["Du", "Se", "Cho", "Pa", "Ju", "Sha", "Ya"];

	const year_field = page.add_field({
		fieldname: "year", label: __("Yil"), fieldtype: "Int",
		default: cint(today.split("-")[0]),
	});
	const month_field = page.add_field({
		fieldname: "month", label: __("Oy"), fieldtype: "Select",
		options: MONTHS, default: MONTHS[cint(today.split("-")[1]) - 1],
	});
	const company_field = page.add_field({
		fieldname: "company", label: __("Kompaniya"), fieldtype: "Link", options: "Company",
	});

	const $body = $(`<div class="cdc-wrap" style="padding:16px;"></div>`).appendTo(page.body);

	function selected() {
		return {
			year: cint(year_field.get_value()) || cint(today.split("-")[0]),
			month: (MONTHS.indexOf(month_field.get_value()) + 1) || cint(today.split("-")[1]),
			company: company_field.get_value() || undefined,
		};
	}

	function money(v) {
		v = flt(v);
		return v ? v.toLocaleString("en-US", { maximumFractionDigits: 2 }) : "0";
	}

	function render(data) {
		const s = selected();
		const first = new Date(s.year, s.month - 1, 1);
		const startOffset = (first.getDay() + 6) % 7; // Monday-first
		const daysInMonth = new Date(s.year, s.month, 0).getDate();

		// To'yingan (vivid) ranglar — to'q fon + oq matn, darrov ko'zga tashlanadi.
		const COLORS = {
			green: { bg: "#2e9e4b", br: "#1e7e34", txt: "#ffffff" },
			red: { bg: "#e53935", br: "#b02a25", txt: "#ffffff" },
			neutral: { bg: "#f4f5f7", br: "#dfe1e6", txt: "#9aa0a6" },
		};

		let html = `<div style="display:flex;gap:16px;margin-bottom:12px;font-size:13px;align-items:center;">
			<span><span style="display:inline-block;width:12px;height:12px;background:${COLORS.green.bg};border:2px solid ${COLORS.green.br};border-radius:3px;vertical-align:middle;"></span> Yopilgan</span>
			<span><span style="display:inline-block;width:12px;height:12px;background:${COLORS.red.bg};border:2px solid ${COLORS.red.br};border-radius:3px;vertical-align:middle;"></span> Yopilmagan (osilib qolgan)</span>
			<span><span style="display:inline-block;width:12px;height:12px;background:${COLORS.neutral.bg};border:2px solid ${COLORS.neutral.br};border-radius:3px;vertical-align:middle;"></span> Faoliyat yo'q</span>
		</div>`;

		html += `<table style="width:100%;border-collapse:separate;border-spacing:6px;table-layout:fixed;">`;
		html += `<thead><tr>` + WEEK.map((w) =>
			`<th style="text-align:center;font-size:12px;color:#5f6368;padding:2px;">${w}</th>`).join("") + `</tr></thead><tbody><tr>`;

		let col = 0;
		for (let i = 0; i < startOffset; i++) { html += `<td></td>`; col++; }

		for (let day = 1; day <= daysInMonth; day++) {
			const ds = `${s.year}-${String(s.month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
			const info = data[ds] || { status: "neutral", undist_usd: 0, undist_uzs: 0, hamidulla: 0, has_cde: false };
			const c = COLORS[info.status] || COLORS.neutral;
			let sub = "";
			if (info.status === "red") {
				sub = `<div style="font-size:11px;font-weight:600;margin-top:4px;color:${c.txt};line-height:1.25;">`;
				if (info.undist_usd) sub += `$${money(info.undist_usd)}<br>`;
				if (info.undist_uzs) sub += `${money(info.undist_uzs)} so'm`;
				sub += `</div>`;
			} else if (info.status === "green") {
				sub = `<div style="font-size:20px;margin-top:2px;color:${c.txt};line-height:1;">✓</div>`;
			}
			const shadow = info.status === "neutral" ? "none" : "0 1px 4px rgba(0,0,0,.20)";
			html += `<td>
				<div class="cdc-day" data-date="${ds}" data-status="${info.status}"
					style="cursor:pointer;min-height:66px;border:2px solid ${c.br};background:${c.bg};
					border-radius:8px;padding:6px 8px;box-shadow:${shadow};transition:transform .05s;">
					<div style="font-weight:700;font-size:15px;color:${c.txt};">${day}</div>
					${sub}
				</div>
			</td>`;
			col++;
			if (col % 7 === 0) html += `</tr><tr>`;
		}
		html += `</tr></tbody></table>`;
		$body.html(html);

		$body.find(".cdc-day").on("click", function () {
			const ds = $(this).data("date");
			const info = data[ds] || {};
			show_day_dialog(ds, info);
		});
	}

	function show_day_dialog(ds, info) {
		const s = selected();
		let msg = `<div style="font-size:13px;">`;
		if (info.status === "red") {
			msg += `<p style="color:#c5221f;font-weight:600;">Yopilmagan — taqsimlanmagan (osilib qolgan) summa:</p><ul>`;
			if (info.undist_usd) msg += `<li>USD: <b>$${money(info.undist_usd)}</b>${info.hamidulla ? ` (shundan Hamidulla: $${money(info.hamidulla)})` : ""}</li>`;
			if (info.undist_uzs) msg += `<li>UZS: <b>${money(info.undist_uzs)} so'm</b></li>`;
			msg += `</ul><p>Yopish uchun shu sanaga Cash Distribution Entry yarating/qayta oching.</p>`;
		} else if (info.status === "green") {
			msg += `<p style="color:#137333;font-weight:600;">✓ To'liq yopilgan — barcha pul taqsimlangan.</p>`;
		} else {
			msg += `<p style="color:#5f6368;">Bu kunда Aripov inflow yo'q.</p>`;
		}
		msg += `</div>`;

		const d = new frappe.ui.Dialog({
			title: frappe.datetime.str_to_user(ds),
			primary_action_label: info.status === "red" ? __("CDE yaratish") : __("CDE'larni ko'rish"),
			primary_action() {
				d.hide();
				if (info.status === "red") {
					frappe.new_doc("Cash Distribution Entry", { posting_date: ds, company: s.company });
				} else {
					frappe.set_route("List", "Cash Distribution Entry", { posting_date: ds });
				}
			},
		});
		d.$body.html(msg);
		d.show();
	}

	function refresh() {
		const s = selected();
		$body.html(`<div class="text-muted" style="padding:24px;">Yuklanmoqda...</div>`);
		frappe.call({
			method: "akfa_accounting2.akfa_accounting2.doctype.cash_distribution_entry.cash_distribution_entry.get_calendar_status",
			args: { month: s.month, year: s.year, company: s.company },
			callback: function (r) { render(r.message || {}); },
		});
	}

	year_field.$input.on("change", refresh);
	month_field.$input.on("change", refresh);
	company_field.$input.on("change", refresh);
	page.set_primary_action(__("Yangilash"), refresh, "refresh");

	refresh();
};
