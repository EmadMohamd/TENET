async function updateAlerts() {
    try {
        const res = await fetch("/get_alerts");
        const alerts = await res.json();

        const tbody = document.getElementById("alertsBody");
        tbody.innerHTML = "";

        Object.entries(alerts).forEach(([key, t]) => {
            const timestamp = t.timestamp
            const log_id = t.log_id;
            const log_message = (t.log_message || "").toLowerCase();
            const role = t.role;
            const alert_level = (t.alert_level || "").toLowerCase();

            const row = document.createElement("tr");


            if (
                alert_level.includes("alert") ||
                alert_level.includes("critical")
            ) {
                row.classList.add("task-alert");
            } else {
                row.classList.add("task-info");
            }
            console.log(alert_level);



            row.innerHTML = `
                <td>${log_id}</td>
                <td>${log_message}</td>
                <td>${timestamp}</td>
                <td>${role}</td>
                <td>${alert_level}</td>
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