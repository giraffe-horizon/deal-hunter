function updateCompareBar() {
    const checked = document.querySelectorAll('.compare-cb:checked');
    const bar = document.getElementById('compare-bar');
    const countEl = document.getElementById('compare-count');
    const btn = document.getElementById('compare-btn');
    if (!bar || !countEl || !btn) return;
    countEl.textContent = checked.length;
    bar.classList.toggle('hidden', checked.length === 0);
    btn.disabled = checked.length < 2 || checked.length > 5;
    btn.classList.toggle('opacity-50', checked.length < 2 || checked.length > 5);
}

function clearCompare() {
    document.querySelectorAll('.compare-cb:checked').forEach(cb => { cb.checked = false; });
    updateCompareBar();
}

function goCompare() {
    const ids = Array.from(document.querySelectorAll('.compare-cb:checked')).map(cb => cb.value);
    if (ids.length >= 2 && ids.length <= 5) {
        window.location = '/compare?ids=' + ids.join(',');
    }
}
