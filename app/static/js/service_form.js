const typeField = document.querySelector("#check_type");
const httpOnlyField = document.querySelector("[data-http-only]");
const statusField = document.querySelector("#expected_status_code");

function updateExpectedStatus() {
  const isHttp = typeField?.value === "http";
  if (httpOnlyField) httpOnlyField.hidden = !isHttp;
  if (statusField) statusField.disabled = !isHttp;
}

typeField?.addEventListener("change", updateExpectedStatus);
updateExpectedStatus();
