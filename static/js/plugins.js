function previewPlugin(pluginName) {
    const url = `/plugins/${encodeURIComponent(pluginName)}`;

    fetch(url, {
        headers: {
            "Authorization": "Bearer " + window.API_KEY
        }
    })
    .then(res => {
        if (!res.ok) throw new Error("Failed to load plugin");
        return res.text();
    })
    .then(content => {
        showPreviewModal(pluginName, content);
    })
    .catch(err => {
        console.error(err);
        alert("Failed to preview plugin");
    });
}

function showPreviewModal(name, content) {
    document.getElementById("pluginPreviewTitle").innerText = name;
    document.getElementById("pluginPreviewContent").innerText = content;

    const modal = new bootstrap.Modal(
        document.getElementById("pluginPreviewModal")
    );
    modal.show();
}