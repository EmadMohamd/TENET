document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector("form");

    form.addEventListener("submit", async (event) => {
        event.preventDefault(); // Prevent page reload

        // Collect form data
        const formData = {
            username: form.username.value,
            password: form.password.value,
            confirm_password: form.confirm_password.value
        };

        try {
            const response = await fetch("/admin_register", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(formData)
            });

            const result = await response.json();

            if (response.ok) {
                alert("Admin registered successfully!");
                // Optionally redirect
                // window.location.href = "/login";
            } else {
                alert(result.error || "Registration failed.");
            }
        } catch (error) {
            console.error("Error:", error);
            alert("An error occurred while registering.");
        }
    });
});