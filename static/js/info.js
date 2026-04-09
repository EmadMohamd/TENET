async function updateMap() {
    const response = await fetch("/get_map");
    const html = await response.text();  // ✅ treat as text
    document.getElementById("map-container").innerHTML = html;
}

async function updateBarChart() {
    const response = await fetch("/get_bar_chart");
    const data = await response.json();

    const traces = [];
    for (const [agent_id, counts] of Object.entries(data.agents)) {
        traces.push({
            x: data.dates,
            y: Object.values(counts),
            name: `Agent ${agent_id}`,
            type: 'bar'
        });
    }

    const layout = {
        barmode: 'group',
        template: 'plotly_dark',
        plot_bgcolor: 'rgba(30,41,59,0.85)',
        paper_bgcolor: 'rgba(30,41,59,0.85)',
        font: {color: '#e5e7eb'},
        xaxis: {gridcolor: 'rgba(148,163,184,0.15)'},
        yaxis: {gridcolor: 'rgba(148,163,184,0.15)'}
    };

    // ✅ update the chart without flickering
    Plotly.react('barchart', traces, layout);
}

async function updatePieChart() {
    const response = await fetch("/get_pie_chart");
    const counts = await response.json();

    const data = [{
        values: [counts.online, counts.offline],
        labels: ["Online 🟢", "Offline 🔴"],
        type: 'pie',
        hole: 0.4,
        marker: {colors: ['#22c55e', '#ef4444']}
    }];

    const layout = {
        template: 'plotly_dark',
        plot_bgcolor: 'rgba(30,41,59,0.85)',
        paper_bgcolor: 'rgba(30,41,59,0.85)',
        font: {color: '#e5e7eb'},
        title: "Agent Status (last 30 seconds)"
    };

    Plotly.react('piechart', data, layout);
}

async function updatePieChartTasks() {
    const response = await fetch("/get_piechart_task_success_rate");
    const counts = await response.json();

    const dropdown = document.getElementById("agentDropdown");

    // Populate dropdown if empty
    if (dropdown.options.length === 0) {
        for (const agentId of Object.keys(counts.agents)) {
            const option = document.createElement("option");
            option.value = agentId;
            option.text = `Agent ${agentId}`;
            dropdown.add(option);
        }
    }

    // Get selected agent
    const selectedAgent = dropdown.value || Object.keys(counts.agents)[0];
    const agentCounts = counts.agents[selectedAgent] || {};

    // Default to 0 if a status is missing
    const success = agentCounts.success || 0;
    const failure = agentCounts.failure || 0;
    const pending = agentCounts.pending || 0;

    const data = [{
        values: [success, failure, pending],
        labels: ["Successful 🟢", "Failed 🔴", "Pending 🟡"],
        type: 'pie',
        hole: 0.4,
        marker: {colors: ['#22c55e', '#ef4444', '#FFEA00']}
    }];

    const layout = {
        template: 'plotly_dark',
        plot_bgcolor: 'rgba(30,41,59,0.85)',
        paper_bgcolor: 'rgba(30,41,59,0.85)',
        font: {color: '#e5e7eb'},
        title: `Task Success Rate - Agent ${selectedAgent}`
    };

    Plotly.react('piechart_tasks', data, layout);
}

// Update pie chart when dropdown changes
document.getElementById("agentDropdown").addEventListener("change", updatePieChartTasks);
updatePieChartTasks();

// Initial render
updateBarChart();
updatePieChart();
updatePieChartTasks
setInterval(() => {
    updateBarChart();
    updatePieChart();
    updatePieChartTasks
}, 10000);
