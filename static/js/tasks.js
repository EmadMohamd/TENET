/* ================= DELETE TASK ================= */
function deleteTask(uuid, btn) {
    if (!confirm("Delete task?")) return;

    fetch(`/tasks/${uuid}`, {
        method: "DELETE",
        headers: {
            "Authorization": "Bearer " + window.API_KEY,
            "Content-Type": "application/json"
        }
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === "deleted") {
            if (btn) btn.closest("tr").remove();
        } else {
            alert("Failed to delete task: " + (data.error || "Unknown error"));
        }
    })
    .catch(err => {
        console.error(err);
        alert("Network or server error");
    });
}

/* ================= UPDATE TASKS ================= */
async function updateTasks() {
    try {
        const res = await fetch("/tasks-data");
        const tasks = await res.json();
        const tbody = document.getElementById("tasksBody");
        tbody.innerHTML = "";

        Object.entries(tasks).forEach(([uuid, t]) => {
            const task = t.task;
            const output = (t.output || "").toLowerCase();
            const row = document.createElement("tr");
            const executedAt = t.executed_at ? (() => {
                const date = new Date(t.executed_at.replace(" ", "T"));
                 return isNaN(date.getTime()) ? "—" : date.toLocaleString(); })(): "—";
            const scheduledAt = t.scheduled_at
            const recurringEvery = t.recurring_every
            // Apply row class based on output
            if (output.includes("error") || output.includes("failed") || output.includes("exception")) {
                row.classList.add("task-failed");
            } else if (t.output && output !== "pending" || t.executed_at) {
                row.classList.add("task-completed");
            } else {
                row.classList.add("task-pending");
            }

            row.innerHTML = `
                <td>${t.agent_id}</td>
                <td>${task.type}</td>
                <td>${task.command || task.url || task.path_to_file || ""}</td>
                <td>${t.output || "Pending"}</td>
                <td>${scheduledAt}</td>
                <td>${executedAt}</td>
                <td>${recurringEvery}</td>
                <td>${uuid}</td>
                <td><button class="btn btn-sm btn-delete" onclick="deleteTask('${uuid}', this)">Delete</button></td>
            `;
            tbody.appendChild(row);
        });

        // Re-apply filters after updating tasks
        applyFilters();
    } catch (e) {
        console.error(e);
    }
}

/* ================= FILTERS ================= */
const tableBody = document.getElementById("tasksBody");
const filters = ["filterAgent", "filterType", "filterStatus", "filterUUID"]
    .map(id => document.getElementById(id));

function applyFilters() {
    const agentFilter = filters[0].value.toLowerCase();
    const typeFilter = filters[1].value.toLowerCase();
    const statusFilter = filters[2].value.toLowerCase();
    const uuidFilter = filters[3].value.toLowerCase();

    for (let row of tableBody.rows) {
        const agentId = row.cells[0].innerText.toLowerCase();
        const type = row.cells[1].innerText.toLowerCase();
        const output = row.cells[3].innerText.toLowerCase();
        const uuid = row.cells[4].innerText.toLowerCase();

        let status = "pending";
        if (row.classList.contains("task-completed")) status = "completed";
        if (row.classList.contains("task-failed")) status = "failed";

        const statusMatch = (statusFilter === "" || status === statusFilter);
        const agentMatch = agentFilter === "" || agentId.includes(agentFilter);
        const typeMatch = typeFilter === "" || type === typeFilter;
        const uuidMatch = uuidFilter === "" || uuid.includes(uuidFilter);

        if (agentMatch && typeMatch && statusMatch && uuidMatch) {
            row.style.display = "";
        } else {
            row.style.display = "none";
        }
    }
}

// Attach event listeners to filters
filters.forEach(f => f.addEventListener("input", applyFilters));

// Initial load and auto-refresh
updateTasks();
setInterval(updateTasks, 2000);