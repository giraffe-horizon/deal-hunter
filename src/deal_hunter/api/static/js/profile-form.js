/**
 * Shared helpers for profile create and edit forms.
 */

/**
 * Display error messages in a container element.
 * @param {string} containerId - ID of the error container div
 * @param {string[]} errors - Array of error message strings
 */
function showErrors(containerId, errors) {
    var container = document.getElementById(containerId);
    while (container.firstChild) container.removeChild(container.firstChild);
    if (!errors || !errors.length) return;
    var wrapper = document.createElement('div');
    wrapper.className = 'bg-error-container/20 text-error rounded-card p-4 text-sm';
    errors.forEach(function(e) {
        var item = document.createElement('div');
        item.textContent = '\u2022 ' + e;
        wrapper.appendChild(item);
    });
    container.appendChild(wrapper);
}

/**
 * Add a keyword/points rule row to a list container.
 * @param {string} listId - ID of the container element
 * @param {string} [key] - Pre-filled keyword value
 * @param {string|number} [val] - Pre-filled points value
 */
function addRule(listId, key, val) {
    var list = document.getElementById(listId);
    var row = document.createElement('div');
    row.className = 'flex items-center gap-2 rule-row';

    var keyInput = document.createElement('input');
    keyInput.type = 'text';
    keyInput.name = 'score_rule_key[]';
    keyInput.placeholder = 'keyword';
    keyInput.value = key || '';
    keyInput.className = 'rule-key flex-1 px-3 py-2 rounded-card border border-outline-variant bg-surface-container-lowest text-on-surface text-sm focus:outline-none focus:border-primary';

    var valInput = document.createElement('input');
    valInput.type = 'number';
    valInput.name = 'score_rule_val[]';
    valInput.placeholder = 'pts';
    valInput.value = val != null ? val : '';
    valInput.className = 'rule-val w-24 px-3 py-2 rounded-card border border-outline-variant bg-surface-container-lowest text-on-surface text-sm focus:outline-none focus:border-primary';

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'text-on-surface-variant hover:text-error transition-colors flex-shrink-0';
    btn.onclick = function() { removeRow(btn); };

    var icon = document.createElement('span');
    icon.className = 'material-symbols-outlined text-[18px]';
    icon.textContent = 'remove_circle';
    btn.appendChild(icon);

    row.appendChild(keyInput);
    row.appendChild(valInput);
    row.appendChild(btn);
    list.appendChild(row);
    keyInput.focus();
}

/**
 * Remove the closest rule-row ancestor of a button.
 * @param {HTMLElement} btn - The remove button element
 */
function removeRow(btn) {
    var row = btn.closest('.rule-row');
    if (row) row.remove();
}

/**
 * Collect keyword/points rules from a container's rule rows.
 * @param {string} listId - ID of the container element
 * @returns {Object} Map of keyword -> points
 */
function collectRulesFromList(listId) {
    var rules = {};
    var rows = document.querySelectorAll('#' + listId + ' .rule-row');
    rows.forEach(function(row) {
        var key = row.querySelector('.rule-key').value.trim();
        var val = parseInt(row.querySelector('.rule-val').value, 10);
        if (key) {
            rules[key] = isNaN(val) ? 0 : val;
        }
    });
    return rules;
}

/**
 * Split a comma-separated string into an array of trimmed, non-empty strings.
 * @param {string} str - The comma-separated string
 * @returns {string[]}
 */
function splitComma(str) {
    return str.split(',').map(function(s) { return s.trim(); }).filter(Boolean);
}
