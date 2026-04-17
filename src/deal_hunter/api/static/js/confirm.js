// Tiny promise-based confirmation dialog.
// Usage:  if (await Confirm({title, body, okLabel})) { ... }
(function (global) {
    function Confirm({ title, body, okLabel }) {
        return new Promise((resolve) => {
            const root = document.getElementById("confirm-dialog-mount");
            const titleEl = document.getElementById("confirm-title");
            const bodyEl = document.getElementById("confirm-body");
            const okBtn = document.getElementById("confirm-ok");
            const cancelBtn = document.getElementById("confirm-cancel");
            if (!root || !titleEl || !bodyEl || !okBtn || !cancelBtn) {
                resolve(true);
                return;
            }

            titleEl.textContent = title || "Confirm";
            bodyEl.textContent = body || "";
            okBtn.textContent = okLabel || "Confirm";
            root.classList.remove("hidden");
            root.classList.add("flex");

            const cleanup = (result) => {
                root.classList.add("hidden");
                root.classList.remove("flex");
                okBtn.removeEventListener("click", onOk);
                cancelBtn.removeEventListener("click", onCancel);
                resolve(result);
            };
            const onOk = () => cleanup(true);
            const onCancel = () => cleanup(false);
            okBtn.addEventListener("click", onOk);
            cancelBtn.addEventListener("click", onCancel);
        });
    }

    global.Confirm = Confirm;
})(window);
