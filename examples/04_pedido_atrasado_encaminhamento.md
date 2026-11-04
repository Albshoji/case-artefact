# Status de pedido com previsão vencida e encaminhamento para a equipe com protocolo

> Gerado por `scripts/gerar_exemplos.py` · modelo `gemini-3.5-flash-lite` · data simulada 2026-03-25 10:30 (quarta-feira)
> As chamadas de ferramenta (invisíveis para o cliente) aparecem nos blocos recolhíveis.

**👤 Cliente:** Oi, meu pedido ainda não chegou e já passou da data 😤

**🎸 Tom:** Poxa, peço desculpas por esse atraso! Para eu verificar o que aconteceu com a sua entrega, você poderia me informar o **número do pedido** e o seu **e-mail ou telefone** cadastrado? 🎸

---

**👤 Cliente:** Pedido 8, telefone 99654-7821

<details><summary>⚙️ 1 chamada(s) de ferramenta: consultar_pedido</summary>

`consultar_pedido({"numero_pedido": 8, "contato": "99654-7821"})`

```json
{
  "result": {
    "numero": 8,
    "cliente": "Ana",
    "data_compra": "2026-02-15",
    "status": "Enviado: a caminho do endereço de entrega",
    "itens": [
      "1x Kala KA-C Concert Mogno"
    ],
    "total": "R$ 349,90",
    "pagamento": "cartão de débito",
    "rastreio": "BRJL5544332BR",
    "observacoes": null,
    "previsao_entrega": "2026-02-28",
    "alerta": "Previsão de entrega vencida há 25 dias: ofereça encaminhar para a equipe."
  }
}
```

</details>

**🎸 Tom:** Ana, vi aqui que o seu pedido 8 (o *Kala KA-C Concert Mogno*) foi enviado com previsão de entrega para o dia 28/02, mas realmente está atrasado.   
  
Como a previsão venceu, posso registrar esse caso com nossa equipe para eles verificarem com urgência junto à transportadora? Se quiser, já deixo o protocolo engatilhado para você! 🎸

---

**👤 Cliente:** Sim, por favor registra aí

<details><summary>⚙️ 1 chamada(s) de ferramenta: encaminhar_para_equipe</summary>

`encaminhar_para_equipe({"contato_cliente": "99654-7821", "resumo": "Pedido 8 (Kala KA-C Concert Mogno) com previsão de entrega vencida desde 28/02 (25 dias de atraso). Cliente solicitou verificação urgente.", "motivo": "atraso_entrega", "numero_pedido": 8})`

```json
{
  "result": {
    "protocolo": "EM-20260325-3463",
    "prazo_retorno": "até 24 horas úteis"
  }
}
```

</details>

**🎸 Tom:** Prontinho, Ana! Já registrei o caso com a nossa equipe. O seu número de protocolo é o *EM-20260325-3463*.   
  
Eles vão verificar o que aconteceu com a transportadora e te dão um retorno em *até 24 horas úteis*. Qualquer coisa, estou por aqui! 🎸

---
