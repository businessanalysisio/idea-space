document.body.addEventListener("dragstart", (event) => {
  const taskEl = event.target.closest("li[data-task-id]");
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

  const newDate = dayEl.dataset.date;
  const response = await fetch(`/tasks/${taskId}/reschedule`, {
    method: "PATCH",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: `due_date=${encodeURIComponent(newDate)}`,
  });

  if (response.ok) {
    const html = await response.text();
    document.querySelector("main").innerHTML = html;
  }
});
