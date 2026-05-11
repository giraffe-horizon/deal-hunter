/**
 * Shared Chart.js configuration and helpers for Deal Hunter dashboard.
 *
 * Idempotent: re-loading this script (e.g. via an HTMX partial that includes
 * <script src=".../charts.js">) is a no-op after the first execution. The
 * factory functions also destroy any prior Chart bound to the target canvas
 * so re-rendering a sparkline after a swap can't trigger Chart.js's
 * "Canvas is already in use" error.
 */
(function () {
    if (window.DH_CHART_COLORS) return;

    const DH_CHART_COLORS = {
        primary: '#005db5',
        primaryFill: 'rgba(0, 93, 181, 0.08)',
        secondary: '#526074',
        tertiary: '#006b62',
        error: '#9f403d',
        label: '#445d99',
        grid: 'rgba(152, 177, 242, 0.15)',
        tooltip: '#060e20',
    };

    const DH_CHART_FONT = 'Inter';

    window.DH_CHART_COLORS = DH_CHART_COLORS;
    window.DH_CHART_FONT = DH_CHART_FONT;

    function destroyExisting(canvas) {
        const existing = Chart.getChart(canvas);
        if (existing) existing.destroy();
    }

    window.createPriceChart = function (canvas, labels, prices, lowest, highest) {
        destroyExisting(canvas);
        const ctx = canvas.getContext('2d');

        const lowestIdx = lowest !== null ? prices.indexOf(lowest) : -1;
        const highestIdx = highest !== null ? prices.indexOf(highest) : -1;

        const pointBg = prices.map((p, i) => {
            if (i === lowestIdx && lowest !== highest) return DH_CHART_COLORS.error;
            if (i === highestIdx && lowest !== highest) return DH_CHART_COLORS.tertiary;
            return DH_CHART_COLORS.primary;
        });
        const pointRadius = prices.map((p, i) => {
            if (i === lowestIdx || i === highestIdx) return 6;
            return 3;
        });

        return new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Price (PLN)',
                    data: prices,
                    borderColor: DH_CHART_COLORS.primary,
                    backgroundColor: DH_CHART_COLORS.primaryFill,
                    fill: true,
                    tension: 0.3,
                    pointBackgroundColor: pointBg,
                    pointBorderColor: pointBg,
                    pointRadius: pointRadius,
                    pointHoverRadius: 7,
                    borderWidth: 2,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: DH_CHART_COLORS.tooltip,
                        titleFont: { family: DH_CHART_FONT },
                        bodyFont: { family: DH_CHART_FONT },
                        callbacks: {
                            label: function(ctx) {
                                return ctx.parsed.y.toLocaleString('pl-PL') + ' zl';
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: {
                            font: { family: DH_CHART_FONT, size: 11 },
                            color: DH_CHART_COLORS.label,
                            maxTicksLimit: 10
                        }
                    },
                    y: {
                        grid: { color: DH_CHART_COLORS.grid },
                        ticks: {
                            font: { family: DH_CHART_FONT, size: 11 },
                            color: DH_CHART_COLORS.label,
                            callback: function(v) { return v.toLocaleString('pl-PL') + ' zl'; }
                        }
                    }
                }
            }
        });
    };

    window.createSparkline = function (canvas, labels, data, color, fill) {
        destroyExisting(canvas);
        color = color || DH_CHART_COLORS.primary;
        return new Chart(canvas, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    data: data,
                    borderColor: color,
                    borderWidth: 1.5,
                    pointRadius: 0,
                    tension: 0.3,
                    fill: fill || false,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false }, tooltip: { enabled: false } },
                scales: { x: { display: false }, y: { display: false } },
            }
        });
    };

    window.createTrendSparkline = function (canvas, labels, data, color) {
        destroyExisting(canvas);
        color = color || DH_CHART_COLORS.primary;
        return new Chart(canvas, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    data: data,
                    borderColor: color,
                    backgroundColor: color + '15',
                    fill: true,
                    tension: 0.4,
                    borderWidth: 2,
                    pointRadius: 0,
                    pointHitRadius: 8,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: DH_CHART_COLORS.tooltip,
                        titleFont: { family: DH_CHART_FONT, size: 11 },
                        bodyFont: { family: DH_CHART_FONT, size: 11 },
                        callbacks: {
                            label: function(ctx) {
                                return ctx.parsed.y.toLocaleString('pl-PL') + ' zl';
                            }
                        }
                    }
                },
                scales: {
                    x: { display: false },
                    y: { display: false }
                }
            }
        });
    };
})();
