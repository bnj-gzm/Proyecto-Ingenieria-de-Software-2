(function () {
  "use strict";

  const notify = (message) => {
    if (window.dartToast) window.dartToast(message, "warning");
  };

  function initRiskTable(form) {
    if (form.dataset.riskInitialized === "true") return;

    const body = form.querySelector("[data-risk-rows]");
    const addButton = form.querySelector("[data-risk-add]");
    const error = form.querySelector("[data-risk-error]");
    const jsonInput = form.querySelector("[data-risks-json]");
    if (!body || !addButton) return;

    const rows = () => Array.from(body.children).filter((row) => row.matches("[data-risk-row]"));
    const activeRows = () => rows().filter((row) => row.dataset.removing !== "true");
    let riskRowsState = [];

    function fieldsFor(row) {
      return Array.from(row.querySelectorAll("[data-risk-field]"));
    }

    function updateState() {
      const currentRows = activeRows();
      riskRowsState = currentRows.map((row) => ({
        actividad: row.querySelector('[data-risk-field="secuencia"]')?.value.trim() || "",
        riesgo: row.querySelector('[data-risk-field="riesgo"]')?.value.trim() || "",
        control: row.querySelector('[data-risk-field="control"]')?.value.trim() || "",
      }));
      form.dataset.riskRowCount = String(riskRowsState.length);
      if (jsonInput) jsonInput.value = JSON.stringify(riskRowsState);

      currentRows.forEach((row, index) => {
        const number = row.querySelector("[data-risk-number]");
        const removeButton = row.querySelector("[data-risk-remove]");
        if (number) number.textContent = String(index + 1);
        if (!removeButton) return;
        const isOnlyRow = currentRows.length === 1;
        removeButton.disabled = isOnlyRow;
        removeButton.setAttribute("aria-disabled", isOnlyRow ? "true" : "false");
        removeButton.title = isOnlyRow ? "Debe existir al menos una fila" : "Eliminar esta fila";
      });
    }

    function clearRow(row) {
      row.removeAttribute("data-removing");
      row.classList.remove("risk-row-invalid", "risk-row-removing", "is-visible");
      fieldsFor(row).forEach((field) => {
        field.value = "";
        field.defaultValue = "";
        field.classList.remove("risk-field-invalid");
        field.setAttribute("aria-invalid", "false");
      });
      return row;
    }

    function validateRow(row, showErrors) {
      const fields = fieldsFor(row);
      const incomplete = fields.some((field) => !field.value.trim());
      if (showErrors) {
        row.classList.toggle("risk-row-invalid", incomplete);
        fields.forEach((field) => {
          const invalid = !field.value.trim();
          field.classList.toggle("risk-field-invalid", invalid);
          field.setAttribute("aria-invalid", invalid ? "true" : "false");
        });
      }
      return !incomplete;
    }

    function addRow() {
      const baseRow = activeRows()[0];
      if (!baseRow) return;
      const newRow = clearRow(baseRow.cloneNode(true));
      newRow.classList.add("risk-row-enter");
      body.appendChild(newRow);
      updateState();
      window.requestAnimationFrame(() => newRow.classList.add("is-visible"));
      newRow.querySelector("[data-risk-field]")?.focus();
      error?.classList.add("hidden");
    }

    function removeRow(row) {
      if (!row || row.parentElement !== body || activeRows().length <= 1) return;
      row.dataset.removing = "true";
      row.classList.add("risk-row-removing");
      updateState();
      window.setTimeout(() => {
        row.remove();
        updateState();
      }, 180);
    }

    addButton.addEventListener("click", addRow);
    body.addEventListener("click", (event) => {
      const removeButton = event.target.closest("[data-risk-remove]");
      if (!removeButton || !body.contains(removeButton)) return;
      removeRow(removeButton.closest("[data-risk-row]"));
    });
    body.addEventListener("input", () => {
      updateState();
    });
    form.addEventListener("submit", (event) => {
      updateState();
      const currentRows = activeRows();
      const complete = currentRows.length >= 1 && currentRows.every((row) => validateRow(row, true));
      if (complete) {
        error?.classList.add("hidden");
        return;
      }
      event.preventDefault();
      error?.classList.remove("hidden");
      notify("Completa actividad, riesgo y control en cada fila.");
      currentRows.find((row) => !validateRow(row, false))?.querySelector("[data-risk-field]")?.focus();
    }, true);

    form.dataset.riskInitialized = "true";
    updateState();
  }

  document.querySelectorAll("[data-risk-form]").forEach(initRiskTable);
})();
