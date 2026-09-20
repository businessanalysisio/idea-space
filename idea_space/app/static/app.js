document.body.addEventListener("dragstart", (event) => {
  const taskEl = event.target.closest("[data-task-id]");
  if (!taskEl) return;
  event.dataTransfer.setData("text/task-id", taskEl.dataset.taskId);
});

document.body.addEventListener("dragover", (event) => {
  if (event.target.closest(".calendar-day")) {
    event.preventDefault();
  }
});

document.body.addEventListener("drop", async (event) => {
  const dayEl = event.target.closest(".calendar-day");
  if (!dayEl) return;
  event.preventDefault();

  const taskId = event.dataTransfer.getData("text/task-id");
  if (!taskId) return;

  const contentEl = document.getElementById("calendar-content");
  if (!contentEl) return;

  const newDate = dayEl.dataset.date;
  const params = new URLSearchParams();
  params.set("due_date", newDate);
  params.set("view", contentEl.dataset.view || "month");
  if (contentEl.dataset.month) params.set("month", contentEl.dataset.month);
  if (contentEl.dataset.weekStart) params.set("start", contentEl.dataset.weekStart);

  const response = await fetch(`/tasks/${taskId}/reschedule`, {
    method: "PATCH",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: params.toString(),
  });

  if (response.ok) {
    const html = await response.text();
    contentEl.outerHTML = html;
  }
});
