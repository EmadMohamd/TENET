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

// Initial render
updateBarChart();
updatePieChart();
setInterval(() => {
    updateBarChart();
    updatePieChart();
}, 10000);
