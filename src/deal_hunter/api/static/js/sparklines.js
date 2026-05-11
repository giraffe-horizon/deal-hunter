/**
 * Initialises all sparkline canvases on the current page/fragment.
 *
 * Selects every element with class .sparkline-canvas, reads price data
 * from its data-prices attribute (JSON array), and calls createSparkline()
 * from charts.js. createSparkline destroys any existing Chart on the
 * canvas first, so this is safe to call repeatedly.
 *
 * Idempotent: re-running the script (e.g. if loaded twice) does not
 * register duplicate htmx:afterSwap listeners.
 */
(function () {
    if (window.__dhSparklinesBound) return;
    window.__dhSparklinesBound = true;

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
