/* Alternância claro/escuro.
 *
 * Três estados possíveis: sem escolha (segue o sistema), "light" e "dark".
 * A escolha vira o atributo data-theme no <html> e fica no localStorage.
 * Este arquivo é carregado no <head> sem defer de propósito: aplica o tema
 * antes da primeira pintura, senão a página pisca no tema errado.
 */
(function () {
  "use strict";

  var KEY = "designtheory:theme";
  var root = document.documentElement;

  function read() {
    try {
      var value = window.localStorage.getItem(KEY);
      return value === "light" || value === "dark" ? value : null;
    } catch (error) {
      return null; // localStorage bloqueado (modo privado, cookies off)
    }
  }

  function write(value) {
    try {
      if (value) {
        window.localStorage.setItem(KEY, value);
      } else {
        window.localStorage.removeItem(KEY);
      }
    } catch (error) {
      /* segue sem persistir */
    }
  }

  function apply(value) {
    if (value === "light" || value === "dark") {
      root.setAttribute("data-theme", value);
    } else {
      root.removeAttribute("data-theme");
    }
  }

  function systemPrefersDark() {
    return (
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches
    );
  }

  function effective() {
    var chosen = root.getAttribute("data-theme");
    if (chosen === "light" || chosen === "dark") {
      return chosen;
    }
    return systemPrefersDark() ? "dark" : "light";
  }

  // 1. antes da pintura: aplica o que já estava escolhido
  apply(read());

  // 2. com o DOM pronto: liga o botão
  function wire() {
    var buttons = document.querySelectorAll("[data-theme-toggle]");
    if (!buttons.length) {
      return;
    }

    function sync() {
      var current = effective();
      for (var i = 0; i < buttons.length; i++) {
        buttons[i].setAttribute("aria-pressed", current === "dark" ? "true" : "false");
        buttons[i].setAttribute(
          "title",
          current === "dark" ? "Mudar para o tema claro" : "Mudar para o tema escuro"
        );
      }
    }

    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener("click", function () {
        var next = effective() === "dark" ? "light" : "dark";
        apply(next);
        write(next);
        sync();
      });
    }

    sync();

    // Sem escolha explícita, acompanha o sistema em tempo real
    if (typeof window.matchMedia === "function") {
      var query = window.matchMedia("(prefers-color-scheme: dark)");
      var onChange = function () {
        if (!read()) {
          sync();
        }
      };
      if (typeof query.addEventListener === "function") {
        query.addEventListener("change", onChange);
      } else if (typeof query.addListener === "function") {
        query.addListener(onChange); // Safari antigo
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }
})();
