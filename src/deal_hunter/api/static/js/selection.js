// Selection state module for bulk operations on the deals table.
//
// Two modes:
//   - "ids":    user has checked specific rows -> .ids holds them.
//   - "filter": user checked the header "select all" -> .filter is a snapshot
//               of the current URL filters; .excluded holds rows the user
//               subsequently unchecked.
//
// The selection is deliberately fragile: any filter OR sort change clears it,
// but pagination preserves it (so a user can select all, page through, and
// then run a bulk action on the whole filtered set).
(function (global) {
    const FILTER_KEYS = ["profile", "source", "min_score", "category", "status"];

    const state = {
        mode: "ids",
        ids: new Set(),
        filter: null,
        excluded: new Set(),
    };

    const listeners = new Set();

    function emit() {
        for (const fn of listeners) {
            try { fn(snapshot()); } catch (err) { console.error(err); }
        }
    }

    function snapshot() {
        return {
            mode: state.mode,
            ids: new Set(state.ids),
            filter: state.filter ? { ...state.filter } : null,
            excluded: new Set(state.excluded),
            count: computeCount(),
        };
    }

    function computeCount() {
        if (state.mode === "ids") return state.ids.size;
        const total = parseInt(currentTableTotal(), 10) || 0;
        return Math.max(0, total - state.excluded.size);
    }

    function currentTableTotal() {
        const wrapper = document.querySelector("[data-total-filtered]");
        return wrapper ? wrapper.getAttribute("data-total-filtered") : 0;
    }

    function snapshotFilters() {
        const params = new URLSearchParams(window.location.search);
        const f = {};
        for (const key of FILTER_KEYS) {
            const v = params.get(key);
            if (v !== null && v !== "") f[key] = v;
        }
        return f;
    }

    function toggleId(id, checked) {
        if (state.mode === "filter") {
            if (checked) {
                state.excluded.delete(id);
            } else {
                state.excluded.add(id);
            }
        } else {
            if (checked) {
                state.ids.add(id);
            } else {
                state.ids.delete(id);
            }
        }
        emit();
    }

    function selectAllFiltered() {
        state.mode = "filter";
        state.filter = snapshotFilters();
        state.ids.clear();
        state.excluded.clear();
        emit();
    }

    function clear() {
        state.mode = "ids";
        state.ids.clear();
        state.excluded.clear();
        state.filter = null;
        emit();
    }

    function isRowSelected(id) {
        if (state.mode === "filter") return !state.excluded.has(id);
        return state.ids.has(id);
    }

    function toPayload(action, extra) {
        const body = { action, ...(extra || {}) };
        if (state.mode === "ids") {
            body.ids = Array.from(state.ids);
        } else {
            body.filter = state.filter || {};
            body.excluded = Array.from(state.excluded);
        }
        return body;
    }

    function subscribe(fn) {
        listeners.add(fn);
        fn(snapshot());
        return () => listeners.delete(fn);
    }

    // Sync DOM row checkboxes with current state after a table refresh.
    function syncDom() {
        document.querySelectorAll(".deal-cb").forEach((cb) => {
            cb.checked = isRowSelected(cb.value);
        });
        const header = document.getElementById("select-all-cb");
        if (header) header.checked = state.mode === "filter" && state.excluded.size === 0;
    }

    global.Selection = {
        toggleId,
        selectAllFiltered,
        clear,
        subscribe,
        snapshot,
        toPayload,
        syncDom,
        isRowSelected,
    };
})(window);
