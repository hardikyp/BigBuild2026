(function () {
  const root = document.documentElement;
  const storageKey = "morgan-theme";

  function savedTheme() {
    try {
      return window.localStorage.getItem(storageKey);
    } catch (error) {
      return null;
    }
  }

  function setTheme(theme) {
    const dark = theme === "dark";
    root.dataset.theme = dark ? "dark" : "light";
    const button = document.querySelector("[data-theme-toggle]");
    if (!button) return;
    button.textContent = dark ? "☀ Light" : "◐ Dark";
    button.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
  }

  setTheme(savedTheme() === "dark" ? "dark" : "light");
  const button = document.querySelector("[data-theme-toggle]");
  if (button) {
    button.addEventListener("click", function () {
      const theme = root.dataset.theme === "dark" ? "light" : "dark";
      setTheme(theme);
      try {
        window.localStorage.setItem(storageKey, theme);
      } catch (error) {
        // The toggle still works when browser storage is unavailable.
      }
    });
  }
})();
