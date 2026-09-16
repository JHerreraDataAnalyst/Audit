(function () {
  "use strict";

  var frame = document.getElementById("report-preview");
  var navRoot = document.getElementById("preview-nav");
  if (!frame || !navRoot) return;

  var titles = [];
  var pages = [];
  var activeTab = "titles";
  var query = "";
  /** @type {Object.<string, boolean>} collapsed parent ids */
  var collapsed = {};

  var searchInput = navRoot.querySelector("[data-nav-search]");
  var listEl = navRoot.querySelector("[data-nav-list]");
  var tabButtons = navRoot.querySelectorAll("[data-nav-tab]");
  var closeBtn = navRoot.querySelector("[data-nav-close]");
  var expandAllBtn = navRoot.querySelector("[data-nav-expand-all]");
  var collapseAllBtn = navRoot.querySelector("[data-nav-collapse-all]");
  var openBtn = document.getElementById("preview-nav-open");
  var workspace = document.getElementById("preview-workspace");

  function postNavigate(payload) {
    if (!frame.contentWindow) return;
    frame.contentWindow.postMessage(
      {
        type: "report-navigate",
        id: payload.id || null,
        page: payload.page || null,
      },
      "*"
    );
  }

  function setOpen(open) {
    if (!workspace) return;
    workspace.classList.toggle("nav-open", open);
    navRoot.hidden = !open;
    navRoot.setAttribute("aria-hidden", open ? "false" : "true");
    if (openBtn) openBtn.hidden = open;
  }

  function buildTree(items) {
    var roots = [];
    var currentParent = null;
    items.forEach(function (t) {
      var node = {
        id: t.id,
        text: t.text,
        level: t.level || 1,
        page: t.page,
        children: [],
      };
      if (node.level <= 1 || !currentParent) {
        roots.push(node);
        currentParent = node;
      } else {
        currentParent.children.push(node);
      }
    });
    return roots;
  }

  function parentIdsWithChildren(tree) {
    var ids = [];
    tree.forEach(function (n) {
      if (n.children && n.children.length) ids.push(n.id);
    });
    return ids;
  }

  function expandAll() {
    collapsed = {};
    render();
  }

  function collapseAll() {
    var tree = buildTree(titles);
    collapsed = {};
    parentIdsWithChildren(tree).forEach(function (id) {
      collapsed[id] = true;
    });
    render();
  }

  function toggleCollapsed(id) {
    collapsed[id] = !collapsed[id];
    render();
  }

  function nodeMatches(node, q) {
    if (!q) return true;
    if (node.text.toLowerCase().indexOf(q) >= 0) return true;
    return (node.children || []).some(function (c) {
      return nodeMatches(c, q);
    });
  }

  function renderTreeNode(node, q) {
    if (q && !nodeMatches(node, q)) return null;

    var hasChildren = node.children && node.children.length > 0;
    var isCollapsed = !!collapsed[node.id];
    // While searching, keep matching branches expanded
    if (q) isCollapsed = false;

    var wrap = document.createElement("div");
    wrap.className = "preview-nav-node";

    var row = document.createElement("div");
    row.className = "preview-nav-row level-" + (node.level || 1);

    if (hasChildren) {
      var twisty = document.createElement("button");
      twisty.type = "button";
      twisty.className = "preview-nav-twisty" + (isCollapsed ? " is-collapsed" : "");
      twisty.title = isCollapsed ? "Expandir" : "Colapsar";
      twisty.setAttribute("aria-expanded", isCollapsed ? "false" : "true");
      twisty.textContent = isCollapsed ? "▸" : "▾";
      twisty.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        toggleCollapsed(node.id);
      });
      row.appendChild(twisty);
    } else {
      var spacer = document.createElement("span");
      spacer.className = "preview-nav-twisty-spacer";
      row.appendChild(spacer);
    }

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "preview-nav-item";
    btn.title = node.text;
    btn.innerHTML =
      '<span class="preview-nav-item-text"></span>' +
      '<span class="preview-nav-item-page">p. ' +
      node.page +
      "</span>";
    btn.querySelector(".preview-nav-item-text").textContent = node.text;
    btn.addEventListener("click", function () {
      listEl.querySelectorAll(".preview-nav-item").forEach(function (el) {
        el.classList.remove("is-active");
      });
      btn.classList.add("is-active");
      postNavigate({ id: node.id, page: node.page });
    });
    row.appendChild(btn);
    wrap.appendChild(row);

    if (hasChildren && !isCollapsed) {
      var kids = document.createElement("div");
      kids.className = "preview-nav-children";
      node.children.forEach(function (child) {
        var childEl = renderTreeNode(child, q);
        if (childEl) kids.appendChild(childEl);
      });
      wrap.appendChild(kids);
    }

    return wrap;
  }

  function render() {
    if (!listEl) return;
    listEl.innerHTML = "";
    var q = (query || "").trim().toLowerCase();
    var showTreeControls = activeTab === "titles";
    if (expandAllBtn) expandAllBtn.hidden = !showTreeControls;
    if (collapseAllBtn) collapseAllBtn.hidden = !showTreeControls;

    if (activeTab === "pages") {
      pages.forEach(function (p) {
        var label = "Página " + p.page;
        if (q && label.toLowerCase().indexOf(q) < 0) return;
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "preview-nav-item level-1";
        btn.textContent = label;
        btn.addEventListener("click", function () {
          listEl.querySelectorAll(".preview-nav-item").forEach(function (el) {
            el.classList.remove("is-active");
          });
          btn.classList.add("is-active");
          postNavigate({ page: p.page });
        });
        listEl.appendChild(btn);
      });
      if (!listEl.children.length) {
        listEl.innerHTML = '<p class="preview-nav-empty">Sin páginas</p>';
      }
      return;
    }

    if (!titles.length) {
      listEl.innerHTML = '<p class="preview-nav-empty">Cargando títulos…</p>';
      return;
    }

    var tree = buildTree(titles);
    var shown = 0;
    tree.forEach(function (node) {
      var el = renderTreeNode(node, q);
      if (el) {
        listEl.appendChild(el);
        shown += 1;
      }
    });

    if (!shown) {
      listEl.innerHTML = q
        ? '<p class="preview-nav-empty">Sin resultados</p>'
        : '<p class="preview-nav-empty">Sin títulos</p>';
    }
  }

  tabButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      activeTab = btn.getAttribute("data-nav-tab") || "titles";
      tabButtons.forEach(function (b) {
        b.classList.toggle("is-active", b === btn);
      });
      if (activeTab === "results") activeTab = "titles";
      render();
    });
  });

  if (searchInput) {
    searchInput.addEventListener("input", function () {
      query = searchInput.value || "";
      activeTab = "titles";
      tabButtons.forEach(function (b) {
        b.classList.toggle("is-active", b.getAttribute("data-nav-tab") === "titles");
      });
      render();
    });
  }

  if (expandAllBtn) {
    expandAllBtn.addEventListener("click", function () {
      expandAll();
    });
  }
  if (collapseAllBtn) {
    collapseAllBtn.addEventListener("click", function () {
      collapseAll();
    });
  }

  if (closeBtn) {
    closeBtn.addEventListener("click", function () {
      setOpen(false);
    });
  }
  if (openBtn) {
    openBtn.addEventListener("click", function () {
      setOpen(true);
    });
  }

  window.addEventListener("message", function (ev) {
    if (!ev.data) return;
    if (ev.data.type === "report-nav") {
      titles = ev.data.titles || [];
      pages = ev.data.pages || [];
      // Keep previously collapsed parents when possible; new parents start expanded
      render();
    }
  });

  setOpen(true);
  render();
})();
