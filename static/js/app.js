
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("form").forEach(form => {
    form.addEventListener("submit", () => {
      const button = form.querySelector("button[type=submit], button:not([type])");
      if (button && !button.disabled) {
        button.disabled = true;
        setTimeout(() => { button.disabled = false; }, 5000);
      }
    });
  });
});
