// Applies the stored/preferred theme before first paint to avoid a flash.
// External (not inline) so the page can ship a strict Content-Security-Policy
// without allowing inline scripts.
(() => {
  try {
    const storedTheme = localStorage.getItem("alcohol-label-theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme = storedTheme || (prefersDark ? "dark" : "light");
  } catch {
    document.documentElement.dataset.theme = "light";
  }
})();
