(function () {
  "use strict";

  var projectId = document.body.getAttribute("data-project-id");
  var editable = document.body.getAttribute("data-editable") === "true";
  if (!editable || !projectId) return;

  function closestEditable(el) {
    while (el && el !== document) {
      if (el.classList && el.classList.contains("is-editable")) return el;
      el = el.parentNode;
    }
    return null;
  }

  function hideOriginalContent(host) {
    var children = Array.from(host.childNodes);
    children.forEach(function (child) {
      if (child.nodeType === 1 && child.classList && child.classList.contains("inline-editor")) return;
      if (child.nodeType === 1) {
        child.setAttribute("data-was-display", child.style.display || "");
        child.style.display = "none";
      } else if (child.nodeType === 3) {
        child._originalText = child.textContent;
        child.textContent = "";
      }
    });
  }

  function restoreOriginalContent(host) {
    var children = Array.from(host.childNodes);
    children.forEach(function (child) {
      if (child.nodeType === 1 && child.classList && child.classList.contains("inline-editor")) return;
      if (child.nodeType === 1 && child.hasAttribute("data-was-display")) {
        child.style.display = child.getAttribute("data-was-display");
        child.removeAttribute("data-was-display");
      } else if (child.nodeType === 3 && child._originalText !== undefined) {
        child.textContent = child._originalText;
        delete child._originalText;
      }
    });
  }

  function closeEditor(host) {
    var form = host.querySelector(".inline-editor");
    if (form) form.remove();
    host.classList.remove("editing");
    restoreOriginalContent(host);
  }

  function openEditor(host) {
    if (host.querySelector(".inline-editor")) return;
    var blockId = host.getAttribute("data-block-id");
    var raw = host.getAttribute("data-raw") || "";

    host.classList.add("editing");
    hideOriginalContent(host);

    var form = document.createElement("form");
    form.className = "inline-editor";
    form.addEventListener("click", function (ev) {
      ev.stopPropagation();
    });
    var ta = document.createElement("textarea");
    ta.name = "text";
    ta.value = raw;
    ta.rows = Math.max(4, raw.split("\n").length + 2);
    var actions = document.createElement("div");
    actions.className = "inline-editor-actions";
    var save = document.createElement("button");
    save.type = "submit";
    save.className = "ed-btn";
    save.textContent = "Guardar";
    var cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "ed-btn ed-secondary";
    cancel.textContent = "Cancelar";
    var del = document.createElement("button");
    del.type = "button";
    del.className = "ed-btn ed-danger";
    del.textContent = "Eliminar";
    actions.appendChild(save);
    actions.appendChild(cancel);
    actions.appendChild(del);
    form.appendChild(ta);
    form.appendChild(actions);
    host.appendChild(form);
    ta.focus();

    cancel.addEventListener("click", function () {
      closeEditor(host);
    });

    del.addEventListener("click", function () {
      if (!confirm("¿Eliminar este párrafo? El documento se recompactará.")) return;
      post("/projects/" + projectId + "/content/" + encodeURIComponent(blockId) + "/delete", new FormData());
    });

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var data = new FormData();
      data.append("text", ta.value);
      post("/projects/" + projectId + "/content/" + encodeURIComponent(blockId), data);
    });
  }

  function post(url, data) {
    fetch(url, {
      method: "POST",
      headers: { Accept: "application/json" },
      body: data,
    })
      .then(function (res) {
        if (!res.ok) throw new Error("No se pudo guardar");
        return res.json();
      })
      .then(function () {
        window.location.reload();
      })
      .catch(function (err) {
        alert(err.message || "Error al guardar");
      });
  }

  document.addEventListener("click", function (ev) {
    if (ev.target.closest(".inline-editor")) return;

    var host = closestEditable(ev.target);
    if (!host) return;

    // Prevent native text selection from firing on editable elements
    ev.preventDefault();

    // Clear any browser text selection that may have happened
    if (window.getSelection) {
      window.getSelection().removeAllRanges();
    }

    openEditor(host);
  });
})();
