/* Filtro da galeria por categoria.
 *
 * Progressive enhancement: os chips só aparecem porque o theme.js marcou
 * <html class="js"> antes da primeira pintura. Sem JavaScript o CSS os
 * mantém escondidos e a grade aparece inteira — nada de oferecer um
 * controle que não responde.
 *
 * A categoria escolhida vira o hash da URL, então dá para compartilhar
 * "…/#ux-pesquisa" e cair na home já filtrada.
 */
(function () {
  "use strict";

  var bar = document.querySelector("[data-filters]");
  var gallery = document.querySelector("[data-gallery]");
  if (!bar || !gallery) {
    return;
  }

  var buttons = Array.prototype.slice.call(bar.querySelectorAll("[data-filter]"));
  var tiles = Array.prototype.slice.call(gallery.querySelectorAll(".tile"));
  var status = document.querySelector("[data-filter-status]");
  var known = buttons.map(function (b) {
    return b.getAttribute("data-filter");
  });

  function apply(slug, updateUrl) {
    if (known.indexOf(slug) === -1) {
      slug = "all";
    }

    var shown = 0;
    tiles.forEach(function (tile) {
      var match = slug === "all" || tile.getAttribute("data-category") === slug;
      tile.hidden = !match;
      if (match) {
        shown += 1;
      }
    });

    buttons.forEach(function (button) {
      var on = button.getAttribute("data-filter") === slug;
      button.classList.toggle("is-active", on);
      button.setAttribute("aria-pressed", on ? "true" : "false");
    });

    if (status) {
      status.textContent = shown + (shown === 1 ? " item" : " itens");
    }

    if (updateUrl && window.history && window.history.replaceState) {
      var url = slug === "all" ? window.location.pathname : "#" + slug;
      try {
        window.history.replaceState(null, "", url);
      } catch (error) {
        /* file:// e afins recusam replaceState; o filtro segue funcionando */
      }
    }
  }

  buttons.forEach(function (button) {
    button.addEventListener("click", function () {
      apply(button.getAttribute("data-filter"), true);
    });
  });

  window.addEventListener("hashchange", function () {
    apply(window.location.hash.replace("#", ""), false);
  });

  apply(window.location.hash.replace("#", ""), false);
})();
