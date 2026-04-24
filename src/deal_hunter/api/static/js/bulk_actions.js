// Wire the deals-table selection UI to the bulk-ops backend.
//
// Responsibilities:
//   - React to row/header checkbox toggles and update Selection state.
//   - Show/hide the bulk action bar based on selection count.
//   - Dispatch Watch/Skip/Restore/Set-Target/Compare/Export requests.
//   - Prompt for confirmation on destructive or high-intent actions.
//   - Re-sync checkbox state after HTMX swaps the table back in.
(function () {
    const BULK_URL = "/api/deals/bulk";
    const EXPORT_URL = "/api/deals/export";

    function buildFilterQuery() {
        const params = new URLSearchParams(window.location.search);
        const passthrough = ["profile", "source", "min_score", "category", "status"];
        const q = new URLSearchParams();
        for (const key of passthrough) {
            const v = params.get(key);
            if (v !== null && v !== "") q.set(key, v);
        }
        return q;
    }

    function showToast(msg, kind) {
        const toast = document.getElementById("bulk-toast");
        if (!toast) return;
        toast.textContent = msg;
        toast.classList.remove("hidden");
        toast.classList.toggle("text-error", kind === "error");
        setTimeout(() => toast.classList.add("hidden"), 3500);
    }

    function renderBar() {
        const bar = document.getElementById("bulk-action-bar");
        const countEl = document.getElementById("bulk-count");
        const note = document.getElementById("bulk-scope-note");
        if (!bar || !countEl) return;
        const snap = window.Selection.snapshot();
        bar.classList.toggle("hidden", snap.count === 0);
        countEl.textContent = snap.count;
        if (note) {
            note.textContent = snap.mode === "filter" ? " (all filtered)" : "";
        }

        const compareBtn = bar.querySelector('[data-bulk-action="compare"]');
        if (compareBtn) {
            // Compare only works with 2–4 concrete ids; disable otherwise.
            const ok = snap.mode === "ids" && snap.count >= 2 && snap.count <= 4;
            compareBtn.disabled = !ok;
            compareBtn.classList.toggle("opacity-50", !ok);
            compareBtn.title = ok ? "Compare selected deals" : "Select 2–4 deals to compare";
        }
    }

    async function doBulk(action, extra) {
        const body = window.Selection.toPayload(action, extra);
        const res = await fetch(BULK_URL, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
            },
            body: JSON.stringify(body),
        });
        if (res.status === 413) {
            showToast("Selection too large — narrow the filter.", "error");
            return null;
        }
        if (!res.ok) {
            showToast("Bulk action failed.", "error");
            return null;
        }
        return res.json();
    }

    // Always confirm destructive (rejected), and confirm ANY bulk status
    // change above this many rows — accidental bulk-watch on hundreds of
    // rows is nearly as disruptive as accidental bulk-restore.
    const BULK_CONFIRM_THRESHOLD = 50;

    async function actionSetStatus(status, label) {
        const snap = window.Selection.snapshot();
        if (snap.count === 0) return;
        if (status === "rejected" || snap.count > BULK_CONFIRM_THRESHOLD) {
            const ok = await window.Confirm({
                title: `${label} ${snap.count} deal${snap.count === 1 ? "" : "s"}?`,
                body: "This will update every deal in the current selection.",
                okLabel: label,
            });
            if (!ok) return;
        }
        const result = await doBulk("set-status", { status });
        if (!result) return;
        showToast(`${label}: ${result.updated} deal${result.updated === 1 ? "" : "s"} updated.`);
        window.Selection.clear();
        reloadTable();
    }

    async function actionSetTarget() {
        const snap = window.Selection.snapshot();
        if (snap.count === 0) return;
        const raw = await window.Prompt({
            title: `Set target price on ${snap.count} deal${snap.count === 1 ? "" : "s"}`,
            body: "Target price in PLN (integer). Existing targets will be overwritten.",
            okLabel: "Next",
            placeholder: "e.g. 2500",
            inputType: "number",
        });
        if (raw === null || raw === "") return;
        const target = parseInt(raw, 10);
        if (!target || target <= 0) {
            showToast("Invalid price.", "error");
            return;
        }
        const ok = await window.Confirm({
            title: `Set target ${target} PLN on ${snap.count} deal${snap.count === 1 ? "" : "s"}?`,
            body: "Existing targets will be overwritten.",
            okLabel: "Set Target",
        });
        if (!ok) return;
        const result = await doBulk("set-target", { target_price: target });
        if (!result) return;
        showToast(`Set target on ${result.updated} deal${result.updated === 1 ? "" : "s"}.`);
        window.Selection.clear();
        reloadTable();
    }

    async function actionCompare() {
        const result = await doBulk("compare", {});
        if (result && result.redirect) window.location = result.redirect;
    }

    function actionExport(fmt) {
        const q = buildFilterQuery();
        q.set("format", fmt);
        window.location = `${EXPORT_URL}?${q.toString()}`;
    }

    function reloadTable() {
        // Re-fetch the current deals table via HTMX to reflect bulk changes.
        if (window.htmx) {
            htmx.ajax("GET", window.location.pathname + window.location.search, {
                target: "#deals-table",
                swap: "innerHTML",
            });
        } else {
            window.location.reload();
        }
    }

    function onRowCheckboxChange(e) {
        const cb = e.target;
        if (!cb.classList.contains("deal-cb")) return;
        window.Selection.toggleId(cb.value, cb.checked);
    }

    function onHeaderCheckboxChange(e) {
        const cb = e.target;
        if (cb.id !== "select-all-cb") return;
        if (cb.checked) {
            window.Selection.selectAllFiltered();
        } else {
            window.Selection.clear();
        }
        window.Selection.syncDom();
    }

    document.addEventListener("change", (e) => {
        onRowCheckboxChange(e);
        onHeaderCheckboxChange(e);
    });

    document.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-bulk-action]");
        if (btn) {
            if (btn.disabled) return;
            const action = btn.getAttribute("data-bulk-action");
            if (action === "watch") actionSetStatus("watching", "Watch");
            else if (action === "skip") actionSetStatus("rejected", "Skip");
            else if (action === "restore") actionSetStatus("active", "Restore");
            else if (action === "set-target") actionSetTarget();
            else if (action === "compare") actionCompare();
            else if (action === "export-csv") actionExport("csv");
            else if (action === "export-json") actionExport("json");
            return;
        }
        if (e.target && e.target.id === "bulk-clear-btn") {
            window.Selection.clear();
            window.Selection.syncDom();
        }
    });

    // Clear selection whenever a filter or sort changes (HTMX fires this on the
    // filter selects and the sort links). Pagination is NOT cleared — those
    // links don't fire this event on the filter form.
    document.addEventListener("htmx:beforeRequest", (e) => {
        const target = e.target;
        if (!target) return;
        const isFilter = target.closest && target.closest("#deal-filters");
        const isSort = target.tagName === "A" && target.href && /[?&](sort|dir)=/.test(target.href);
        if (isFilter || isSort) window.Selection.clear();
    });

    // After HTMX swaps the table back in, re-check the rows that belong to
    // the current selection (pagination preserves selection).
    document.addEventListener("htmx:afterSwap", (e) => {
        if (e.target && e.target.id === "deals-table") {
            window.Selection.syncDom();
        }
    });

    // Initial wiring.
    window.Selection.subscribe(renderBar);
    document.addEventListener("DOMContentLoaded", () => window.Selection.syncDom());
})();
