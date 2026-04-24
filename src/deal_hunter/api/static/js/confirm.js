// Tiny promise-based dialog helpers.
//
//   const ok = await Confirm({title, body, okLabel})
//   const value = await Prompt({title, body, okLabel, placeholder, inputType})
//
// Prompt resolves with the entered string on OK, or null on cancel.
(function (global) {
    function getMount() {
        return {
            root: document.getElementById("confirm-dialog-mount"),
            titleEl: document.getElementById("confirm-title"),
            bodyEl: document.getElementById("confirm-body"),
            okBtn: document.getElementById("confirm-ok"),
            cancelBtn: document.getElementById("confirm-cancel"),
            inputSlot: document.getElementById("confirm-input-slot"),
        };
    }

    function open(root) {
        root.classList.remove("hidden");
        root.classList.add("flex");
    }

    function close(root) {
        root.classList.add("hidden");
        root.classList.remove("flex");
    }

    function clearInputSlot(slot) {
        if (slot) slot.replaceChildren();
    }

    function Confirm({ title, body, okLabel }) {
        return new Promise((resolve) => {
            const { root, titleEl, bodyEl, okBtn, cancelBtn, inputSlot } = getMount();
            if (!root || !titleEl || !bodyEl || !okBtn || !cancelBtn) {
                resolve(true);
                return;
            }
            clearInputSlot(inputSlot);

            titleEl.textContent = title || "Confirm";
            bodyEl.textContent = body || "";
            okBtn.textContent = okLabel || "Confirm";
            open(root);

            const cleanup = (result) => {
                close(root);
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

    function Prompt({ title, body, okLabel, placeholder, inputType }) {
        return new Promise((resolve) => {
            const { root, titleEl, bodyEl, okBtn, cancelBtn, inputSlot } = getMount();
            if (!root || !titleEl || !bodyEl || !okBtn || !cancelBtn || !inputSlot) {
                resolve(null);
                return;
            }

            titleEl.textContent = title || "Input";
            bodyEl.textContent = body || "";
            okBtn.textContent = okLabel || "OK";

            clearInputSlot(inputSlot);
            const input = document.createElement("input");
            input.type = inputType || "text";
            input.placeholder = placeholder || "";
            input.className =
                "w-full px-3 py-2 mt-2 rounded-card border border-outline-variant bg-surface text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/30";
            inputSlot.appendChild(input);

            open(root);
            setTimeout(() => input.focus(), 0);

            const cleanup = (result) => {
                close(root);
                clearInputSlot(inputSlot);
                okBtn.removeEventListener("click", onOk);
                cancelBtn.removeEventListener("click", onCancel);
                input.removeEventListener("keydown", onKey);
                resolve(result);
            };
            const onOk = () => cleanup(input.value);
            const onCancel = () => cleanup(null);
            const onKey = (e) => {
                if (e.key === "Enter") onOk();
                else if (e.key === "Escape") onCancel();
            };
            input.addEventListener("keydown", onKey);
            okBtn.addEventListener("click", onOk);
            cancelBtn.addEventListener("click", onCancel);
        });
    }

    global.Confirm = Confirm;
    global.Prompt = Prompt;
})(window);
