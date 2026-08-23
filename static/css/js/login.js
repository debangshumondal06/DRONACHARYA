const loginForm = document.getElementById("loginForm");
const loginButton = document.getElementById("loginButton");
const loginStatus = document.getElementById("loginStatus");
const aadhaarInput = document.getElementById("aadhaar_number");
const phoneInput = document.getElementById("phone_number");

function showLoginStatus(message, type = "error") {
  if (!loginStatus) return;
  loginStatus.textContent = message;
  loginStatus.className = `status-message ${type}`;
}

function digitsOnly(value) {
  return String(value || "").replace(/\D/g, "");
}

if (aadhaarInput) {
  aadhaarInput.addEventListener("input", () => {
    const digits = digitsOnly(aadhaarInput.value).slice(0, 12);
    aadhaarInput.value = digits.replace(/(\d{4})(?=\d)/g, "$1 ").trim();
  });
}

if (phoneInput) {
  phoneInput.addEventListener("input", () => {
    let digits = digitsOnly(phoneInput.value);
    if (digits.startsWith("91") && digits.length > 10) {
      digits = digits.slice(2);
    }
    digits = digits.slice(0, 10);
    phoneInput.value =
      digits.length > 5
        ? `+91 ${digits.slice(0, 5)} ${digits.slice(5)}`
        : digits;
  });
}

if (loginForm) {
  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const aadhaarDigits = digitsOnly(aadhaarInput.value);
    const phoneDigits = digitsOnly(phoneInput.value).replace(
      /^91(?=\d{10}$)/,
      "",
    );
    const consent = document.getElementById("prototypeConsent").checked;

    if (aadhaarDigits.length !== 12) {
      showLoginStatus("Please enter exactly 12 Aadhaar digits.");
      return;
    }

    if (phoneDigits.length !== 10) {
      showLoginStatus("Please enter a valid 10-digit Indian mobile number.");
      return;
    }

    if (!consent) {
      showLoginStatus(
        "Please accept the development-prototype notice before continuing.",
      );
      return;
    }

    const formData = new FormData();
    formData.append("aadhaar_number", aadhaarDigits);
    formData.append("phone_number", phoneDigits);
    formData.append(
      "email_id",
      document.getElementById("email_id").value.trim(),
    );
    formData.append("prototype_consent", "true");

    loginButton.disabled = true;
    loginButton.textContent = "Opening workspace…";
    showLoginStatus("Validating your workspace details…", "success");

    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        credentials: "same-origin",
        body: formData,
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || "Login failed.");
      }
      window.location.href = result.redirect_url;
    } catch (error) {
      showLoginStatus(error.message);
      loginButton.disabled = false;
      loginButton.textContent = "Enter workspace";
    }
  });
}
