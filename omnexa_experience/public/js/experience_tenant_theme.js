frappe.ui.form.on("Experience Tenant Theme", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Preview Head"), async () => {
			const r = await frappe.call({
				method: "omnexa_experience.omnexa_experience.web_theme.preview_theme_head",
				args: { theme: frm.doc.name, company: frm.doc.company },
			});
			const out = r.message || {};
			frappe.msgprint({
				title: __("Theme Preview"),
				indicator: "blue",
				message: `<pre style="white-space:pre-wrap">${frappe.utils.escape_html(out.head_html || "")}</pre>`,
				wide: true,
			});
		});

		frm.add_custom_button(__("Publish"), async () => {
			await frappe.call({
				method: "omnexa_experience.omnexa_experience.doctype.experience_tenant_theme.experience_tenant_theme.publish_theme",
				args: { theme: frm.doc.name, company: frm.doc.company, note: "desk publish" },
			});
			await frm.reload_doc();
			frappe.show_alert({ message: __("Theme published"), indicator: "green" });
		});

		frm.add_custom_button(__("Rollback Previous"), async () => {
			await frappe.call({
				method: "omnexa_experience.omnexa_experience.doctype.experience_tenant_theme.experience_tenant_theme.rollback_theme",
				args: { company: frm.doc.company, note: "desk rollback previous" },
			});
			await frm.reload_doc();
			frappe.show_alert({ message: __("Theme rolled back"), indicator: "orange" });
		});

		frm.add_custom_button(__("History"), async () => {
			const r = await frappe.call({
				method: "omnexa_experience.omnexa_experience.doctype.experience_tenant_theme.experience_tenant_theme.list_theme_publish_history",
				args: { company: frm.doc.company, limit_page_length: 10 },
			});
			const rows = (r.message && r.message.history) || [];
			const lines = rows.map((x) => {
				const active = x.apply_to_public_site ? " (active)" : "";
				const who = x.published_by || "-";
				const when = x.published_at || "-";
				return `<li><b>${frappe.utils.escape_html(x.name)}</b>${active} — ${frappe.utils.escape_html(who)} @ ${frappe.utils.escape_html(when)}</li>`;
			});
			frappe.msgprint({
				title: __("Publish History"),
				indicator: "blue",
				message: `<ul>${lines.join("") || "<li>No history</li>"}</ul>`,
			});
		});

		frm.add_custom_button(__("Compare With Active"), async () => {
			const rHist = await frappe.call({
				method: "omnexa_experience.omnexa_experience.doctype.experience_tenant_theme.experience_tenant_theme.list_theme_publish_history",
				args: { company: frm.doc.company, limit_page_length: 10 },
			});
			const hist = (rHist.message && rHist.message.history) || [];
			const active = hist.find((x) => x.apply_to_public_site);
			if (!active) {
				frappe.msgprint(__("No active published theme found for this company."));
				return;
			}
			const r = await frappe.call({
				method: "omnexa_experience.omnexa_experience.doctype.experience_tenant_theme.experience_tenant_theme.compare_themes",
				args: { theme_a: frm.doc.name, theme_b: active.name, company: frm.doc.company },
			});
			const out = r.message || {};
			const diffs = out.diffs || [];
			const rows = diffs.map((d) => {
				const field = frappe.utils.escape_html(d.field || "");
				const a = frappe.utils.escape_html(String(d.a ?? ""));
				const b = frappe.utils.escape_html(String(d.b ?? ""));
				return `<tr><td><b>${field}</b></td><td>${a}</td><td>${b}</td></tr>`;
			});
			frappe.msgprint({
				title: __("Theme Diff vs Active"),
				indicator: "blue",
				message: diffs.length
					? `<table class="table table-bordered"><thead><tr><th>Field</th><th>This Theme</th><th>Active Theme</th></tr></thead><tbody>${rows.join("")}</tbody></table>`
					: __("No differences."),
				wide: true,
			});
		});
	},
});

