// Confirmação de ações destrutivas: <form data-confirmar="Tem certeza?">
document.addEventListener("submit", (e) => {
  const texto = e.target.dataset?.confirmar;
  if (texto && !window.confirm(texto)) e.preventDefault();
});
