// The chat page: each tab keeps its own conversation id (sessionStorage survives a reload of that tab only).
// A message is sent as an ordinary request, then its checked sentences arrive on a server-sent-event stream.
(function () {
  "use strict";
  var log = document.getElementById("log");
  var form = document.getElementById("send");
  var box = document.getElementById("message");
  var sendButton = form.querySelector("button[type=submit]");

  function newId() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID().replace(/-/g, "");
    return Date.now().toString(36) + Math.random().toString(36).slice(2);
  }

  function conversationId() {
    var id = null;
    try { id = sessionStorage.getItem("meridian-conversation"); } catch (e) { /* storage blocked */ }
    if (!id) {
      id = newId();
      try { sessionStorage.setItem("meridian-conversation", id); } catch (e) { /* storage blocked */ }
    }
    return id;
  }

  var conversation = conversationId();

  function add(kind, text) {
    var item = document.createElement("div");
    item.className = kind === "proof" || kind === "step" ? kind : "bubble " + kind;
    item.textContent = text;
    log.appendChild(item);
    item.scrollIntoView({ block: "end" });
    return item;
  }

  function busy(on) {
    sendButton.disabled = on;
  }

  function listen(messageId) {
    // The stream replays every saved sentence on a reconnect, so count what is already shown.
    var shown = 0, seen = 0;
    var source = new EventSource("/api/stream/" + encodeURIComponent(messageId));
    source.addEventListener("sentence", function (event) {
      seen += 1;
      if (seen > shown) { add("agent", JSON.parse(event.data).text); shown = seen; }
    });
    source.addEventListener("done", function (event) {
      source.close();
      var done = JSON.parse(event.data);
      if (done.proof) add("proof", done.proof);
      busy(false);
    });
    source.addEventListener("open", function () { seen = 0; });
    source.onerror = function () {
      if (source.readyState === EventSource.CLOSED) { add("agent", "The connection dropped. Please send your message again."); busy(false); }
    };
  }

  function send(text) {
    var messageId = newId();
    add("caller", text);
    busy(true);
    fetch("/api/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ conversation_id: conversation, message_id: messageId, text: text })
    }).then(function (response) {
      if (response.status === 404) {
        add("agent", "I can't open that conversation. Please start a new one.");
        try { sessionStorage.removeItem("meridian-conversation"); } catch (e) { /* storage blocked */ }
        conversation = conversationId();
        busy(false);
        return;
      }
      if (!response.ok) throw new Error("status " + response.status);
      listen(messageId);
    }).catch(function () {
      add("agent", "I couldn't send that just now. Please try again.");
      busy(false);
    });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var text = box.value;
    box.value = "";
    send(text);
  });

  box.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); form.requestSubmit(); }
  });

  // Suggested questions: fill the text box only.
  document.querySelectorAll(".suggestion").forEach(function (button) {
    button.addEventListener("click", function () {
      box.value = button.dataset.question;
      box.focus();
    });
  });
  // End of suggested questions.

  // A reload of this tab shows its conversation so far and any booking step in progress.
  fetch("/api/conversation/" + encodeURIComponent(conversation), { credentials: "same-origin" })
    .then(function (response) { return response.ok ? response.json() : null; })
    .then(function (saved) {
      if (!saved) return;
      saved.messages.forEach(function (message) { add(message.role, message.text); });
      if (saved.step_label) add("step", saved.step_label);
    })
    .catch(function () { /* a new conversation has no history */ });
})();
