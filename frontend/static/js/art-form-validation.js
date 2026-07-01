(function () {
  "use strict";

  const timePattern = /^(?:[01]\d|2[0-3]):[0-5]\d$/;

  document.querySelectorAll("[data-art-schedule-form]").forEach((form) => {
    const start = form.elements.namedItem("hora_inicio");
    const end = form.elements.namedItem("hora_termino");
    if (!start || !end) return;

    function setError(field, message) {
      const error = form.querySelector(`[data-time-error="${field.name}"]`);
      field.setAttribute("aria-invalid", message ? "true" : "false");
      if (!error) return;
      error.textContent = message;
      error.classList.toggle("hidden", !message);
    }

    function validate() {
      const startValue = start.value.trim();
      const endValue = end.value.trim();
      let startError = "";
      let endError = "";

      if (startValue || endValue) {
        if (!startValue) startError = "Ingresa el horario de inicio.";
        else if (!timePattern.test(startValue)) startError = "Usa un horario válido en formato HH:MM (00:00 a 23:59).";
        if (!endValue) endError = "Ingresa el horario de término.";
        else if (!timePattern.test(endValue)) endError = "Usa un horario válido en formato HH:MM (00:00 a 23:59).";
        if (!startError && !endError && startValue >= endValue) {
          endError = "El horario de término debe ser posterior al horario de inicio.";
        }
      }

      setError(start, startError);
      setError(end, endError);
      return !startError && !endError;
    }

    form.addEventListener("submit", (event) => {
      const scheduleValid = validate();
      const nativeValid = form.checkValidity();
      if (scheduleValid && nativeValid) return;
      event.preventDefault();
      if (!nativeValid) form.reportValidity();
      const firstInvalid = form.querySelector('[aria-invalid="true"], :invalid');
      firstInvalid?.focus();
      firstInvalid?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, true);
  });
})();
