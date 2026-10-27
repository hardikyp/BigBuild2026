// Shows previews of photos picked in a checklist item's evidence dropdown
// before the section is saved. Delegated on document so it keeps working
// after hx-boost swaps the page body.
document.addEventListener("change", (event) => {
  const input = event.target;
  if (!input.matches("[data-photo-input]")) return;
  const details = input.closest(".evidence-details");
  const previews = details.querySelector("[data-photo-previews]");
  previews.querySelectorAll("img").forEach((img) => URL.revokeObjectURL(img.src));
  previews.replaceChildren();
  const files = [...details.querySelectorAll("[data-photo-input]")].flatMap((el) => [...el.files]);
  previews.hidden = files.length === 0;
  for (const file of files) {
    const figure = document.createElement("figure");
    const img = document.createElement("img");
    img.src = URL.createObjectURL(file);
    img.alt = file.name;
    const caption = document.createElement("figcaption");
    caption.textContent = file.name;
    figure.append(img, caption);
    previews.append(figure);
  }
  if (files.length) {
    const note = document.createElement("p");
    note.className = "muted";
    note.textContent = `${files.length} photo${files.length === 1 ? "" : "s"} ready. Save this section to upload.`;
    previews.append(note);
  }
});
