// The theme picker in the sidebar's footer.
//
// Served by `python -m concentric.dashboard` at /theme.js. The <select> itself is
// injected server-side (the launcher reads the option list out of themes.css, so
// the two cannot disagree); this only wires it up.
//
// A theme is one attribute: data-irina-theme on <html>. themes.css carries a
// block per theme, and a second block under [data-theme="light"] for the light
// variant where the palette has one — so this composes with waku's own
// light/dark toggle instead of fighting it.
(function () {
  const KEY = "irina-theme";
  const picker = document.getElementById("irina-theme");
  if (!picker) return;

  const apply = (name) => {
    if (name) document.documentElement.dataset.irinaTheme = name;
    else delete document.documentElement.dataset.irinaTheme;
  };

  let saved = "";
  try {
    saved = localStorage.getItem(KEY) || "";
  } catch (e) { /* private mode */ }
  // A theme that no longer exists must not strand the dashboard on it.
  if (saved && !picker.querySelector('option[value="' + saved + '"]')) saved = "";

  picker.value = saved;
  apply(saved);

  picker.addEventListener("change", () => {
    apply(picker.value);
    try {
      localStorage.setItem(KEY, picker.value);
    } catch (e) { /* private mode */ }
  });
})();
