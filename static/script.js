const analyzeForm = document.getElementById("analyzeForm");
const message = document.getElementById("message");
const trackerMessage = document.getElementById("trackerMessage");

let applicationChart = null;

function setMessage(element, text, isError = false) {
    element.textContent = text;
    element.className = isError ? "message error" : "message";
}

function renderSkills(elementId, skills, type = "") {
    const container = document.getElementById(elementId);
    container.replaceChildren();

    if (!skills || skills.length === 0) {
        const empty = document.createElement("span");
        empty.className = "result-note";
        empty.textContent = "No skills detected.";
        container.appendChild(empty);
        return;
    }

    skills.forEach(skill => {
        const tag = document.createElement("span");
        tag.className = `skill-tag ${type}`;
        tag.textContent = skill;
        container.appendChild(tag);
    });
}

function renderSuggestions(suggestions) {
    const container = document.getElementById("suggestions");
    container.replaceChildren();

    suggestions.forEach(suggestion => {
        const item = document.createElement("div");
        item.className = "suggestion-item";
        item.textContent = suggestion;
        container.appendChild(item);
    });
}


// RESUME ANALYSIS
analyzeForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const file = document.getElementById("resume").files[0];
    const jobDescription = document.getElementById("jobDescription").value.trim();
    const button = document.getElementById("analyzeButton");

    if (!file || !jobDescription) {
        setMessage(message, "Please upload a PDF and enter a job description.", true);
        return;
    }

    if (!file.name.toLowerCase().endsWith(".pdf")) {
        setMessage(message, "Please choose a PDF file.", true);
        return;
    }

    if (file.size > 5 * 1024 * 1024) {
        setMessage(message, "The PDF must be smaller than 5 MB.", true);
        return;
    }

    const formData = new FormData(analyzeForm);
    button.disabled = true;
    button.textContent = "Analyzing...";
    setMessage(message, "Analyzing your resume. Please wait.");

    try {
        const response = await fetch("/api/analyze", {
            method: "POST",
            body: formData
        });
        const data = await response.json();

        if (!response.ok) throw new Error(data.error || "Analysis failed.");

        document.getElementById("emptyState").hidden = true;
        document.getElementById("results").hidden = false;

        document.getElementById("score").textContent = `${data.match_score}%`;
        document.getElementById("similarity").textContent = `${data.text_similarity}%`;
        document.getElementById("coverage").textContent = `${data.skill_score}%`;

        renderSkills("matchedSkills", data.matched_skills);
        renderSkills("missingSkills", data.missing_skills, "missing");
        renderSkills("resumeSkills", data.resume_skills, "neutral");
        renderSuggestions(data.suggestions || []);

        setMessage(message, "Analysis completed and saved to your history.");
        await loadHistory();
    } catch (error) {
        setMessage(message, error.message, true);
    } finally {
        button.disabled = false;
        button.textContent = "Analyze Resume →";
    }
});


// APPLICATION TRACKER
async function loadApplications() {
    try {
        const response = await fetch("/api/applications");
        if (!response.ok) throw new Error("Could not load applications.");

        const applications = await response.json();
        const list = document.getElementById("applicationsList");
        list.replaceChildren();

        if (applications.length === 0) {
            const row = document.createElement("tr");
            const cell = document.createElement("td");
            cell.colSpan = 4;
            cell.textContent = "No applications yet.";
            row.appendChild(cell);
            list.appendChild(row);
        }

        applications.forEach(app => {
            const row = document.createElement("tr");

            const companyCell = document.createElement("td");
            companyCell.textContent = app.company;

            const roleCell = document.createElement("td");
            roleCell.textContent = app.role;

            const statusCell = document.createElement("td");
            const select = document.createElement("select");
            select.className = "status-select";

            ["Applied", "Interview", "Selected", "Rejected"].forEach(status => {
                const option = document.createElement("option");
                option.value = status;
                option.textContent = status;
                option.selected = app.status === status;
                select.appendChild(option);
            });

            select.addEventListener("change", () => updateStatus(app.id, select.value));
            statusCell.appendChild(select);

            const actionCell = document.createElement("td");
            const deleteButton = document.createElement("button");
            deleteButton.className = "delete-btn";
            deleteButton.type = "button";
            deleteButton.textContent = "Delete";
            deleteButton.addEventListener("click", () => deleteApplication(app.id));
            actionCell.appendChild(deleteButton);

            row.append(companyCell, roleCell, statusCell, actionCell);
            list.appendChild(row);
        });

        await loadStats();
    } catch (error) {
        console.error(error);
        setMessage(trackerMessage, error.message, true);
    }
}

document.getElementById("applicationForm").addEventListener("submit", async (event) => {
    event.preventDefault();

    const payload = {
        company: document.getElementById("company").value.trim(),
        role: document.getElementById("role").value.trim(),
        status: document.getElementById("status").value,
        job_url: document.getElementById("jobUrl").value.trim()
    };

    try {
        const response = await fetch("/api/applications", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Unable to add application.");

        event.target.reset();
        setMessage(trackerMessage, "Application added successfully.");
        await loadApplications();
    } catch (error) {
        setMessage(trackerMessage, error.message, true);
    }
});

async function updateStatus(id, status) {
    try {
        const response = await fetch(`/api/applications/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Unable to update status.");
        setMessage(trackerMessage, "Application status updated.");
        await loadApplications();
    } catch (error) {
        setMessage(trackerMessage, error.message, true);
        await loadApplications();
    }
}

async function deleteApplication(id) {
    if (!confirm("Delete this application?")) return;

    try {
        const response = await fetch(`/api/applications/${id}`, { method: "DELETE" });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Unable to delete application.");
        setMessage(trackerMessage, "Application deleted.");
        await loadApplications();
    } catch (error) {
        setMessage(trackerMessage, error.message, true);
    }
}


// DASHBOARD STATS AND CHART
async function loadStats() {
    const response = await fetch("/api/stats");
    if (!response.ok) throw new Error("Could not load dashboard statistics.");

    const stats = await response.json();
    document.getElementById("totalApps").textContent = stats.total;
    document.getElementById("interviews").textContent = stats.Interview;
    document.getElementById("selected").textContent = stats.Selected;
    document.getElementById("rejected").textContent = stats.Rejected;
    renderChart(stats);
}

function renderChart(stats) {
    const canvas = document.getElementById("applicationChart");
    if (applicationChart) applicationChart.destroy();

    applicationChart = new Chart(canvas, {
        type: "doughnut",
        data: {
            labels: ["Applied", "Interview", "Selected", "Rejected"],
            datasets: [{
                data: [stats.Applied, stats.Interview, stats.Selected, stats.Rejected],
                backgroundColor: ["#8b5cf6", "#3b82f6", "#34d399", "#fb7185"],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: "bottom",
                    labels: { color: "#cbd5e1", padding: 18 }
                }
            }
        }
    });
}


// ANALYSIS HISTORY
async function loadHistory() {
    try {
        const response = await fetch("/api/history");
        if (!response.ok) throw new Error("Unable to load analysis history.");

        const history = await response.json();
        const list = document.getElementById("historyList");
        list.replaceChildren();

        if (history.length === 0) {
            const row = document.createElement("tr");
            const cell = document.createElement("td");
            cell.colSpan = 4;
            cell.textContent = "No analysis history yet.";
            row.appendChild(cell);
            list.appendChild(row);
            return;
        }

        history.forEach(item => {
            const row = document.createElement("tr");
            const date = new Date(item.created_at).toLocaleString();

            [item.company, item.job_title, `${item.match_score}%`, date].forEach(value => {
                const cell = document.createElement("td");
                cell.textContent = value;
                row.appendChild(cell);
            });

            list.appendChild(row);
        });
    } catch (error) {
        console.error(error);
    }
}

document.getElementById("refreshHistory").addEventListener("click", loadHistory);


// INITIALIZE
loadApplications();
loadHistory();
