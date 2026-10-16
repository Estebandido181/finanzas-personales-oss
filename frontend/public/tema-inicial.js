// Aplica las preferencias del dispositivo antes de que React pinte, para que
// no haya destello de modo claro/oscuro equivocado. Mismas claves que el
// prototipo (frontend/diseno/prototipo/tema.js) y que src/tema/preferencias.ts:
//   finanzas-tema    -> data-tema en <html>    ("claro" | "oscuro"; sin valor = sistema)
//   finanzas-grafico -> data-grafico en <html> ("dona"; sin valor = barras)
// Son preferencias, no datos financieros: por eso pueden ir en localStorage.
// Archivo aparte (no en línea) porque la CSP solo permite scripts de 'self'.
(function () {
  var raiz = document.documentElement;
  var preferencias = [
    ["finanzas-tema", "data-tema", ["claro", "oscuro"]],
    ["finanzas-grafico", "data-grafico", ["dona"]]
  ];
  preferencias.forEach(function (p) {
    var valor = null;
    try { valor = localStorage.getItem(p[0]); } catch (e) { /* sin almacenamiento */ }
    if (p[2].indexOf(valor) >= 0) raiz.setAttribute(p[1], valor);
  });
})();
