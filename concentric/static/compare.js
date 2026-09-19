// ---- Model & Memory LAB.
//
// waku ships the two races as two rail entries. They are one question asked
// twice — which brain, and which memory — so the rail carries one row and the
// races become its tabs. Neither page is touched: both are waku's own, called
// here exactly as the router would have called them.
(function () {
  "use strict";

  const base = VIEWS.compare;

  VIEWS.compare = (d, sub) => {
    const tabs = uiTabs([
      { label: "Model race", href: "#compare/models", on: sub !== "memory" },
      { label: "Memory race", href: "#compare/memory", on: sub === "memory" },
    ]);
    return tabs + base(d, sub);
  };
})();
