// DEV ONLY. Stands in for pywebview when the page is served by `python -m desktop.devserver`:
// window.pywebview.api.<method>(...args) becomes POST /api/<method> with the arguments as a JSON list.
(function () {
  window.pywebview = {
    api: new Proxy({}, {
      get: (_, name) => (...args) =>
        fetch("/api/" + String(name), { method: "POST", body: JSON.stringify(args) }).then((r) => r.json()),
    }),
  };
  window.addEventListener("DOMContentLoaded", () => window.dispatchEvent(new Event("pywebviewready")));
})();
