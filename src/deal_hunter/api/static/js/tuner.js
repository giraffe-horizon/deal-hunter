/**
 * Scoring Tuner — simulate and save profile scoring rules.
 */

const TUNER_PROFILE = document.querySelector('[data-profile]')?.dataset.profile;

async function simulate() {
    const rules = collectRules();
    const errDiv = document.getElementById('tuner-errors');
    errDiv.replaceChildren();

    try {
        const resp = await fetch('/api/tuner/' + TUNER_PROFILE + '/simulate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
            body: JSON.stringify(rules),
        });
        const data = await resp.json();
        if (data.error) {
            showError(data.error);
            return;
        }
        renderResults(data.results);
    } catch(e) {
        showError('Simulation failed: ' + e.message);
    }
}

function showError(msg) {
    const errDiv = document.getElementById('tuner-errors');
    const container = document.createElement('div');
    container.className = 'bg-error-container/20 text-error rounded-card p-4 text-sm mb-4';
    const item = document.createElement('div');
    item.textContent = msg;
    container.appendChild(item);
    errDiv.appendChild(container);
}

function renderResults(results) {
    const tbody = document.getElementById('results-body');
    tbody.replaceChildren();
    results.forEach(r => {
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-surface-container transition-colors border-b border-outline-variant/10';

        // Title cell
        const tdTitle = document.createElement('td');
        tdTitle.className = 'py-2 pl-4 pr-2 max-w-[180px]';
        const titleLink = document.createElement('a');
        titleLink.href = '/deals/' + encodeURIComponent(r.id);
        titleLink.className = 'text-sm text-primary hover:underline line-clamp-1 block truncate';
        titleLink.title = r.title;
        titleLink.textContent = r.title;
        tdTitle.appendChild(titleLink);
        tr.appendChild(tdTitle);

        // Price cell
        const tdPrice = document.createElement('td');
        tdPrice.className = 'py-2 pr-2 whitespace-nowrap';
        const priceSpan = document.createElement('span');
        priceSpan.className = 'text-sm font-headline font-semibold text-on-surface';
        priceSpan.textContent = r.price ? r.price.toLocaleString('pl-PL') + ' zl' : '0 zl';
        tdPrice.appendChild(priceSpan);
        tr.appendChild(tdPrice);

        // Current score cell
        const tdCurrent = document.createElement('td');
        tdCurrent.className = 'py-2 pr-2';
        const currentSpan = document.createElement('span');
        currentSpan.className = 'text-sm text-on-surface-variant';
        currentSpan.textContent = r.current_score ?? '\u2014';
        tdCurrent.appendChild(currentSpan);
        tr.appendChild(tdCurrent);

        // New score cell
        const tdNew = document.createElement('td');
        tdNew.className = 'py-2 pr-2';
        const newSpan = document.createElement('span');
        const scoreClass = r.rejected ? 'text-error' :
            r.new_score >= 70 ? 'text-tertiary' :
            r.new_score >= 40 ? 'text-[#b8860b]' : 'text-error';
        newSpan.className = 'text-sm font-headline font-bold ' + scoreClass;
        newSpan.textContent = r.rejected ? 'REJ' : r.new_score;
        tdNew.appendChild(newSpan);
        tr.appendChild(tdNew);

        // Diff cell
        const tdDiff = document.createElement('td');
        tdDiff.className = 'py-2 pr-4';
        const diffSpan = document.createElement('span');
        const diffClass = r.diff > 0 ? 'text-tertiary' : r.diff < 0 ? 'text-error' : 'text-on-surface-variant';
        diffSpan.className = 'text-sm font-headline font-bold ' + diffClass;
        diffSpan.textContent = r.rejected ? '\u2014' : (r.diff > 0 ? '+' : '') + r.diff;
        tdDiff.appendChild(diffSpan);
        tr.appendChild(tdDiff);

        tbody.appendChild(tr);
    });
}

function collectRules() {
    const rules = {};
    // Score rules
    const scoreRules = {};
    document.querySelectorAll('#score-rules-body tr').forEach(tr => {
        const keyword = tr.querySelector('.rule-keyword')?.value?.trim();
        const points = parseInt(tr.querySelector('.rule-points')?.value) || 0;
        if (keyword) scoreRules[keyword] = points;
    });
    rules.score_rules = scoreRules;
    // Penalties
    const penalties = {};
    document.querySelectorAll('#penalties-body tr').forEach(tr => {
        const keyword = tr.querySelector('.penalty-keyword')?.value?.trim();
        const points = parseInt(tr.querySelector('.penalty-points')?.value) || 0;
        if (keyword) penalties[keyword] = points;
    });
    rules.penalties = penalties;
    // Budget
    rules.budget = {
        min: parseInt(document.getElementById('budget-min')?.value) || 0,
        max: parseInt(document.getElementById('budget-max')?.value) || 999999,
    };
    // Thresholds
    rules.score_threshold = parseInt(document.getElementById('score-threshold')?.value) || 50;
    rules.score_threshold_alert = parseInt(document.getElementById('score-threshold-alert')?.value) || 100;
    // Excluded words
    const excludedText = document.getElementById('excluded-words')?.value || '';
    rules.excluded_words = excludedText.split(',').map(s => s.trim()).filter(Boolean);
    // Required any
    const requiredText = document.getElementById('required-any')?.value || '';
    rules.required_any = requiredText.split(',').map(s => s.trim()).filter(Boolean);
    return rules;
}

function addRuleRow(tbodyId, keywordClass, pointsClass) {
    const tbody = document.getElementById(tbodyId);
    const tr = document.createElement('tr');

    const tdKeyword = document.createElement('td');
    tdKeyword.className = 'py-1 pr-2';
    const inputKeyword = document.createElement('input');
    inputKeyword.type = 'text';
    inputKeyword.className = keywordClass + ' w-full bg-surface-container rounded-lg px-3 py-2 text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/30';
    inputKeyword.placeholder = 'keyword';
    tdKeyword.appendChild(inputKeyword);
    tr.appendChild(tdKeyword);

    const tdPoints = document.createElement('td');
    tdPoints.className = 'py-1 pr-2';
    const inputPoints = document.createElement('input');
    inputPoints.type = 'number';
    inputPoints.className = pointsClass + ' w-20 bg-surface-container rounded-lg px-3 py-2 text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/30';
    inputPoints.value = '0';
    tdPoints.appendChild(inputPoints);
    tr.appendChild(tdPoints);

    const tdAction = document.createElement('td');
    tdAction.className = 'py-1';
    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'text-error hover:text-error/80 text-sm';
    removeBtn.textContent = 'Remove';
    removeBtn.onclick = () => tr.remove();
    tdAction.appendChild(removeBtn);
    tr.appendChild(tdAction);

    tbody.appendChild(tr);
}

async function saveProfile() {
    const rules = collectRules();
    const errDiv = document.getElementById('tuner-errors');
    errDiv.replaceChildren();

    try {
        const resp = await fetch('/api/tuner/' + TUNER_PROFILE + '/save', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
            body: JSON.stringify(rules),
        });
        const data = await resp.json();
        if (!data.ok) {
            if (data.errors) {
                const container = document.createElement('div');
                container.className = 'bg-error-container/20 text-error rounded-card p-4 text-sm mb-4';
                data.errors.forEach(e => {
                    const item = document.createElement('div');
                    item.textContent = '\u2022 ' + e;
                    container.appendChild(item);
                });
                errDiv.appendChild(container);
            }
            return;
        }
        // Show success
        const successDiv = document.createElement('div');
        successDiv.className = 'bg-tertiary-container/20 text-tertiary rounded-card p-4 text-sm mb-4';
        successDiv.textContent = 'Profile saved successfully.';
        errDiv.appendChild(successDiv);
        setTimeout(() => successDiv.remove(), 3000);
    } catch(e) {
        showError('Save failed: ' + e.message);
    }
}
