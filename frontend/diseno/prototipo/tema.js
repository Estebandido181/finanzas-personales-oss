// Único JavaScript del prototipo: dos preferencias que se recuerdan en el
// dispositivo (localStorage; no son datos financieros):
//   - Apariencia: Sistema, Claro u Oscuro  → data-tema en <html>.
//   - Vista del gráfico "¿En qué se fue?": Barras (por defecto) o Dona
//                                           → data-grafico en <html>.
// Se carga en <head> sin defer para aplicarlas antes de pintar (evita el
// destello de modo o de gráfico equivocado). Sin código en línea: la CSP de
// la app no lo permite.
(function () {
  var raiz = document.documentElement;

  function leer(clave) {
    try { return localStorage.getItem(clave); } catch (e) { return null; }
  }
  function guardar(clave, valor) {
    try {
      if (valor === null) localStorage.removeItem(clave); else localStorage.setItem(clave, valor);
    } catch (e) { /* sin almacenamiento: la elección dura hasta recargar */ }
  }

  // Cada preferencia: clave de almacenamiento, atributo en <html>, atributo de
  // los botones que la eligen, valor por defecto (que no se guarda) y valores
  // válidos.
  var PREFERENCIAS = [
    { clave: "finanzas-tema", atributo: "data-tema", boton: "data-elegir-tema",
      defecto: "sistema", validos: ["claro", "oscuro"] },
    { clave: "finanzas-grafico", atributo: "data-grafico", boton: "data-elegir-grafico",
      defecto: "barras", validos: ["dona"] }
  ];

  function aplicar(p, valor) {
    if (p.validos.indexOf(valor) >= 0) raiz.setAttribute(p.atributo, valor);
    else { raiz.removeAttribute(p.atributo); valor = p.defecto; }
    document.querySelectorAll("[" + p.boton + "]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute(p.boton) === valor));
    });
  }

  // Solo para las capturas del prototipo: con ?captura la barra inferior se
  // dibuja al pie de la página y no a mitad de una captura de página completa.
  if (/[?&]captura\b/.test(location.search)) raiz.classList.add("captura");

  PREFERENCIAS.forEach(function (p) { aplicar(p, leer(p.clave)); });

  document.addEventListener("DOMContentLoaded", function () {
    PREFERENCIAS.forEach(function (p) { aplicar(p, leer(p.clave)); });
    document.addEventListener("click", function (ev) {
      PREFERENCIAS.forEach(function (p) {
        var b = ev.target.closest("[" + p.boton + "]");
        if (!b) return;
        var valor = b.getAttribute(p.boton);
        guardar(p.clave, valor === p.defecto ? null : valor);
        aplicar(p, valor);
      });
    });
  });
})();
