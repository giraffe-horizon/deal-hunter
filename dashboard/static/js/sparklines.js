/**
 * Initialises all sparkline canvases on the current page/fragment.
 *
 * Selects every element with class .sparkline-canvas, reads price data
 * from its data-prices attribute (JSON array), and calls createSparkline()
 * from charts.js if at least two data points are available.
 *
 * Safe to call multiple times (e.g. after HTMX swaps) — only canvases
 * without an existing Chart instance will be initialised.
 */
(function () {
    function initSparklines() {
        document.querySelectorAll('.sparkline-canvas').forEach(function (el) {
            var prices = JSON.parse(el.dataset.prices || '[]');
            if (prices.length >= 2 && typeof createSparkline === 'function') {
                createSparkline(el, prices);
            }
        });
    }

    // Run on initial load.
    initSparklines();

    // Re-run after every HTMX content swap so that newly injected rows
    // (e.g. pagination, watchlist row updates) are also initialised.
    document.body.addEventListener('htmx:afterSwap', initSparklines);
})();
