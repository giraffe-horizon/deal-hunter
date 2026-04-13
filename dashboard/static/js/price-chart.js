/**
 * Price history chart initialisation for deal_detail.html.
 *
 * Reads the deal ID from data-deal-id on the canvas element,
 * fetches /api/price-history/<id>, and renders the Chart.js line chart.
 * Period filter buttons call window.filterChart(period).
 */
(function () {
    const canvas = document.getElementById('priceChart');
    if (!canvas) return;

    const dealId = canvas.dataset.dealId;
    if (!dealId) return;

    let allLabels = [];
    let allPrices = [];
    let chart = null;

    fetch('/api/price-history/' + encodeURIComponent(dealId))
        .then(function (r) { return r.json(); })
        .then(function (data) {
            allLabels = data.labels;
            allPrices = data.prices;

            if (!allLabels.length) {
                document.getElementById('chart-container').classList.add('hidden');
                document.getElementById('chart-empty').classList.remove('hidden');
                document.getElementById('period-buttons').classList.add('hidden');
                return;
            }

            if (chart) chart.destroy();
            chart = createPriceChart(canvas, allLabels, allPrices, data.lowest, data.highest);
        })
        .catch(function () {
            document.getElementById('chart-container').classList.add('hidden');
            document.getElementById('chart-empty').classList.remove('hidden');
            document.getElementById('period-buttons').classList.add('hidden');
        });

    window.filterChart = function (period) {
        document.querySelectorAll('.period-btn').forEach(function (btn) {
            if (btn.dataset.period === period) {
                btn.className = 'period-btn px-3 py-1.5 text-xs font-label rounded-card transition-colors bg-primary text-on-primary';
            } else {
                btn.className = 'period-btn px-3 py-1.5 text-xs font-label rounded-card transition-colors bg-surface-container-high text-on-surface-variant hover:bg-surface-container-highest';
            }
        });

        if (!allLabels.length) return;

        var filteredLabels = allLabels;
        var filteredPrices = allPrices;

        if (period !== 'all') {
            var now = new Date();
            var months = period === '1m' ? 1 : 3;
            var cutoff = new Date(now.getFullYear(), now.getMonth() - months, now.getDate());
            var cutoffStr = cutoff.toISOString().slice(0, 10);

            var startIdx = allLabels.findIndex(function (l) { return l >= cutoffStr; });
            if (startIdx >= 0) {
                filteredLabels = allLabels.slice(startIdx);
                filteredPrices = allPrices.slice(startIdx);
            }
        }

        var lowest = filteredPrices.length ? Math.min.apply(null, filteredPrices) : null;
        var highest = filteredPrices.length ? Math.max.apply(null, filteredPrices) : null;
        if (chart) chart.destroy();
        chart = createPriceChart(canvas, filteredLabels, filteredPrices, lowest, highest);
    };
})();
