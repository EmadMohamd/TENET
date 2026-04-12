async function updateAgents() {
    try {
        const res = await fetch("/agents-data");
        const agents = await res.json();

        const tbody = document.querySelector("table tbody");
        tbody.innerHTML = "";

        // ✅ Sort: online first, then by last_seen (most recent first)
        agents.sort((a, b) => {
            // Step 1: online priority
            if (a.online !== b.online) {
                return b.online - a.online;
            }

            // Step 2: last_seen (descending)
            const timeA = a.last_seen || 0;
            const timeB = b.last_seen || 0;
            return timeB - timeA;
        });

        agents.forEach(agent => {
            const status = agent.online ? "Online" : "Offline";
            const badgeClass = agent.online ? "badge-online" : "badge-offline";
            console.log("pending_tasks:", agent.pending_tasks);
            // Convert last_seen to "X seconds ago"
            let lastSeenText = "—";
            if (agent.last_seen) {
                const seconds = Math.floor(Date.now() / 1000 - agent.last_seen);
                lastSeenText = `${seconds}s ago`;
            }

            const row = document.createElement("tr");

            row.innerHTML = `
                <td>
                    <span class="badge ${badgeClass}">${status}</span>
                </td>

                <td>
                    <a href="/agents/${agent.id}" class="text-primary">
                        ${agent.id}
                    </a>
                </td>

                <td>${agent.hostname || ""}</td>
                <td>${agent.user || ""}</td>
                <td>${agent.os || ""}</td>
                <td>${agent.ip || ""}</td>
                <td>${lastSeenText}</td>
                <td>${agent.pending_tasks ?? 0}</td>
            `;

            tbody.appendChild(row);
        });

    } catch (e) {
        console.error(e);
    }
}

/* ================= AGENT FILTERS ================= */
const agentsTableBody = document.querySelector("table tbody");

const agentFilters = [
    document.getElementById("filterAgentID"),
    document.getElementById("filterUser"),
    document.getElementById("filterOS"),
    document.getElementById("filterAgentStatus")
];

function applyAgentFilters() {
    const agentIdFilter = agentFilters[0].value.toLowerCase();
    const userFilter = agentFilters[1].value.toLowerCase();
    const osFilter = agentFilters[2].value.toLowerCase();
    const statusFilter = agentFilters[3].value.toLowerCase();

    for (let row of agentsTableBody.rows) {
        const agentId = row.cells[1].innerText.toLowerCase();
        const user = row.cells[3].innerText.toLowerCase();
        const os = row.cells[4].innerText.toLowerCase();
        const status = row.dataset.status;

        const agentMatch = agentIdFilter === "" || agentId.includes(agentIdFilter);
        const userMatch = userFilter === "" || user.includes(userFilter);
        const osMatch = osFilter === "" || os.includes(osFilter);
        const statusMatch = statusFilter === "" || status === statusFilter;

        if (agentMatch && userMatch && osMatch && statusMatch) {
            row.style.display = "";
        } else {
            row.style.display = "none";
        }
    }
}


// live filtering
agentFilters.forEach(input => {
    input.addEventListener("input", applyAgentFilters);
    input.addEventListener("change", applyAgentFilters);
});


setInterval(updateAgents, 3000); // refresh every 5s
updateAgents(); // initial load