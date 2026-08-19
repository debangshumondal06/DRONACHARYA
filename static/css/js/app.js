const uploadForm = document.getElementById("uploadForm");
const datasetInput = document.getElementById("dataset");
const fileLabel = document.getElementById("fileLabel");
const uploadButton = document.getElementById("uploadButton");
const uploadStatus = document.getElementById("uploadStatus");

if (datasetInput) {
    datasetInput.addEventListener("change", () => {
        const file = datasetInput.files[0];
        fileLabel.textContent = file ? file.name : "Choose a CSV file";
    });
}

if (uploadForm) {
    uploadForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const file = datasetInput.files[0];
        if (!file) {
            showStatus("Please choose a CSV file first.", "error");
            return;
        }

        const formData = new FormData(uploadForm);
        uploadButton.disabled = true;
        uploadButton.innerHTML = "Analyzing dataset <span>...</span>";
        showStatus("Cleaning the data and preparing your analysis...", "info");

        try {
            const response = await fetch("/api/upload", {
                method: "POST",
                body: formData,
            });
            const result = await response.json();
            if (!response.ok) {
                throw new Error(result.error || "Upload failed.");
            }
            window.location.href = result.redirect_url;
        } catch (error) {
            showStatus(error.message, "error");
            uploadButton.disabled = false;
            uploadButton.innerHTML = "Analyze dataset <span>→</span>";
        }
    });
}

function showStatus(message, type) {
    uploadStatus.textContent = message;
    uploadStatus.className = `status-message ${type}`;
}
