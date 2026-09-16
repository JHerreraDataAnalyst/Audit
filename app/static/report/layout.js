(function () {
  "use strict";

  function paginate() {
    var source = document.getElementById("doc-flow");
    var dest = document.getElementById("doc-pages");
    if (!source || !dest) return;

    dest.innerHTML = "";
    var nodes = Array.from(source.children);
    var body = null;

    function makeSheet() {
      var section = document.createElement("section");
      section.className = "sheet";
      var inner = document.createElement("div");
      inner.className = "sheet-body";
      var footer = document.createElement("footer");
      footer.className = "page-footer";
      var left = document.createElement("span");
      left.className = "footer-left";
      left.textContent = document.body.getAttribute("data-footer-left") || "";
      var right = document.createElement("span");
      right.className = "footer-right";
      footer.appendChild(left);
      footer.appendChild(right);
      section.appendChild(inner);
      section.appendChild(footer);
      dest.appendChild(section);
      return { body: inner };
    }

    function overflows(container) {
      return container.scrollHeight - container.clientHeight > 1;
    }

    function ensureSheet() {
      if (!body) body = makeSheet().body;
    }

    function newSheet() {
      body = makeSheet().body;
    }

    function wrapTable(tableEl, wrapperTemplate) {
      if (!wrapperTemplate) return tableEl;
      var wrap = wrapperTemplate.cloneNode(false);
      // Keep editable metadata on every split fragment
      Array.from(wrapperTemplate.attributes).forEach(function (attr) {
        wrap.setAttribute(attr.name, attr.value);
      });
      wrap.appendChild(tableEl);
      return wrap;
    }

    function splitTable(table, wrapperTemplate) {
      var rows = Array.from(table.querySelectorAll("tbody tr"));
      if (!rows.length) return false;
      var thead = table.querySelector("thead");
      var caption = table.querySelector("caption");
      var index = 0;
      var placedAny = false;

      function emptyTable() {
        var t = table.cloneNode(false);
        t.className = table.className;
        if (table.getAttribute("data-table-id")) {
          t.setAttribute("data-table-id", table.getAttribute("data-table-id"));
        }
        if (caption) t.appendChild(caption.cloneNode(true));
        if (thead) t.appendChild(thead.cloneNode(true));
        var tb = document.createElement("tbody");
        t.appendChild(tb);
        return t;
      }

      while (index < rows.length) {
        ensureSheet();
        var t = emptyTable();
        var tb = t.querySelector("tbody");
        var wrapped = wrapTable(t, wrapperTemplate);
        body.appendChild(wrapped);
        var added = 0;
        while (index < rows.length) {
          tb.appendChild(rows[index].cloneNode(true));
          if (overflows(body)) {
            tb.removeChild(tb.lastElementChild);
            break;
          }
          index += 1;
          added += 1;
        }
        if (added === 0) {
          body.removeChild(wrapped);
          if (body.childElementCount === 0) {
            body.appendChild(wrapped);
            tb.appendChild(rows[index].cloneNode(true));
            index += 1;
            placedAny = true;
            if (index < rows.length) newSheet();
            continue;
          }
          newSheet();
          continue;
        }
        placedAny = true;
        if (index < rows.length) newSheet();
      }
      return placedAny;
    }

    function placeNode(node) {
      ensureSheet();
      var table = node.matches("table") ? node : node.querySelector("table");
      var wrapperTemplate = node.classList.contains("comp-table") ? node : null;
      var clone = node.cloneNode(true);
      body.appendChild(clone);
      if (!overflows(body)) return;
      body.removeChild(clone);
      if (table && (node.matches("table") || node.classList.contains("comp-table"))) {
        splitTable(table, wrapperTemplate);
        return;
      }
      if (body.childElementCount === 0) {
        body.appendChild(clone);
        return;
      }
      newSheet();
      body.appendChild(clone);
      if (overflows(body) && table && node.classList.contains("comp-table")) {
        body.removeChild(clone);
        splitTable(table, wrapperTemplate);
      }
    }

    var i = 0;
    while (i < nodes.length) {
      var node = nodes[i];
      if (node.getAttribute("data-keep-with-next") === "true") {
        var group = [node];
        var j = i;
        while (j < nodes.length && nodes[j].getAttribute("data-keep-with-next") === "true") {
          j += 1;
          if (j < nodes.length) group.push(nodes[j]);
          else break;
        }
        ensureSheet();
        var placed = [];
        group.forEach(function (n) {
          var c = n.cloneNode(true);
          body.appendChild(c);
          placed.push(c);
        });
        if (overflows(body) && body.childElementCount > placed.length) {
          placed.forEach(function (c) {
            body.removeChild(c);
          });
          newSheet();
          group.forEach(placeNode);
        } else if (overflows(body)) {
          placed.forEach(function (c) {
            body.removeChild(c);
          });
          group.forEach(placeNode);
        }
        i += group.length;
        continue;
      }
      placeNode(node);
      i += 1;
    }

    var sheets = dest.querySelectorAll(".sheet");
    var total = sheets.length || 1;
    var titles = [];
    var pages = [];

    sheets.forEach(function (s, idx) {
      var pageNum = idx + 1;
      s.setAttribute("data-page-index", String(pageNum));
      s.setAttribute("id", "report-page-" + pageNum);
      var slot = s.querySelector(".footer-right");
      if (slot) slot.textContent = String(pageNum) + " / " + String(total);
      pages.push({ page: pageNum, id: "report-page-" + pageNum });

      var headingNodes = s.querySelectorAll(
        "h1.comp-heading1, h2.comp-heading2, h2.comp-heading, .section-header .stmt-title, .cover-entity"
      );
      headingNodes.forEach(function (h, hIdx) {
        var text = (h.textContent || "").replace(/\s+/g, " ").trim();
        if (!text) return;
        var level = 1;
        if (h.classList.contains("comp-heading2") || h.classList.contains("comp-heading")) level = 2;
        if (h.classList.contains("stmt-title")) level = 1;
        if (h.classList.contains("cover-entity")) level = 1;
        var navId = "nav-" + pageNum + "-" + hIdx;
        h.setAttribute("data-nav-id", navId);
        h.setAttribute("id", navId);
        titles.push({
          id: navId,
          text: text,
          level: level,
          page: pageNum,
        });
      });
    });
    if (sheets[0]) sheets[0].classList.add("sheet-first");

    document.documentElement.dataset.layoutReady = "1";
    document.documentElement.dataset.pageCount = String(total);
    var height = dest.getBoundingClientRect().height + 48;
    window.parent.postMessage({ type: "report-layout", height: height, pages: total }, "*");
    window.parent.postMessage({ type: "report-nav", titles: titles, pages: pages }, "*");
  }

  function clearNavFlash() {
    document.querySelectorAll(".nav-target-flash").forEach(function (el) {
      el.classList.remove("nav-target-flash");
    });
  }

  function navigateTo(payload) {
    if (!payload) return;
    clearNavFlash();
    var target = null;
    if (payload.id) {
      target = document.querySelector('[data-nav-id="' + payload.id + '"]') || document.getElementById(payload.id);
    } else if (payload.page) {
      target = document.getElementById("report-page-" + payload.page);
    }
    if (!target) return;
    try {
      target.scrollIntoView({ block: "start", behavior: "smooth" });
    } catch (err) {
      target.scrollIntoView(true);
    }
    target.classList.add("nav-target-flash");
    window.setTimeout(function () {
      target.classList.remove("nav-target-flash");
    }, 1600);
  }

  window.addEventListener("message", function (ev) {
    if (!ev.data || ev.data.type !== "report-navigate") return;
    navigateTo(ev.data);
  });

  function run() {
    document.documentElement.dataset.layoutReady = "0";
    paginate();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
  window.AuditLayout = { relayout: run, navigateTo: navigateTo };
})();
