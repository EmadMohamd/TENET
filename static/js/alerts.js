async function updateAlerts() {
    try {
        const res = await fetch("/get_alerts");
        const alerts = await res.json();

        const tbody = document.getElementById("alertsBody");
        tbody.innerHTML = "";

        // Convert object entries to an array and sort by timestamp (newest first)
        const sortedAlerts = Object.entries(alerts).sort(([, a], [, b]) => {
            return new Date(b.timestamp) - new Date(a.timestamp);
        });

        sortedAlerts.forEach(([key, t]) => {
            const timestamp = t.timestamp;
            const log_id = t.log_id;
            const log_message = (t.log_message || "").toLowerCase();
            const role = t.role;
            const alert_level = (t.alert_level || "").toLowerCase();
            const task_id = t.task_id;
            const row = document.createElement("tr");

            if (
                alert_level.includes("alert") ||
                alert_level.includes("critical")
            ) {
                row.classList.add("task-alert");
            } else {
                row.classList.add("task-info");
            }

            row.innerHTML = `
                <td>${log_id}</td>
                <td>${log_message}</td>
                <td>${timestamp}</td>
                <td>${role}</td>
                <td>${alert_level}</td>
                <td>${task_id}</td>
            `;

            tbody.appendChild(row);
        });

    } catch (e) {
        console.error(e);
    }
}

// Initial load + auto refresh
updateAlerts();
setInterval(updateAlerts, 5000);