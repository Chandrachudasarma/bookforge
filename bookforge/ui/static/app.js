/* BookForge UI — vanilla JavaScript, no framework */

const API = "/api/v1";
let pollInterval = null;

// Rewrite slider label — update on both input and change events
const rewriteSlider = document.getElementById("rewrite_percent");
const rewriteLabel = document.getElementById("rewrite_value");
if (rewriteSlider && rewriteLabel) {
    const updateLabel = () => { rewriteLabel.textContent = rewriteSlider.value + "%"; };
    rewriteSlider.addEventListener("input", updateLabel);
    rewriteSlider.addEventListener("change", updateLabel);
    updateLabel(); // sync on page load
}

// ---------------------------------------------------------------------------
// Upload form
// ---------------------------------------------------------------------------

document.getElementById("upload-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("submit-btn");
    const statusEl = document.getElementById("upload-status");

    btn.disabled = true;
    btn.textContent = "Uploading...";
    statusEl.hidden = true;

    try {
        const formData = new FormData();

        // Files
        const fileInput = document.getElementById("files");
        for (const file of fileInput.files) {
            formData.append("files", file);
        }

        if (fileInput.files.length === 0) {
            showStatus("Please select at least one file.", "error");
            return;
        }

        // Metadata as JSON
        const metadata = JSON.stringify({
            title: document.getElementById("title").value,
            author: document.getElementById("author").value,
        });
        formData.append("metadata", metadata);

        // Config as JSON
        const formatSelect = document.getElementById("output_formats");
        const formats = Array.from(formatSelect.selectedOptions).map(o => o.value);
        const config = JSON.stringify({
            template: document.getElementById("template").value,
            rewrite_percent: parseInt(document.getElementById("rewrite_percent").value) || 0,
            output_formats: formats,
            generate_preface: document.getElementById("gen_preface").checked,
            generate_acknowledgement: document.getElementById("gen_ack").checked,
        });
        formData.append("config", config);

        const resp = await fetch(`${API}/jobs`, { method: "POST", body: formData });

        if (resp.status === 401) {
            showStatus("Demo access required. Contact the administrator for credentials.", "error");
            return;
        }
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || "Upload failed");
        }

        const data = await resp.json();
        showStatus(`Job created: ${data.job_id}`, "success");

        // Reset form
        document.getElementById("upload-form").reset();

        // Refresh jobs list
        loadJobs();

    } catch (err) {
        showStatus(err.message, "error");
    } finally {
        btn.disabled = false;
        btn.textContent = "Start Job";
    }
});

function showStatus(msg, type) {
    const el = document.getElementById("upload-status");
    el.textContent = msg;
    el.className = `status-msg ${type}`;
    el.hidden = false;
}

// ---------------------------------------------------------------------------
// Jobs list
// ---------------------------------------------------------------------------

async function loadJobs() {
    try {
        const resp = await fetch(`${API}/jobs`);
        if (!resp.ok) return;

        const data = await resp.json();
        const container = document.getElementById("jobs-list");

        if (data.jobs.length === 0) {
            container.innerHTML = '<p class="empty">No jobs yet.</p>';
            return;
        }

        container.innerHTML = data.jobs.map(job => {
            const statusClass = `status-${job.status}`;
            const progress = job.total_files > 0
                ? `${job.succeeded + job.failed}/${job.total_files}`
                : "";

            return `
                <div class="job-item" data-job-id="${job.job_id}">
                    <div class="job-info">
                        <div class="job-title">${escapeHtml(job.title || "Untitled")}</div>
                        <div class="job-meta">
                            <span class="job-id">${job.job_id}</span>
                            ${progress ? ` &middot; ${progress} files` : ""}
                            ${job.created_at ? ` &middot; ${formatTime(job.created_at)}` : ""}
                        </div>
                    </div>
                    <div>
                        <span class="job-status ${statusClass}">${job.status}</span>
                    </div>
                    <div class="job-actions">
                        ${job.status === "completed" || job.status === "partially_failed"
                            ? `<span class="job-downloads" id="dl-${job.job_id}"><a href="#" onclick="loadDownloadLinks('${job.job_id}'); return false;">Download</a></span>`
                            : ""}
                        ${job.status === "failed"
                            ? `<a href="#" onclick="showError('${job.job_id}'); return false;">Details</a>`
                            : ""}
                    </div>
                </div>
            `;
        }).join("");

        // If any job is processing, start polling
        const hasActive = data.jobs.some(j =>
            j.status === "queued" || j.status === "processing"
        );
        if (hasActive && !pollInterval) {
            pollInterval = setInterval(loadJobs, 2000);
        } else if (!hasActive && pollInterval) {
            clearInterval(pollInterval);
            pollInterval = null;
        }

    } catch (err) {
        console.error("Failed to load jobs:", err);
    }
}

async function loadDownloadLinks(jobId) {
    try {
        const resp = await fetch(`${API}/jobs/${jobId}`);
        if (!resp.ok) return;

        const job = await resp.json();
        const outputs = [];
        for (const result of job.file_results) {
            for (const path of result.output_paths) {
                outputs.push(path.split("/").pop());
            }
        }

        const container = document.getElementById(`dl-${jobId}`);
        if (!container) return;

        if (outputs.length === 0) {
            container.textContent = "No files";
            return;
        }

        container.innerHTML = outputs.map(f =>
            `<a href="${API}/jobs/${jobId}/download/${f}" download>${f}</a>`
        ).join(" ");

    } catch (err) {
        console.error("Failed to get downloads:", err);
    }
}

async function showError(jobId) {
    try {
        const resp = await fetch(`${API}/jobs/${jobId}`);
        if (!resp.ok) return;
        const job = await resp.json();
        const errors = job.file_results
            .filter(r => r.status === "failed" && r.error)
            .map(r => r.error);
        alert(errors.length ? errors.join("\n\n") : "Unknown error");
    } catch (err) {
        alert("Could not fetch error details");
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function formatTime(iso) {
    try {
        const d = new Date(iso);
        return d.toLocaleString();
    } catch {
        return iso;
    }
}

// Initial load
loadJobs();
