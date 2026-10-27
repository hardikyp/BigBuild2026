// Opens evidence photos in a large overlay. Any <a data-lightbox="group" href="image">
// works; links sharing a group value can be stepped through with the arrows.
// Without JavaScript the link still opens the image on its own.
(() => {
  let dialog, image, caption, counter, links = [], index = 0;

  function build() {
    dialog = document.createElement("dialog");
    dialog.className = "lightbox";
    dialog.setAttribute("aria-label", "Evidence photo");
    dialog.innerHTML = `
      <button type="button" class="lightbox-close" aria-label="Close">&times;</button>
      <button type="button" class="lightbox-nav prev" aria-label="Previous photo">&#8249;</button>
      <figure><img alt=""><figcaption><span class="lightbox-caption"></span><span class="lightbox-counter"></span><a class="lightbox-original" target="_blank" rel="noopener">Open original</a></figcaption></figure>
      <button type="button" class="lightbox-nav next" aria-label="Next photo">&#8250;</button>`;
    image = dialog.querySelector("img");
    caption = dialog.querySelector(".lightbox-caption");
    counter = dialog.querySelector(".lightbox-counter");
    dialog.querySelector(".lightbox-close").addEventListener("click", () => dialog.close());
    dialog.querySelector(".prev").addEventListener("click", () => step(-1));
    dialog.querySelector(".next").addEventListener("click", () => step(1));
    // A click on the backdrop (outside the figure and buttons) closes it.
    dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
    dialog.addEventListener("keydown", (event) => {
      if (event.key === "ArrowLeft") step(-1);
      if (event.key === "ArrowRight") step(1);
    });
    dialog.addEventListener("close", () => image.removeAttribute("src"));
    document.body.append(dialog);
  }

  function show(i) {
    index = (i + links.length) % links.length;
    const link = links[index];
    const thumb = link.querySelector("img");
    // Show the already-loaded thumbnail at once, then swap in the full-size
    // photo when it arrives; originals from a phone can be several MB.
    image.src = thumb ? thumb.currentSrc || thumb.src : link.href;
    image.classList.add("loading");
    const full = new window.Image();
    full.onload = () => {
      if (links[index] === link) {
        image.src = full.src;
        image.classList.remove("loading");
      }
    };
    full.src = link.href;
    image.alt = thumb ? thumb.alt : "";
    caption.textContent = link.dataset.caption || (thumb && thumb.alt) || "";
    counter.textContent = links.length > 1 ? `${index + 1} / ${links.length}` : "";
    dialog.querySelector(".lightbox-original").href = link.href;
    dialog.classList.toggle("single", links.length < 2);
  }

  function step(delta) {
    if (links.length > 1) show(index + delta);
  }

  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[data-lightbox]");
    if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    if (!dialog || !dialog.isConnected) build();
    links = [...document.querySelectorAll(`a[data-lightbox="${CSS.escape(link.dataset.lightbox)}"]`)];
    show(links.indexOf(link));
    if (!dialog.open) dialog.showModal();
  });
})();
