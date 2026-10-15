// Report a scenario's outcome: show it in #result and log it on the server.
function report(task, data, text) {
  const el = document.getElementById("result");
  if (el) el.textContent = text || JSON.stringify(data, null, 1);
  fetch("/api/result", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({task: task, data: data})}).catch(() => {});
}
