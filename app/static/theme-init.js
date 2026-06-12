// Applies the stored/preferred light/dark mode before first paint to avoid a
// flash. External (not inline) so the page can ship a strict
// Content-Security-Policy without allowing inline scripts. The layout is
// always "government" — the only layout the site ships.
(() => {
  try {
    let mode = localStorage.getItem("alcohol-label-theme");
    // The old single-value scheme stored "government" as a theme; it is not a
    // light/dark value, so fall through to the OS preference.
    if (mode === "government") {
      mode = null;
    }
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme = mode === "dark" || mode === "light" ? mode : prefersDark ? "dark" : "light";
    document.documentElement.dataset.layout = "government";
  } catch {
    document.documentElement.dataset.theme = "light";
    document.documentElement.dataset.layout = "government";
  }
})();
