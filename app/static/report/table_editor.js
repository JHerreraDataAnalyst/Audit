(function () {
  "use strict";

  var projectId = document.body.getAttribute("data-project-id");
  var editable = document.body.getAttribute("data-editable") === "true";
  if (!editable || !projectId) return;

  function formatES(num) {
    if (num == null || isNaN(num)) return "";
    var s = Math.abs(num).toFixed(2);
    var parts = s.split(".");
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    var formatted = parts.join(",");
    return num < 0 ? "(" + formatted + ")" : formatted;
  }

  function parseES(str) {
    if (!str || str.trim() === "-" || str.trim() === "–") return null;
    var clean = str.trim();
    var neg = false;
    if (clean.startsWith("(") && clean.endsWith(")")) {
      neg = true;
      clean = clean.slice(1, -1).trim();
    } else if (clean.startsWith("-")) {
      neg = true;
      clean = clean.slice(1).trim();
    }
    clean = clean.replace(/\./g, "").replace(",", ".");
    var val = parseFloat(clean);
    if (isNaN(val)) return null;
    return neg ? -val : val;
  }

  var panel = null;
  var panelDoc = null;
  var usingParentHost = false;

  function getParentHost() {
    try {
      if (window.parent && window.parent !== window && window.parent.document) {
        var mount = window.parent.document.getElementById("preview-side-panel");
        var workspace = window.parent.document.getElementById("preview-workspace");
        if (mount && workspace) {
          return {
            doc: window.parent.document,
            mount: mount,
            workspace: workspace,
          };
        }
      }
    } catch (err) {
      /* cross-origin or unavailable */
    }
    return null;
  }

  function clearTableHighlights() {
    document.querySelectorAll(".table-focus, tr.row-focus, td.note-focus").forEach(function (el) {
      el.classList.remove("table-focus");
      el.classList.remove("row-focus");
      el.classList.remove("note-focus");
    });
  }

  function highlightSourceTable(tableId) {
    clearTableHighlights();
    var pages = document.getElementById("doc-pages") || document;
    var wraps = pages.querySelectorAll(
      '.is-editable-table[data-table-id="' + tableId + '"], table[data-table-id="' + tableId + '"]'
    );
    wraps.forEach(function (wrap) {
      // Only mark visible paginated copies, never #doc-flow (off-screen measure source).
      if (wrap.closest && wrap.closest("#doc-flow")) return;
      wrap.classList.add("table-focus");
    });
  }

  function closePanel() {
    if (!panel) return;
    panel.classList.remove("active");
    clearTableHighlights();
    if (usingParentHost && panelDoc) {
      var workspace = panelDoc.getElementById("preview-workspace");
      if (workspace) workspace.classList.remove("panel-open");
      var mount = panelDoc.getElementById("preview-side-panel");
      if (mount) {
        mount.hidden = true;
        mount.setAttribute("aria-hidden", "true");
      }
    } else {
      document.body.classList.remove("table-editor-open");
    }
  }

  function ensureLocalPanel() {
    var existing = document.getElementById("table-side-panel");
    if (existing) return existing;

    var el = document.createElement("aside");
    el.id = "table-side-panel";
    el.className = "table-side-panel";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-modal", "false");
    el.innerHTML =
      '<div class="table-side-panel-inner">' +
        '<div class="table-modal-header">' +
          "<div>" +
            '<h3 class="table-modal-title"></h3>' +
            '<div class="table-modal-subtitle"></div>' +
          "</div>" +
          '<button type="button" class="table-modal-close" title="Cerrar">✕</button>' +
        "</div>" +
        '<div class="table-modal-body"></div>' +
        '<div class="table-modal-impact"></div>' +
        '<div class="table-modal-validation"></div>' +
        '<div class="table-modal-footer">' +
          '<button type="button" class="ed-btn table-modal-save">Guardar cambios</button>' +
          '<button type="button" class="ed-btn ed-secondary table-modal-cancel">Cerrar</button>' +
        "</div>" +
      "</div>";
    document.body.appendChild(el);
    el.querySelector(".table-modal-close").addEventListener("click", closePanel);
    el.querySelector(".table-modal-cancel").addEventListener("click", closePanel);
    return el;
  }

  function ensureParentPanel(host) {
    var mount = host.mount;
    if (!mount.querySelector(".table-side-panel-inner")) {
      mount.innerHTML =
        '<div class="table-side-panel-inner">' +
          '<div class="table-modal-header">' +
            "<div>" +
              '<h3 class="table-modal-title"></h3>' +
              '<div class="table-modal-subtitle"></div>' +
            "</div>" +
            '<button type="button" class="table-modal-close" title="Cerrar">✕</button>' +
          "</div>" +
          '<div class="table-modal-body"></div>' +
          '<div class="table-modal-impact"></div>' +
          '<div class="table-modal-validation"></div>' +
          '<div class="table-modal-footer">' +
            '<button type="button" class="ed-btn table-modal-save">Guardar cambios</button>' +
            '<button type="button" class="ed-btn ed-secondary table-modal-cancel">Cerrar</button>' +
          "</div>" +
        "</div>";
      mount.querySelector(".table-modal-close").addEventListener("click", closePanel);
      mount.querySelector(".table-modal-cancel").addEventListener("click", closePanel);
    }
    return mount;
  }

  function getPanel() {
    var host = getParentHost();
    if (host) {
      usingParentHost = true;
      panelDoc = host.doc;
      panel = ensureParentPanel(host);
      return panel;
    }
    usingParentHost = false;
    panelDoc = document;
    panel = ensureLocalPanel();
    return panel;
  }

  function showPanel() {
    var m = getPanel();
    m.classList.add("active");
    m.hidden = false;
    m.setAttribute("aria-hidden", "false");
    if (usingParentHost && panelDoc) {
      var workspace = panelDoc.getElementById("preview-workspace");
      if (workspace) workspace.classList.add("panel-open");
    } else {
      document.body.classList.add("table-editor-open");
    }
    return m;
  }

  function findSourceTable(tableId) {
    var source = document.getElementById("doc-flow");
    if (source) {
      var full =
        source.querySelector('.is-editable-table[data-table-id="' + tableId + '"] table') ||
        source.querySelector('table[data-table-id="' + tableId + '"]');
      if (full) return full;
    }
    var pages = document.getElementById("doc-pages");
    if (pages) {
      var visible =
        pages.querySelector('.is-editable-table[data-table-id="' + tableId + '"] table') ||
        pages.querySelector('table[data-table-id="' + tableId + '"]');
      if (visible) return visible;
    }
    return (
      document.querySelector('.is-editable-table[data-table-id="' + tableId + '"] table') ||
      document.querySelector('table[data-table-id="' + tableId + '"]')
    );
  }

  function isEditableAmountCell(cell) {
    if (!cell) return false;
    if (cell.classList.contains("amount")) return true;
    var numericVal = cell.getAttribute("data-numeric");
    return numericVal !== null && numericVal !== "";
  }

  function openTableEditor(tableId, headingHint) {
    if (!tableId) return;

    var originalTable = findSourceTable(tableId);
    if (!originalTable) {
      alert("No se pudo abrir la tabla para editar.");
      return;
    }

    highlightSourceTable(tableId);

    var m = showPanel();
    var title = m.querySelector(".table-modal-title");
    var subtitle = m.querySelector(".table-modal-subtitle");
    var body = m.querySelector(".table-modal-body");
    var impactDiv = m.querySelector(".table-modal-impact");
    var validationDiv = m.querySelector(".table-modal-validation");
    var saveBtn = m.querySelector(".table-modal-save");

    var tableHeading = headingHint || "";
    if (!tableHeading) {
      if (tableId === "balance_asset" || tableId === "balance_equity") {
        tableHeading = "Balance de Situación";
      } else if (tableId === "pyg_statement") {
        tableHeading = "Cuenta de pérdidas y ganancias";
      } else {
        tableHeading = "Editar tabla";
      }
    }

    title.textContent = tableHeading;
    subtitle.textContent = "Tabla activa en el informe. Esc o ✕ para cerrar.";
    body.innerHTML = "";
    impactDiv.innerHTML = "";
    validationDiv.innerHTML = "";
    saveBtn.disabled = false;
    saveBtn.textContent = "Guardar cambios";

    var doc = panelDoc || document;
    var editTable = doc.createElement("table");
    editTable.className = "fin-table modal-edit-table";

    var thead = originalTable.querySelector("thead");
    if (thead) editTable.appendChild(doc.importNode(thead, true));

    var tbody = doc.createElement("tbody");
    var rows = originalTable.querySelectorAll("tbody tr");
    var editableCount = 0;

    rows.forEach(function (row, rowIdx) {
      var tr = doc.createElement("tr");
      tr.className = row.className;
      var lineId = row.getAttribute("data-line-id") || "";
      if (lineId) tr.setAttribute("data-line-id", lineId);

      var labelCell = row.querySelector("td.label") || row.querySelector("td");
      var rowLabel = labelCell ? labelCell.textContent.trim() : "";

      row.querySelectorAll("td").forEach(function (cell, colIdx) {
        var td = doc.createElement("td");
        td.className = cell.className;

        var numericVal = cell.getAttribute("data-numeric");
        if (isEditableAmountCell(cell) && numericVal !== null && numericVal !== "") {
          editableCount += 1;
          var input = doc.createElement("input");
          input.type = "text";
          input.className = "table-cell-input";
          var parsed = parseFloat(numericVal);
          input.value = isNaN(parsed) ? cell.textContent.trim() : formatES(parsed);
          input.setAttribute("data-row", String(rowIdx));
          input.setAttribute("data-col", cell.getAttribute("data-col") || String(colIdx));
          input.setAttribute("data-line-id", lineId);
          input.setAttribute("data-label", rowLabel);
          input.setAttribute("data-original", numericVal);

          input.addEventListener("focus", function () {
            var n = parseES(this.value);
            if (n !== null) this.value = String(n);
            this.select();
            checkConceptImpact(this.getAttribute("data-label"), impactDiv);
          });
          input.addEventListener("blur", function () {
            var n = parseES(this.value);
            if (n !== null) this.value = formatES(n);
            recalcTotals(editTable, validationDiv);
          });
          input.addEventListener("input", function () {
            recalcTotals(editTable, validationDiv);
          });
          td.appendChild(input);
        } else {
          td.textContent = cell.textContent;
          if (cell.style.fontWeight) td.style.fontWeight = cell.style.fontWeight;
        }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });

    editTable.appendChild(tbody);
    body.appendChild(editTable);

    if (editableCount === 0) {
      var note = doc.createElement("p");
      note.className = "table-modal-empty";
      note.textContent =
        "Esta tabla no tiene celdas numéricas editables en el modelo actual. Puedes cerrar con ✕ o Esc.";
      body.insertBefore(note, editTable);
      saveBtn.style.display = "none";
    } else {
      saveBtn.style.display = "";
    }

    window.setTimeout(function () {
      var firstInput = editTable.querySelector(".table-cell-input");
      if (!firstInput) return;
      // Focus without scrolling the report preview.
      try {
        firstInput.focus({ preventScroll: true });
      } catch (err) {
        firstInput.focus();
      }
    }, 30);

    saveBtn.onclick = function () {
      saveBtn.disabled = true;
      saveBtn.textContent = "Guardando...";
      saveTable(
        tableId,
        editTable,
        function () {
          closePanel();
          window.location.reload();
        },
        function (err) {
          saveBtn.disabled = false;
          saveBtn.textContent = "Guardar cambios";
          alert("Error al guardar: " + err);
        }
      );
    };

    recalcTotals(editTable, validationDiv);
  }

  var impactCache = {};
  function checkConceptImpact(label, impactDiv) {
    if (!label || label.length < 4 || label.toLowerCase().startsWith("total")) {
      impactDiv.innerHTML = "";
      return;
    }
    if (impactCache[label]) {
      renderImpact(impactCache[label], impactDiv);
      return;
    }
    fetch("/projects/" + projectId + "/concept-impact?label=" + encodeURIComponent(label))
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        impactCache[label] = data.impacts || [];
        renderImpact(impactCache[label], impactDiv);
      })
      .catch(function () {
        impactDiv.innerHTML = "";
      });
  }

  function renderImpact(impacts, impactDiv) {
    if (!impacts || impacts.length <= 1) {
      impactDiv.innerHTML = "";
      return;
    }
    var html =
      '<div class="impact-box">' +
      '<div class="impact-title">Concepto vinculado en otras partes:</div>' +
      '<div class="impact-list">';
    impacts.slice(0, 3).forEach(function (item) {
      var amt = item.n_fmt
        ? item.n_fmt + " €"
        : item.amounts
          ? Object.values(item.amounts).join(" / ") + " €"
          : "";
      html +=
        '<span class="impact-tag"><strong>' +
        item.source +
        ":</strong> " +
        (item.label || "") +
        (amt ? " (" + amt + ")" : "") +
        "</span>";
    });
    html += "</div></div>";
    impactDiv.innerHTML = html;
  }

  function recalcTotals(editTable, validationDiv) {
    var rows = editTable.querySelectorAll("tbody tr");
    var changedCount = 0;
    var mathMismatches = [];
    var colSums = {};
    var colTotals = {};

    rows.forEach(function (row, rIdx) {
      var isTotal = row.classList.contains("is-total") || row.classList.contains("is-subtotal");
      row.querySelectorAll(".table-cell-input").forEach(function (inp) {
        var col = inp.getAttribute("data-col");
        var val = parseES(inp.value);
        var orig = parseFloat(inp.getAttribute("data-original"));
        if (val !== null && !isNaN(orig) && Math.abs(val - orig) > 0.01) {
          inp.classList.add("cell-changed");
          changedCount++;
        } else {
          inp.classList.remove("cell-changed");
        }
        if (val !== null) {
          if (isTotal) {
            colTotals[col] = {
              val: val,
              rowIdx: rIdx,
              label: row.querySelector("td") ? row.querySelector("td").textContent.trim() : "",
            };
          } else {
            colSums[col] = (colSums[col] || 0) + val;
          }
        }
      });
    });

    Object.keys(colTotals).forEach(function (col) {
      var tot = colTotals[col];
      var sum = colSums[col];
      if (sum !== undefined && Math.abs(sum - tot.val) > 0.5) {
        mathMismatches.push({
          label: tot.label || "Total",
          sum: sum,
          tot: tot.val,
          diff: Math.abs(sum - tot.val),
        });
      }
    });

    validationDiv.innerHTML = "";
    var ownerDoc = validationDiv.ownerDocument || document;
    if (mathMismatches.length > 0) {
      var m0 = mathMismatches[0];
      var warn = ownerDoc.createElement("div");
      warn.className = "validation-badge warning";
      warn.textContent =
        "Descuadre: suma (" +
        formatES(m0.sum) +
        ") ≠ " +
        m0.label +
        " (" +
        formatES(m0.tot) +
        ").";
      validationDiv.appendChild(warn);
    } else if (changedCount > 0) {
      var info = ownerDoc.createElement("div");
      info.className = "validation-badge ok";
      info.textContent = changedCount + " celda(s) editada(s).";
      validationDiv.appendChild(info);
    }
  }

  function saveTable(tableId, editTable, onSuccess, onError) {
    var updates = [];
    editTable.querySelectorAll(".table-cell-input").forEach(function (input) {
      updates.push({
        row: parseInt(input.getAttribute("data-row"), 10),
        col: input.getAttribute("data-col"),
        line_id: input.getAttribute("data-line-id") || "",
        numeric: parseES(input.value),
        value: input.value,
      });
    });

    fetch("/projects/" + projectId + "/tables/" + encodeURIComponent(tableId), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ cells: updates }),
    })
      .then(function (res) {
        if (!res.ok) throw new Error("Error al guardar la tabla");
        return res.json();
      })
      .then(function () {
        onSuccess();
      })
      .catch(function (err) {
        if (onError) onError(err.message || err);
      });
  }

  function resolveTableClick(target) {
    if (!target || !target.closest) return null;
    if (target.closest(".inline-editor")) return null;
    if (target.closest(".table-side-panel") || target.closest("#preview-side-panel")) return null;
    if (target.closest(".table-modal-overlay")) return null;

    var container =
      target.closest(".is-editable-table[data-table-id]") ||
      target.closest("table[data-table-id]") ||
      target.closest("[data-table-id]");
    if (!container) return null;

    var tableId = container.getAttribute("data-table-id");
    if (!tableId && container.closest) {
      var wrap = container.closest("[data-table-id]");
      if (wrap) tableId = wrap.getAttribute("data-table-id");
    }
    if (!tableId) return null;

    var heading = "";
    var prev = (container.closest(".comp-table") || container).previousElementSibling;
    while (prev && !heading) {
      if (/^H[1-6]$/i.test(prev.tagName)) heading = prev.textContent.trim();
      prev = prev.previousElementSibling;
    }

    return { tableId: tableId, heading: heading };
  }

  document.addEventListener(
    "click",
    function (ev) {
      var hit = resolveTableClick(ev.target);
      if (!hit) return;
      ev.preventDefault();
      ev.stopPropagation();
      openTableEditor(hit.tableId, hit.heading);
    },
    true
  );

  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") closePanel();
  });

  try {
    if (window.parent && window.parent !== window) {
      window.parent.addEventListener("keydown", function (ev) {
        if (ev.key === "Escape") closePanel();
      });
    }
  } catch (err) {
    /* ignore */
  }
})();
