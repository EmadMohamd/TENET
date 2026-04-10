
// ================= PREVIEW FILE =================
function previewFile(filename) {
    const url = `/uploads/${encodeURIComponent(filename)}`;

    const win = window.open(url, "_blank");

    // fallback if popup blocked
    if (!win) {
        window.location.href = url;
    }
}


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

            // remove row
            const row = btn.closest("tr");
            if (row) row.remove();

            // show empty message if needed
            const tbody = document.getElementById("filesBody");
            const emptyMsg = document.getElementById("noFilesMessage");

            if (!tbody.rows.length) {
                emptyMsg.style.display = "block";
            }

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
        const res = await fetch("/files-data");
        const files = await res.json();

        const tbody = document.getElementById("filesBody");
        const emptyMsg = document.getElementById("noFilesMessage");

        tbody.innerHTML = "";

        if (!files.length) {
            emptyMsg.style.display = "block";
            return;
        }

        emptyMsg.style.display = "none";

        files.forEach(filename => {
            const row = document.createElement("tr");

            // ===== filename cell (click to preview) =====
            const nameTd = document.createElement("td");

            const link = document.createElement("a");
            link.href = "#";
            link.className = "file-link";
            link.textContent = filename;

            link.addEventListener("click", (e) => {
                e.preventDefault();
                previewFile(filename);
            });

            nameTd.appendChild(link);

            // ===== actions cell =====
            const actionTd = document.createElement("td");

            const btn = document.createElement("button");
            btn.className = "btn btn-sm btn-delete";
            btn.textContent = "Delete";

            btn.addEventListener("click", () => {
                deleteFile(filename, btn);
            });

            actionTd.appendChild(btn);

            // ===== append row =====
            row.appendChild(nameTd);
            row.appendChild(actionTd);

            tbody.appendChild(row);
        });

    } catch (err) {
        console.error("Failed to fetch files:", err);
    }
}


// ================= AUTO REFRESH =================
updateFiles();
setInterval(updateFiles, 5000);