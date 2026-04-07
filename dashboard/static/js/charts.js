/**
 * Shared Chart.js configuration and helpers for Deal Hunter dashboard.
 */

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

/**
 * Create a price history line chart with colored points for lowest/highest.
 * Returns the Chart instance.
 */
function createPriceChart(canvas, labels, prices, lowest, highest) {
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
}

/**
 * Create a sparkline (no axes, no legend, no tooltip).
 * Returns the Chart instance.
 */
function createSparkline(canvas, labels, data, color, fill) {
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
}

/**
 * Create a sparkline with tooltip enabled (for trend charts).
 * Returns the Chart instance.
 */
function createTrendSparkline(canvas, labels, data, color) {
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
}
