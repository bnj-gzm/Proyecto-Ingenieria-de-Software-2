(function () {
  "use strict";

  const toast = (message, type = "success") => {
    if (window.dartToast) window.dartToast(message, type);
  };

  document.addEventListener("error", (event) => {
    const image = event.target;
    if (!(image instanceof HTMLImageElement) || !image.matches(".art-visual, .profile-visual")) return;
    if (image.nextElementSibling) return;
    const fallback = document.createElement("div");
    fallback.className = "image-fallback";
    fallback.textContent = image.dataset.fallbackLabel || "Imagen no disponible";
    image.hidden = true;
    image.insertAdjacentElement("afterend", fallback);
  }, true);

  const imageLightbox = document.getElementById("art-image-lightbox");
  const imageLightboxPanel = document.getElementById("art-image-lightbox-panel");
  const imageLightboxImage = document.getElementById("art-image-lightbox-image");
  const imageLightboxClose = document.getElementById("art-image-lightbox-close");
  let lastLightboxTrigger = null;

  function openImageLightbox(image) {
    if (!image || image.hidden || !imageLightbox || !imageLightboxImage) return;
    lastLightboxTrigger = image.closest(".art-lightbox-trigger") || image;
    imageLightboxImage.src = image.currentSrc || image.src;
    imageLightboxImage.alt = image.alt || "Evidencia ART ampliada";
    imageLightbox.classList.add("is-open");
    imageLightbox.setAttribute("aria-hidden", "false");
    document.body.classList.add("modal-open");
    window.setTimeout(() => imageLightboxClose?.focus(), 100);
  }

  function closeImageLightbox() {
    if (!imageLightbox) return;
    imageLightbox.classList.remove("is-open");
    imageLightbox.setAttribute("aria-hidden", "true");
    document.body.classList.remove("modal-open");
    imageLightboxImage.removeAttribute("src");
    lastLightboxTrigger?.focus?.();
    lastLightboxTrigger = null;
  }

  document.querySelectorAll("img.art-visual").forEach((image) => {
    if (!image.closest("button, a")) {
      image.tabIndex = 0;
      image.setAttribute("role", "button");
      image.setAttribute("aria-label", image.alt ? `Ampliar ${image.alt}` : "Ampliar evidencia ART");
    }
  });

  document.addEventListener("click", (event) => {
    const image = event.target.closest?.("img.art-visual")
      || event.target.closest?.(".art-lightbox-trigger")?.querySelector("img.art-visual");
    if (!image || image.hidden || !imageLightbox || !imageLightboxImage) return;
    event.preventDefault();
    openImageLightbox(image);
  });
  document.addEventListener("keydown", (event) => {
    const image = event.target.closest?.("img.art-visual")
      || event.target.closest?.(".art-lightbox-trigger")?.querySelector("img.art-visual");
    if (image && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      openImageLightbox(image);
    }
  });
  imageLightboxClose?.addEventListener("click", closeImageLightbox);
  imageLightbox?.addEventListener("click", (event) => {
    if (event.target === imageLightbox || event.target === imageLightboxPanel) closeImageLightbox();
  });
  imageLightboxImage?.addEventListener("click", closeImageLightbox);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && imageLightbox?.classList.contains("is-open")) closeImageLightbox();
  });

  const imageProcessing = new WeakMap();

  async function compressImage(file, maxWidth) {
    if (!file.type.startsWith("image/") || file.size < 350 * 1024 || typeof createImageBitmap !== "function") return file;
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, maxWidth / bitmap.width, maxWidth / bitmap.height);
    if (scale === 1 && file.size < 900 * 1024) { bitmap.close(); return file; }
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/webp", 0.82));
    if (!blob || blob.size >= file.size) return file;
    return new File([blob], file.name.replace(/\.[^.]+$/, "") + ".webp", { type: "image/webp", lastModified: file.lastModified });
  }

  function renderImagePreview(target, files, objectUrls) {
    objectUrls.forEach((url) => URL.revokeObjectURL(url));
    objectUrls.length = 0;
    target.replaceChildren();
    files.forEach((file) => {
      if (!file.type.startsWith("image/")) return;
      const url = URL.createObjectURL(file);
      objectUrls.push(url);
      const item = document.createElement("div");
      item.className = "image-preview-item";
      const image = document.createElement("img");
      image.src = url;
      image.alt = `Vista previa de ${file.name}`;
      const name = document.createElement("span");
      name.textContent = file.name;
      item.append(image, name);
      target.appendChild(item);
    });
    target.hidden = target.childElementCount === 0;
  }

  document.querySelectorAll("[data-image-input]").forEach((input) => {
    const target = document.getElementById(input.dataset.previewTarget || "");
    if (!target) return;
    const objectUrls = [];
    const initialPreviewHtml = target.innerHTML;
    const initialPreviewHidden = target.hidden;

    // Build or find the confirm/cancel bar for this input
    let confirmBar = input.parentElement.querySelector(".image-confirm-bar");
    if (!confirmBar) {
      confirmBar = document.createElement("div");
      confirmBar.className = "image-confirm-bar hidden";
      confirmBar.innerHTML =
        '<span class="image-confirm-label">¿Confirmar imagen seleccionada?</span>' +
        '<button type="button" class="image-confirm-ok btn-primary px-3 py-2 text-xs">Confirmar</button>' +
        '<button type="button" class="image-confirm-cancel btn-secondary px-3 py-2 text-xs">Cancelar</button>';
      // Insert after the target preview div, or after the input
      (target.parentElement || input.parentElement).insertBefore(confirmBar, target.nextSibling || null);
    }

    const confirmOk = confirmBar.querySelector(".image-confirm-ok");
    const confirmCancel = confirmBar.querySelector(".image-confirm-cancel");
    const confirmLabel = confirmBar.querySelector(".image-confirm-label");
    let pendingFiles = [];
    let selectionVersion = 0;

    function applyFiles(files) {
      const version = selectionVersion;
      renderImagePreview(target, files, objectUrls);
      const processing = Promise.all(files.map((file) => compressImage(file, Number(input.dataset.imageMaxWidth || 1920))))
        .then((compressed) => {
          if (version !== selectionVersion) return;
          if (typeof DataTransfer === "undefined") return;
          const transfer = new DataTransfer();
          compressed.forEach((file) => transfer.items.add(file));
          input.files = transfer.files;
        })
        .catch(() => toast("No pudimos comprimir una imagen; se enviará el archivo original.", "warning"))
        .finally(() => {
          if (version === selectionVersion) imageProcessing.delete(input);
        });
      imageProcessing.set(input, processing);
    }

    function clearSelection() {
      selectionVersion += 1;
      pendingFiles = [];
      imageProcessing.delete(input);
      input.dataset.imageConfirmed = "false";
      confirmBar.classList.add("hidden");
      confirmOk.classList.remove("hidden");
      confirmLabel.textContent = "¿Confirmar imagen seleccionada?";
      input.value = "";
      if (typeof DataTransfer !== "undefined") {
        input.files = new DataTransfer().files;
      }
      objectUrls.forEach((url) => URL.revokeObjectURL(url));
      objectUrls.length = 0;
      target.innerHTML = initialPreviewHtml;
      target.hidden = initialPreviewHidden;
    }

    input.addEventListener("change", () => {
      const selected = Array.from(input.files || []);
      if (!selected.length) { clearSelection(); return; }
      selectionVersion += 1;
      pendingFiles = selected;
      input.dataset.imageConfirmed = "false";
      confirmOk.classList.remove("hidden");
      confirmLabel.textContent = "¿Confirmar imagen seleccionada?";
      renderImagePreview(target, selected, objectUrls);
      confirmBar.classList.remove("hidden");
    });

    confirmOk.addEventListener("click", () => {
      input.dataset.imageConfirmed = "true";
      confirmOk.classList.add("hidden");
      confirmLabel.textContent = "Imagen confirmada y lista para subir.";
      applyFiles(pendingFiles);
      pendingFiles = [];
    });

    confirmCancel.addEventListener("click", () => {
      clearSelection();
    });

    input.form?.addEventListener("reset", () => window.setTimeout(clearSelection, 0));
  });

  document.addEventListener("submit", async (event) => {
    const unconfirmed = Array.from(event.target.querySelectorAll?.("[data-image-input]") || [])
      .find((input) => input.files?.length && input.dataset.imageConfirmed !== "true");
    if (unconfirmed) {
      event.preventDefault();
      toast("Confirma o cancela la imagen seleccionada antes de continuar.", "warning");
      unconfirmed.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    const pending = Array.from(event.target.querySelectorAll?.("[data-image-input]") || [])
      .map((input) => imageProcessing.get(input))
      .filter(Boolean);
    if (!pending.length) return;
    event.preventDefault();
    await Promise.allSettled(pending);
    event.target.requestSubmit(event.submitter || undefined);
  }, true);

  const supportModal = document.getElementById("support-modal");
  const supportLauncher = document.getElementById("support-launcher");
  const supportForm = document.getElementById("support-form");
  const supportClose = document.getElementById("support-close");
  const supportCancel = document.getElementById("support-cancel");
  const supportCsrf = document.getElementById("support-csrf");
  const supportMessage = document.getElementById("support-message");
  const supportSubmit = document.getElementById("support-submit");

  async function ensureSupportCsrf() {
    if (supportCsrf?.value) return true;
    const response = await fetch("/support/csrf", { headers: { Accept: "application/json" } });
    if (!response.ok) return false;
    const data = await response.json();
    supportCsrf.value = data.csrf_token || "";
    return Boolean(supportCsrf.value);
  }

  function openSupport() {
    if (!supportModal) return;
    supportModal.classList.add("is-open");
    supportModal.setAttribute("aria-hidden", "false");
    document.body.classList.add("modal-open");
    ensureSupportCsrf().catch(() => toast("No pudimos preparar el formulario de soporte.", "error"));
    window.setTimeout(() => supportMessage?.focus(), 180);
  }

  function closeSupport() {
    supportModal?.classList.remove("is-open");
    supportModal?.setAttribute("aria-hidden", "true");
    document.body.classList.remove("modal-open");
  }

  supportLauncher?.addEventListener("click", openSupport);
  supportClose?.addEventListener("click", closeSupport);
  supportCancel?.addEventListener("click", closeSupport);
  supportModal?.addEventListener("click", (event) => {
    if (event.target === supportModal) closeSupport();
  });

  supportForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const now = Date.now();
    if (now - Number(supportForm.dataset.lastSubmit || 0) < 2500) return;
    supportForm.dataset.lastSubmit = String(now);
    supportSubmit.disabled = true;
    supportSubmit.textContent = "Enviando…";
    try {
      if (!(await ensureSupportCsrf())) throw new Error("csrf");
      const response = await fetch(supportForm.action, {
        method: "POST",
        body: new FormData(supportForm),
        headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.message || "No pudimos crear el ticket.");
      toast(data.message, "success");
      supportForm.reset();
      closeSupport();
    } catch (error) {
      toast(error.message === "csrf" ? "La sesión del formulario expiró. Intenta nuevamente." : error.message, "error");
    } finally {
      supportSubmit.disabled = false;
      supportSubmit.textContent = "Enviar ticket";
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && supportModal?.classList.contains("is-open")) closeSupport();
  });

  const notificationBadge = document.getElementById("notification-badge");
  if (!notificationBadge) return;
  const seenKey = `dart.notifications.seen.${notificationBadge.dataset.notificationUser || "user"}`;
  let realtimeSocket = null;
  let reconnectAttempts = 0;
  let pollTimer = null;
  let heartbeatTimer = null;

  function renderBadge(count) {
    notificationBadge.textContent = count > 99 ? "99+" : String(count);
    notificationBadge.classList.toggle("hidden", count < 1);
    notificationBadge.classList.toggle("inline-flex", count > 0);
    notificationBadge.classList.toggle("has-updates", count > 0);
  }

  async function pollNotifications() {
    try {
      const response = await fetch("/api/notificaciones", { headers: { Accept: "application/json" }, cache: "no-store" });
      if (!response.ok) return;
      const data = await response.json();
      renderBadge(Number(data.unread_count || 0));
      const notifications = Array.isArray(data.notifications) ? data.notifications : [];
      const stored = localStorage.getItem(seenKey);
      const seen = new Set(stored ? JSON.parse(stored) : notifications.map((item) => item.id));
      notifications.slice().reverse().forEach((item) => {
        if (!item.read && !seen.has(item.id)) toast(`${item.title}: ${item.message}`, "success");
        seen.add(item.id);
      });
      localStorage.setItem(seenKey, JSON.stringify(Array.from(seen).slice(-100)));
    } catch (_) {
      // El polling es complementario y nunca debe interrumpir el uso de la app.
    }
  }

  function rememberNotification(notification) {
    const stored = localStorage.getItem(seenKey);
    let ids = [];
    try { ids = stored ? JSON.parse(stored) : []; } catch (_) { ids = []; }
    if (ids.includes(notification.id)) return false;
    ids.push(notification.id);
    localStorage.setItem(seenKey, JSON.stringify(ids.slice(-100)));
    return true;
  }

  function stopFallbackPolling() {
    if (pollTimer) window.clearInterval(pollTimer);
    pollTimer = null;
  }

  function startFallbackPolling() {
    if (pollTimer) return;
    pollNotifications();
    pollTimer = window.setInterval(pollNotifications, 45000);
  }

  function connectRealtime() {
    if (!("WebSocket" in window)) { startFallbackPolling(); return; }
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    realtimeSocket = new WebSocket(`${protocol}//${location.host}/ws/notifications`);
    realtimeSocket.addEventListener("open", () => {
      reconnectAttempts = 0;
      stopFallbackPolling();
      heartbeatTimer = window.setInterval(() => {
        if (realtimeSocket?.readyState === WebSocket.OPEN) realtimeSocket.send(JSON.stringify({ type: "ping" }));
      }, 25000);
    });
    realtimeSocket.addEventListener("message", (event) => {
      let payload;
      try { payload = JSON.parse(event.data); } catch (_) { return; }
      if (payload.type === "ready") {
        renderBadge(Number(payload.unread_count || 0));
        return;
      }
      if (payload.type !== "notification" || !payload.notification) return;
      const notification = payload.notification;
      if (rememberNotification(notification)) {
        toast(`${notification.title}: ${notification.message}`, "success");
        const current = Number(notificationBadge.textContent.replace("+", "")) || 0;
        renderBadge(current + (notification.read ? 0 : 1));
      }
      console.info("REALTIME_NOTIFICATION_RECEIVED", notification.id);
      realtimeSocket.send(JSON.stringify({ type: "ack", notification_id: notification.id }));
    });
    realtimeSocket.addEventListener("close", () => {
      if (heartbeatTimer) window.clearInterval(heartbeatTimer);
      heartbeatTimer = null;
      startFallbackPolling();
      const delay = Math.min(30000, 1000 * (2 ** reconnectAttempts));
      reconnectAttempts += 1;
      window.setTimeout(connectRealtime, delay);
    });
    realtimeSocket.addEventListener("error", () => realtimeSocket?.close());
  }

  pollNotifications().finally(connectRealtime);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && realtimeSocket?.readyState !== WebSocket.OPEN) pollNotifications();
  });
})();
