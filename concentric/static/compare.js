// ---- Model & Memory LAB.
//
// Four pages that are one question asked from four angles — which brain, which
// memory, what shape, what it stored — and waku ships them as four rail rows.
// The rail carries one, and they become its tabs.
//
// No page is touched. Each is waku's own, called here exactly as the router
// called it, with the same tab bar in front. That is why the bar is rendered by
// three different views rather than one: the hash decides which view runs, so a
// shared bar has to be added to every view that shows it.
(function () {
  "use strict";

  const TABS = [
    { label: "Model race", href: "#compare/models" },
    { label: "Memory race", href: "#compare/memory" },
    { label: "Graph", href: "#graph" },
    { label: "Database", href: "#database" },
  ];

  function bar(active) {
    return uiTabs(TABS.map((t) => ({ label: t.label, href: t.href, on: t.label === active })));
  }

  const races = VIEWS.compare;
  const graph = VIEWS.graph;
  const database = VIEWS.database;

  VIEWS.compare = (d, sub) =>
    bar(sub === "memory" ? "Memory race" : "Model race") + races(d, sub);
  VIEWS.graph = (d, sub) => bar("Graph") + graph(d, sub);
  VIEWS.database = (d, sub) => bar("Database") + database(d, sub);
})();
