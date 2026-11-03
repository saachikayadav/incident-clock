// Progressive enhancement only. Displayed times are rendered in UTC by the server and
// are not converted here, so every viewer sees the same value.

// Preselect the UTC offset the browser uses *at the chosen moment* (so DST is right).
// The user can still change it; without JS they must pick one before submitting.
function offsetFor(localValue) {
  const d = new Date(localValue);
  if (isNaN(d)) return "";
  const mins = -d.getTimezoneOffset();
  const sign = mins >= 0 ? "+" : "-";
  const abs = Math.abs(mins);
  const pad = (n) => String(n).padStart(2, "0");
  return `${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
}

document.querySelectorAll("input[data-offset-target]").forEach((input) => {
  const select = document.getElementById(input.dataset.offsetTarget);
  if (!select) return;
  let touched = select.value !== "";
  select.addEventListener("change", () => { touched = true; });
  const sync = () => {
    if (touched || !input.value) return;
    const offset = offsetFor(input.value);
    if ([...select.options].some((o) => o.value === offset)) select.value = offset;
  };
  input.addEventListener("change", sync);
  sync();
});

// Live character counter for fields with a limit. Counts code points like the API
// (Python len), so an emoji counts as one character, not two.
const fmt = (n) => n.toLocaleString("en-US");
document.querySelectorAll("[data-maxlength]").forEach((field) => {
  const counter = document.getElementById(`${field.id}-count`);
  if (!counter) return;
  const max = Number(field.dataset.maxlength);
  const update = () => {
    const used = [...field.value].length;
    const over = used - max;
    counter.textContent = `${fmt(used)} / ${fmt(max)}` + (over > 0 ? ` (${fmt(over)} over the limit)` : "");
    counter.classList.toggle("over", over > 0);
    counter.classList.toggle("near", over <= 0 && used >= max * 0.9);
  };
  field.addEventListener("input", update);
  update();
});
