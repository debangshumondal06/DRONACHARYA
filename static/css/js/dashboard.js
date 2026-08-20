const dashboardStatus = document.getElementById("dashboardStatus");

function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value ?? "—";
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function showDashboardStatus(message, type = "error") {
    dashboardStatus.textContent = message;
    dashboardStatus.className = `status-message ${type}`;
}

async function loadAnalysis() {
    if (!window.ANALYSIS_ID) {
        showDashboardStatus("No analysis was selected. Please upload a dataset first.");
        return;
    }

    try {
        const response = await fetch(`/api/analysis/${window.ANALYSIS_ID}`);
        const analysis = await response.json();
        if (!response.ok) throw new Error(analysis.error || "Could not load analysis.");
        renderAnalysis(analysis);
    } catch (error) {
        showDashboardStatus(error.message);
    }
}

function renderAnalysis(analysis) {
    const report = analysis.report;
    const prediction = analysis.prediction;

    setText("analysisTitle", analysis.filename);
    setText("analysisDate", `Created ${analysis.created_at} UTC`);
    setText("qualityScore", `${report.quality_score}/100`);
    setText("rowCountParameter", report.row_count);
    setText("columnCountParameter", report.column_count);
    setText("targetParameter", report.target_column || "Not found");
    setText("modelParameter", prediction.model_name || "Not available");
    const missingCells = Object.values(report.missing_values || {}).reduce((total, value) => total + Number(value || 0), 0);
    setText("missingParameter", missingCells);
    setText("duplicateParameter", report.duplicate_count || 0);
    setText("confidenceParameter", prediction.available ? `${prediction.confidence_score}/100` : "Unavailable");
    setText("trendParameter", prediction.trend || "Unknown");
    setText("qualityLabel", report.quality_score >= 75 ? "Good readiness" : report.quality_score >= 50 ? "Usable with caution" : "Needs attention");
    setText("rowCount", report.row_count);
    setText("columnCount", `${report.column_count} columns`);
    setText("targetColumn", report.target_column || "Not found");
    setText("modelName", prediction.model_name || "No model");
    setText("predictedValue", prediction.available ? prediction.predicted_value : "Unavailable");
    setText("confidenceLabel", `${prediction.confidence || "Low"} confidence`);
    setText("largePrediction", prediction.available ? prediction.predicted_value : "Unavailable");
    setText("trendText", prediction.available ? `Trend: ${prediction.trend}` : "No prediction available");
    setText("predictionNote", prediction.note || prediction.message || "No interpretation is available.");

    renderWarnings(report);
    renderPreview(report);
    renderFactors(prediction);
    renderRecommendations(analysis.recommendations || []);
    showDashboardStatus("Analysis completed successfully.", "success");
}

function renderWarnings(report) {
    const warnings = document.getElementById("warnings");
    const list = report.warnings || [];
    if (!list.length) {
        warnings.innerHTML = '<div class="clean-note">No major data-quality warnings were detected.</div>';
    } else {
        warnings.innerHTML = list.map(item => `<div class="warning-item">Warning: ${escapeHtml(item)}</div>`).join("");
    }
    document.getElementById("cleanMessage").textContent = `The dataset contains ${report.row_count} rows and ${report.column_count} columns. Review the warnings before using the prediction.`;
}

function renderPreview(report) {
    const head = document.getElementById("previewHead");
    const body = document.getElementById("previewBody");
    const columns = report.columns || [];
    head.innerHTML = `<tr>${columns.map(column => `<th>${escapeHtml(column)}</th>`).join("")}</tr>`;
    body.innerHTML = (report.preview || []).map(row => `<tr>${columns.map(column => `<td>${escapeHtml(row[column])}</td>`).join("")}</tr>`).join("");
}

function renderFactors(prediction) {
    const container = document.getElementById("factorList");
    const factors = prediction.top_factors || [];
    if (!factors.length) {
        container.innerHTML = '<p class="muted">No feature relationships could be calculated.</p>';
        return;
    }
    container.innerHTML = factors.map(factor => {
        const width = Math.max(8, Math.round(factor.importance * 100));
        return `<div class="factor-row"><div class="factor-meta"><strong>${escapeHtml(factor.name)}</strong><span>${escapeHtml(factor.direction)} · ${factor.importance}</span></div><div class="factor-track"><span style="width:${width}%"></span></div></div>`;
    }).join("");
}

function renderRecommendations(recommendations) {
    const container = document.getElementById("recommendationGrid");
    if (!recommendations.length) {
        container.innerHTML = '<p class="muted">Recommendations are unavailable because no valid prediction was produced.</p>';
        return;
    }
    container.innerHTML = recommendations.map((item, index) => `<article class="recommendation-card ${index === 2 ? "recommended-card" : ""}">
        <div class="recommendation-top"><span class="recommendation-type">${escapeHtml(item.type)}</span><span class="recommendation-index">0${index + 1}</span></div>
        <h3>${escapeHtml(item.title)}</h3>
        <p>${escapeHtml(item.description)}</p>
        <div class="recommendation-detail"><span>Expected outcome</span><strong>${escapeHtml(item.expected_outcome)}</strong></div>
        <div class="tag-row"><span class="tag">Risk: ${escapeHtml(item.risk_level)}</span><span class="tag">Resources: ${escapeHtml(item.resource_level)}</span><span class="tag">Confidence: ${escapeHtml(item.confidence)}</span></div>
        <div class="tradeoff"><strong>Trade-off:</strong> ${escapeHtml(item.tradeoff)}</div>
    </article>`).join("");
}

loadAnalysis();