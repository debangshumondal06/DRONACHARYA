const uploadForm = document.getElementById("uploadForm");
const datasetInput = document.getElementById("dataset");
const fileLabel = document.getElementById("fileLabel");
const uploadButton = document.getElementById("uploadButton");
const uploadStatus = document.getElementById("uploadStatus");

if (datasetInput && fileLabel) {
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
    uploadButton.textContent = "Analyzing dataset…";
    showStatus("Cleaning the data and preparing your analysis…", "info");

    try {
      const response = await fetch("/api/upload", {
        method: "POST",
        credentials: "same-origin",
        body: formData,
      });
      const result = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(result.error || "Upload failed.");
      }

      window.location.href = result.redirect_url;
    } catch (error) {
      showStatus(error.message, "error");
      uploadButton.disabled = false;
      uploadButton.textContent = "Analyze dataset";
    }
  });
}

function showStatus(message, type) {
  if (!uploadStatus) return;
  uploadStatus.textContent = message;
  uploadStatus.className = `status-message ${type}`;
}