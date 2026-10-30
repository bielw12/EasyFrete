document.addEventListener("submit", (e) => {
  const form = e.target;
  // Clique duplo: só o primeiro envio vale. Não usar `disabled` no botão, que tiraria o name/value dele do envio.
  if (form.dataset.enviando) {
    e.preventDefault();
    return;
  }
  // Confirmação de ações destrutivas: <form data-confirmar="Tem certeza?">
  const texto = form.dataset.confirmar;
  if (texto && !window.confirm(texto)) e.preventDefault();
  // Envio cancelado ou feito pelo HTMX (que já impede o padrão) não trava o formulário.
  if (!e.defaultPrevented && form.method === "post") form.dataset.enviando = "1";
});

// O botão Voltar pode restaurar a página exatamente como foi deixada, ainda travada.
window.addEventListener("pageshow", () => {
  document.querySelectorAll("form[data-enviando]").forEach((form) => delete form.dataset.enviando);
});
