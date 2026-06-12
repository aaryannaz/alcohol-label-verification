// Applies the stored/preferred layout + light/dark mode before first paint to
// avoid a flash. External (not inline) so the page can ship a strict
// Content-Security-Policy without allowing inline scripts.
(() => {
  try {
    let mode = localStorage.getItem("alcohol-label-theme");
    let layout = localStorage.getItem("alcohol-label-layout");
    // Migrate the old single-value scheme where "government" was a theme.
    if (mode === "government") {
      layout = "government";
      mode = null;
    }
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme = mode === "dark" || mode === "light" ? mode : prefersDark ? "dark" : "light";
    document.documentElement.dataset.layout = layout === "government" ? "government" : "standard";
  } catch {
    document.documentElement.dataset.theme = "light";
    document.documentElement.dataset.layout = "standard";
  }
})();
