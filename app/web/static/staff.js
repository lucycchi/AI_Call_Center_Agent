// The Staff view panel beside the chat (R70 to R72). Everything shown comes from /api/staff/panel and
// /api/staff/queue, already masked by the server; it is written with textContent only, never as HTML.
(function () {
  "use strict";
  var button = document.getElementById("staff-button");
  var badge = document.getElementById("staff-badge");
  var panel = document.getElementById("staff-panel");
  var main = document.querySelector("main");
  var formToken = null, staff = false, lastShown = "";

  function seen(value) {
    try {
      if (value === undefined) return parseInt(localStorage.getItem("meridian-staff-seen") || "0", 10) || 0;
      localStorage.setItem("meridian-staff-seen", String(value));
    } catch (e) { /* storage blocked */ }
    return 0;
  }

  function conversation() {
    try { return sessionStorage.getItem("meridian-conversation"); } catch (e) { return null; }
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function field(parent, name, value) {
    var line = el("span", "field");
    line.appendChild(el("b", null, name + ": "));
    line.appendChild(document.createTextNode(value || "none"));
    parent.appendChild(line);
  }

  function ticketItem(ticket) {
    var item = el("li");
    var head = el("div");
    head.appendChild(el("strong", null, "Ticket #" + ticket.ticket_id + " "));
    head.appendChild(el("span", "priority " + ticket.priority_label, ticket.priority_label));
    head.appendChild(document.createTextNode(" " + ticket.tags.join(", ") + " · " + ticket.status));
    item.appendChild(head);
    field(item, "Who", ticket.who);
    field(item, "Wants", ticket.wants);
    field(item, "Tried", ticket.tried);
    field(item, "Constraints", ticket.constraints);
    field(item, "Mood", ticket.mood);
    if (ticket.conversation && ticket.conversation.length) {
      var whole = el("details", "conversation");
      whole.appendChild(el("summary", null, "Whole conversation (" + ticket.conversation.length + " messages)"));
      ticket.conversation.forEach(function (m) {
        field(whole, m.role === "caller" ? "Caller" : "Agent", m.text);
      });
      item.appendChild(whole);
    }
    return item;
  }

  function receiptBlock(receipt) {
    var details = el("details", "receipt");
    details.appendChild(el("summary", null, "How this reply was made: " + receipt.label));
    var list = el("dl");
    [["Safety decision", receipt.safety], ["Route", receipt.route],
     ["Sources", receipt.passages.join("; ") || "none"],
     ["Excluded as stale", receipt.excluded.join("; ") || "none"],
     ["Database action", receipt.db_action],
     ["Handoff reason", receipt.handoff_reason ? receipt.handoff_reason + (receipt.ticket ? " (ticket #" + receipt.ticket + ")" : "") : "none"]
    ].forEach(function (pair) { list.appendChild(el("dt", null, pair[0])); list.appendChild(el("dd", null, pair[1])); });
    details.appendChild(list);
    return details;
  }

  function flagForm(messageId) {
    var form = el("form");
    var note = el("textarea");
    note.rows = 1; note.maxLength = 2000; note.placeholder = "Correction note"; note.setAttribute("aria-label", "Correction note");
    var send = el("button", "small", "Flag as wrong");
    send.type = "submit";
    form.appendChild(note); form.appendChild(send);
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      fetch("/api/staff/flag", {
        method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message_id: messageId, correction: note.value, token: formToken })
      }).then(function (response) {
        form.replaceWith(el("span", "staff-message", response.ok ? "Flagged with your note." : "Could not flag this reply."));
      });
    });
    return form;
  }

  function render(data) {
    var numbers = document.getElementById("staff-numbers");
    numbers.textContent = "";
    var n = data.numbers;
    var containment = n.live_containment === null ? n.live_containment_label
      : Math.round(n.live_containment * 100) + "% (" + n.live_containment_label + ")";
    [["Conversations", n.conversations], ["Handoffs", n.handoffs], ["Errors", n.errors],
     ["Median reply", n.median_reply_ms === null ? "none yet" : (n.median_reply_ms / 1000).toFixed(1) + " s"],
     ["Live containment", containment]].concat(n.nightly_reset ? [["Nightly reset", n.nightly_reset]] : [])
    .forEach(function (pair) {
      var box = el("div", pair[0] === "Live containment" ? "wide" : null); box.appendChild(el("dt", null, pair[0])); box.appendChild(el("dd", null, String(pair[1])));
      numbers.appendChild(box);
    });
    var tickets = document.getElementById("staff-tickets");
    tickets.textContent = "";
    if (!data.tickets.length) tickets.appendChild(el("li", "staff-message", "No tickets in your conversations yet."));
    data.tickets.slice().reverse().forEach(function (ticket) { tickets.appendChild(ticketItem(ticket)); });
    var done = document.getElementById("staff-actions");
    done.textContent = "";
    var actions = data.actions || [];
    if (!actions.length) done.appendChild(el("li", "staff-message", "No payment links or membership changes."));
    actions.forEach(function (action) {
      var item = el("li");
      item.appendChild(el("strong", null, action.kind + " "));
      item.appendChild(document.createTextNode(action.customer_id + " · " + action.detail));
      if (action.sent_to) field(item, "Sent to", action.sent_to);
      if (action.expires_at) field(item, "Link valid until", action.expires_at);
      done.appendChild(item);
    });
    var replies = document.getElementById("staff-replies");
    replies.textContent = "";
    if (!data.replies.length) replies.appendChild(el("li", "staff-message", "No replies yet."));
    data.replies.forEach(function (reply) {
      var item = el("li", null, reply.text || "(no text)");
      if (reply.receipt) item.appendChild(receiptBlock(reply.receipt));
      if (staff) item.appendChild(flagForm(reply.message_id));
      replies.appendChild(item);
    });
  }

  function loadQueue() {
    fetch("/api/staff/queue", { credentials: "same-origin" })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (data) {
        var queue = document.getElementById("staff-queue");
        queue.textContent = "";
        if (!data) return;
        document.getElementById("staff-login").hidden = true;
        document.getElementById("staff-login-message").textContent = "Signed in. Every visitor's tickets, newest first:";
        data.tickets.forEach(function (ticket) { queue.appendChild(ticketItem(ticket)); });
      });
  }

  function fetchPanel(withConversation) {
    var id = withConversation ? conversation() : null;
    var url = "/api/staff/panel?seen=" + seen() + (id ? "&conversation_id=" + encodeURIComponent(id) : "");
    return fetch(url, { credentials: "same-origin" }).then(function (response) {
      if (response.status === 404 && id) return fetchPanel(false);  // a new conversation has no replies yet
      return response.ok ? response.json() : null;
    });
  }

  function refresh() {
    var open = !panel.hidden;
    fetchPanel(open).then(function (data) {
      if (!data) return;
      formToken = data.form_token; staff = data.staff;
      if (open) {
        seen(data.latest_ticket_id);
        badge.hidden = true;
        var shown = JSON.stringify(data);
        if (shown !== lastShown) { lastShown = shown; render(data); if (staff) loadQueue(); }
      } else {
        badge.textContent = String(data.new_tickets);
        badge.hidden = data.new_tickets === 0;
      }
    }).catch(function () { /* try again on the next poll */ });
  }

  button.addEventListener("click", function () {
    panel.hidden = !panel.hidden;
    button.setAttribute("aria-expanded", String(!panel.hidden));
    main.classList.toggle("staff-open", !panel.hidden);
    lastShown = "";
    refresh();
    // On a narrow screen the panel sits below the conversation: bring it into view.
    if (!panel.hidden && window.innerWidth < 820) panel.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  document.getElementById("staff-login").addEventListener("submit", function (event) {
    event.preventDefault();
    var box = document.getElementById("staff-password");
    var message = document.getElementById("staff-login-message");
    fetch("/api/staff/login", {
      method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: box.value })
    }).then(function (response) {
      box.value = "";
      if (response.status === 429) message.textContent = "Too many attempts. Try again in 15 minutes.";
      else if (!response.ok) message.textContent = "That password is not right.";
      else { lastShown = ""; refresh(); }
    });
  });

  refresh();
  // Poll every 8 seconds only while the panel is open; while it is closed, refresh the badge once a minute.
  setInterval(function () { if (!document.hidden && !panel.hidden) refresh(); }, 8000);
  setInterval(function () { if (!document.hidden && panel.hidden) refresh(); }, 60000);
})();
