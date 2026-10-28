document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });
  document.querySelectorAll("[data-toggle-password]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = document.getElementById(button.dataset.togglePassword);
      if (!input) return;
      const showing = input.type === "text";
      input.type = showing ? "password" : "text";
      button.innerHTML = showing ? '<i class="bi bi-eye"></i>' : '<i class="bi bi-eye-slash"></i>';
      button.setAttribute("aria-label", showing ? "Show password" : "Hide password");
    });
  });
});
