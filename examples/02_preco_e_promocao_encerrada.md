# Consulta de preço, promoção encerrada (não pode ser prometida) e promoção ativa

> Gerado por `scripts/gerar_exemplos.py` · modelo `gemini-3.5-flash-lite` · data simulada 2026-03-25 10:30 (quarta-feira)
> As chamadas de ferramenta (invisíveis para o cliente) aparecem nos blocos recolhíveis.

**👤 Cliente:** Quanto custa o Takamine GD20?

<details><summary>⚙️ 1 chamada(s) de ferramenta: buscar_produtos</summary>

`buscar_produtos({"termo": "Takamine GD20"})`

```json
{
  "result": {
    "total_disponiveis": 1,
    "disponiveis": [
      {
        "id": 95,
        "nome": "Takamine GD20 Dreadnought Natural",
        "categoria": "Violões",
        "disponibilidade": "disponível",
        "preco_tabela": "R$ 2.199,00",
        "preco_no_pix": "R$ 2.089,05",
        "cartao": "até 12x de R$ 183,25 sem juros",
        "promocoes_encerradas": [
          "Oferta Especial (12%)"
        ],
        "descricao": "Violão dreadnought Takamine com tampo sólido em cedro. Excelente para fingerstyle com timbre quente e definido.",
        "especificacoes": {
          "top": "Cedro Sólido",
          "back_sides": "Sapele",
          "neck": "Mogno",
          "strings": "steel",
          "scale": "650mm",
          "electronics": "no",
          "color": "Natural"
        }
      }
    ],
    "indisponiveis": []
  }
}
```

</details>

**🎸 Tom:** O *Takamine GD20 Dreadnought Natural* custa *R$ 2.199,00* (ou *R$ 2.089,05* no PIX com 5% de desconto). Você também pode parcelar em até *12x de R$ 183,25* sem juros no cartão! 🎸

---

**👤 Cliente:** Mas eu vi que ele tava com 12% de desconto, ainda vale?

<details><summary>⚙️ 1 chamada(s) de ferramenta: buscar_produtos</summary>

`buscar_produtos({"termo": "Takamine GD20"})`

```json
{
  "result": {
    "total_disponiveis": 1,
    "disponiveis": [
      {
        "id": 95,
        "nome": "Takamine GD20 Dreadnought Natural",
        "categoria": "Violões",
        "disponibilidade": "disponível",
        "preco_tabela": "R$ 2.199,00",
        "preco_no_pix": "R$ 2.089,05",
        "cartao": "até 12x de R$ 183,25 sem juros",
        "promocoes_encerradas": [
          "Oferta Especial (12%)"
        ],
        "descricao": "Violão dreadnought Takamine com tampo sólido em cedro. Excelente para fingerstyle com timbre quente e definido.",
        "especificacoes": {
          "top": "Cedro Sólido",
          "back_sides": "Sapele",
          "neck": "Mogno",
          "strings": "steel",
          "scale": "650mm",
          "electronics": "no",
          "color": "Natural"
        }
      }
    ],
    "indisponiveis": []
  }
}
```

</details>

**🎸 Tom:** Essa promoção de 12% ("Oferta Especial") infelizmente já foi encerrada, então o preço atual é o de tabela por R$ 2.199,00 (ou R$ 2.089,05 no PIX) mesmo, beleza?

---

**👤 Cliente:** Poxa. Tem algum violão em promoção agora?

<details><summary>⚙️ 1 chamada(s) de ferramenta: buscar_produtos</summary>

`buscar_produtos({"so_promocoes": true, "categoria": "Violões"})`

```json
{
  "result": {
    "total_disponiveis": 2,
    "disponiveis": [
      {
        "id": 90,
        "nome": "Crafter HT-100 Folk Aço Natural",
        "categoria": "Violões",
        "disponibilidade": "disponível",
        "preco_tabela": "R$ 2.399,00",
        "promocao_ativa": "Desconto Exclusivo: 18% off → R$ 1.967,18 (sem desconto extra no PIX)",
        "cartao": "até 12x de R$ 163,93 sem juros",
        "descricao": "Violão folk de alta qualidade com tampo sólido em Spruce Engelmann. Projeção sonora superior e acabamento impecável.",
        "especificacoes": {
          "top": "Spruce Engelmann Sólido",
          "back_sides": "Mogno",
          "neck": "Mogno",
          "strings": "steel",
          "scale": "648mm",
          "electronics": "no",
          "color": "Natural"
        }
      },
      {
        "id": 94,
        "nome": "Taylor 110e Dreadnought Natural",
        "categoria": "Violões",
        "disponibilidade": "disponível",
        "preco_tabela": "R$ 5.999,00",
        "promocao_ativa": "Desconto Exclusivo: 8% off → R$ 5.519,08 (sem desconto extra no PIX)",
        "cartao": "até 12x de R$ 459,92 sem juros",
        "descricao": "Violão dreadnought Taylor com tampo sólido em Sitka Spruce e eletrônica ES2. Perfeito para palco com som amplificado de alta fidelidade.",
        "especificacoes": {
          "top": "Sitka Spruce Sólido",
          "back_sides": "Walnut",
          "neck": "Tropical Mahogany",
          "strings": "steel",
          "scale": "648mm",
          "electronics": "yes",
          "color": "Natural"
        }
      }
    ]
  }
}
```

</details>

**🎸 Tom:** Temos sim! Olha só estes violões em promoção agora:  
  
* *Crafter HT-100 Folk Aço Natural*  
De R$ 2.399,00 por *R$ 1.967,18* (18% de desconto) ou em até 12x de R$ 163,93 sem juros.  
  
* *Taylor 110e Dreadnought Natural*  
De R$ 5.999,00 por *R$ 5.519,08* (8% de desconto) ou em até 12x de R$ 459,92 sem juros.  
  
*(Nos produtos em promoção o desconto já está aplicado, então o valor do PIX é o mesmo do cartão, tá?)* Qual deles te chamou mais atenção?

---
