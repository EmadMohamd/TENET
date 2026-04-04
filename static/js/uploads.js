// ================= DELETE FILE =================
function deleteFile(filename, btn) {
    if (!confirm(`Delete "${filename}"?`)) return;

    fetch(`/uploads/${encodeURIComponent(filename)}`, {
        method: "DELETE",
        headers: {
            "Authorization": "Bearer " + window.API_KEY
        }
    })
    .then(res => res.json())
    .then(data => {
        if (data.message === "File deleted successfully") {
            // Remove the row from the table
            if (btn) btn.closest("tr").remove();

            // If table is now empty, show "no files" message
            const tbody = document.getElementById("filesBody");
            const emptyMsg = document.getElementById("noFilesMessage");
            if (!tbody.rows.length) emptyMsg.style.display = "block";
        } else {
            alert("Failed to delete file: " + (data.error || "Unknown error"));
        }
    })
    .catch(err => {
        console.error(err);
        alert("Network or server error");
    });
}

// ================= UPDATE FILE LIST =================
async function updateFiles() {
    try {
        const res = await fetch("/files-data"); // Backend endpoint returning JSON array of filenames
        const files = await res.json();

        const tbody = document.getElementById("filesBody");
        const emptyMsg = document.getElementById("noFilesMessage");

        tbody.innerHTML = "";

        if (!files.length) {
            emptyMsg.style.display = "block";
            return;
        } else {
            emptyMsg.style.display = "none";
        }

        files.forEach(filename => {
            const row = document.createElement("tr");

            row.innerHTML = `
                <td>
                    <a href="/uploads/${encodeURIComponent(filename)}" target="_blank">
                        ${filename}
                    </a>
                </td>
                <td>
                    <button class="btn btn-sm btn-delete"
                        onclick='deleteFile(${JSON.stringify(filename)}, this)'>
                        Delete
                    </button>
                </td>
            `;

            tbody.appendChild(row);
        });
    } catch (err) {
        console.error("Failed to fetch files:", err);
    }
}

// ================= AUTO-REFRESH =================
updateFiles();
setInterval(updateFiles, 5000); // refresh every 5 seconds