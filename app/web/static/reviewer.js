// The secret reviewer link (https://<app>/#r=<token>): the token sits after the #, which browsers never send to
// the server. Read it once, clear it from the address straight away (so it stays out of the address bar, history
// and any screenshot), then post it once in a request body; the server turns it into a reviewer session.
(function () {
  "use strict";
  var match = /^#r=([A-Za-z0-9_-]{1,512})$/.exec(window.location.hash || "");
  if (!match) return;
  var token = match[1];
  try {
    history.replaceState(history.state, document.title, window.location.pathname + window.location.search);
  } catch (e) {
    window.location.hash = "";
  }
  fetch("/api/reviewer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ token: token })
  }).catch(function () { /* a failed or refused link leaves an ordinary visitor session */ });
})();
