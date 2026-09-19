// ---- icons.
//
// One helper, so a view writes `icon("home")` instead of hand-writing an <svg>.
// The drawings are vendored files under /icons/ and painted with a CSS mask, so
// an icon takes the colour of the text it sits in and needs no colour of its
// own — which is the only way it can follow all thirty-four themes.
//
// Names are the file names in concentric/static/icons/. A name with no file
// renders an empty box rather than nothing, so a typo is visible instead of
// silent.
(function () {
  "use strict";

  window.icon = (name, cls) =>
    `<i class="ic ic-${name}${cls ? " " + cls : ""}" aria-hidden="true"></i>`;
})();
