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

setInterval(updateAgents, 5000); // refresh every 5s
updateAgents(); // initial load