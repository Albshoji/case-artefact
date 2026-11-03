# Consulta de preço, promoção encerrada (não pode ser prometida) e promoção ativa

> Gerado por `scripts/gerar_exemplos.py` · modelo `gemini-3.5-flash` · data simulada 2026-03-25 10:30 (quarta-feira)
> As chamadas de ferramenta (invisíveis para o cliente) aparecem nos blocos recolhíveis.

**👤 Cliente:** Quanto custa o Takamine GD20?

<details><summary>⚙️ 2 chamada(s) de ferramenta: detalhes_produto, calcular_condicoes_pagamento</summary>

`detalhes_produto({"produto": "Takamine GD20"})`

```json
{
  "id": 95,
  "nome": "Takamine GD20 Dreadnought Natural",
  "categoria": "Violões",
  "preco_tabela": "R$ 2.199,00",
  "disponibilidade": "disponível",
  "preco_no_pix": "R$ 2.089,05",
  "descricao": "Violão dreadnought Takamine com tampo sólido em cedro. Excelente para fingerstyle com timbre quente e definido.",
  "especificacoes": {
    "tampo": "Cedro Sólido",
    "fundo e laterais": "Sapele",
    "braço": "Mogno",
    "cordas": "aço",
    "escala": "650mm",
    "eletrônica/captação": "não",
    "cor": "Natural"
  },
  "promocoes_encerradas": [
    {
      "campanha": "Oferta Especial",
      "desconto": "12%"
    }
  ]
}
```

`calcular_condicoes_pagamento({"preco_promocional": false, "valor": 2199})`

```json
{
  "valor": "R$ 2.199,00",
  "cartao_credito": {
    "max_parcelas_sem_juros": 12,
    "opcoes": [
      {
        "vezes": 1,
        "parcela": "R$ 2.199,00"
      },
      {
        "vezes": 2,
        "parcela": "R$ 1.099,50"
      },
      {
        "vezes": 3,
        "parcela": "R$ 733,00"
      },
      {
        "vezes": 4,
        "parcela": "R$ 549,75"
      },
      {
        "vezes": 5,
        "parcela": "R$ 439,80"
      },
      {
        "vezes": 6,
        "parcela": "R$ 366,50"
      },
      {
        "vezes": 7,
        "parcela": "R$ 314,14"
      },
      {
        "vezes": 8,
        "parcela": "R$ 274,88"
      },
      {
        "vezes": 9,
        "parcela": "R$ 244,33"
      },
      {
        "vezes": 10,
        "parcela": "R$ 219,90"
      },
      {
        "vezes": 11,
        "parcela": "R$ 199,91"
      },
      {
        "vezes": 12,
        "parcela": "R$ 183,25"
      }
    ]
  },
  "debito_ou_boleto": "R$ 2.199,00",
  "combinar_formas_de_pagamento": "permitido",
  "pix": "R$ 2.089,05 (5% de desconto)"
}
```

</details>

**🎸 Tom:** O *Takamine GD20 Dreadnought Natural* está disponível e custa *R$ 2.199,00*.  
  
Aqui estão as condições de pagamento:  
• *PIX*: R$ 2.089,05 (com 5% de desconto)  
• *Cartão de crédito*: até 12x de R$ 183,25 sem juros  
  
Se quiser consultar o frete para a sua região ou tirar dúvidas sobre o instrumento, é só me avisar! 🎸

---

**👤 Cliente:** Mas eu vi que ele tava com 12% de desconto, ainda vale?

**🎸 Tom:** Essa promoção da *Oferta Especial* com 12% de desconto infelizmente já encerrou, então esse valor promocional não está mais ativo no momento.  
  
Atualmente o valor do violão é o preço de tabela de *R$ 2.199,00*. Mas você ainda aproveita os *5% de desconto no PIX*, saindo por *R$ 2.089,05*, ou pode parcelar em até *12x de R$ 183,25 sem juros* no cartão de crédito.  
  
Quer dar uma olhada em outros modelos ou consultar o frete?

---

**👤 Cliente:** Poxa. Tem algum violão em promoção agora?

<details><summary>⚙️ 2 chamada(s) de ferramenta: listar_promocoes_ativas, buscar_produtos</summary>

`listar_promocoes_ativas({})`

```json
{
  "promocoes_ativas": [
    {
      "id": 90,
      "nome": "Crafter HT-100 Folk Aço Natural",
      "categoria": "Violões",
      "preco_tabela": "R$ 2.399,00",
      "disponibilidade": "disponível",
      "promocao_ativa": {
        "campanha": "Desconto Exclusivo",
        "desconto": "18%",
        "preco_promocional": "R$ 1.967,18",
        "obs": "Desconto PIX não é cumulativo com a promoção."
      }
    },
    {
      "id": 94,
      "nome": "Taylor 110e Dreadnought Natural",
      "categoria": "Violões",
      "preco_tabela": "R$ 5.999,00",
      "disponibilidade": "disponível",
      "promocao_ativa": {
        "campanha": "Desconto Exclusivo",
        "desconto": "8%",
        "preco_promocional": "R$ 5.519,08",
        "obs": "Desconto PIX não é cumulativo com a promoção."
      }
    },
    {
      "id": 121,
      "nome": "Ohana CK-20 Concert Natural",
      "categoria": "Ukuleles",
      "preco_tabela": "R$ 549,00",
      "disponibilidade": "disponível",
      "promocao_ativa": {
        "campanha": "Desconto Exclusivo",
        "desconto": "20%",
        "preco_promocional": "R$ 439,20",
        "obs": "Desconto PIX não é cumulativo com a promoção."
      }
    },
    {
      "id": 127,
      "nome": "Kalani KAL-700T Tenor Natural",
      "categoria": "Ukuleles",
      "preco_tabela": "R$ 359,00",
      "disponibilidade": "disponível",
      "promocao_ativa": {
        "campanha": "Oferta Especial",
        "desconto": "10%",
        "preco_promocional": "R$ 323,10",
        "obs": "Desconto PIX não é cumulativo com a promoção."
      }
    }
  ],
  "total": 4
}
```

`buscar_produtos({"categoria": "Violões"})`

```json
{
  "total_encontrado": 33,
  "mostrando": 8,
  "produtos": [
    {
      "id": 83,
      "nome": "Tagima Memphis AC-39 Nylon Natural",
      "categoria": "Violões",
      "preco_tabela": "R$ 429,90",
      "disponibilidade": "disponível",
      "preco_no_pix": "R$ 408,40"
    },
    {
      "id": 85,
      "nome": "Rozini RC-104 Nylon Estudante",
      "categoria": "Violões",
      "preco_tabela": "R$ 459,90",
      "disponibilidade": "disponível",
      "preco_no_pix": "R$ 436,90"
    },
    {
      "id": 89,
      "nome": "Shelby SN-100 Folk Aço Preto",
      "categoria": "Violões",
      "preco_tabela": "R$ 549,00",
      "disponibilidade": "disponível",
      "preco_no_pix": "R$ 521,55"
    },
    {
      "id": 88,
      "nome": "Giannini GF-1R Aço Folk Sunburst",
      "categoria": "Violões",
      "preco_tabela": "R$ 579,90",
      "disponibilidade": "disponível",
      "preco_no_pix": "R$ 550,90"
    },
    {
      "id": 81,
      "nome": "Yamaha C40 Nylon Natural",
      "categoria": "Violões",
      "preco_tabela": "R$ 599,90",
      "disponibilidade": "disponível",
      "preco_no_pix": "R$ 569,90"
    },
    {
      "id": 84,
      "nome": "Giannini GN-15 Nylon Cedr Natural",
      "categoria": "Violões",
      "preco_tabela": "R$ 689,00",
      "disponibilidade": "disponível",
      "preco_no_pix": "R$ 654,55"
    },
    {
      "id": 87,
      "nome": "Yamaha F310 Aço Natural",
      "categoria": "Violões",
      "preco_tabela": "R$ 699,90",
      "disponibilidade": "disponível",
      "preco_no_pix": "R$ 664,90"
    },
    {
      "id": 86,
      "nome": "Tagima Dallas Tuner Aço Natural",
      "categoria": "Violões",
      "preco_tabela": "R$ 749,00",
      "disponibilidade": "disponível",
      "preco_no_pix": "R$ 711,55"
    }
  ],
  "filtro_preco_considera": "preço efetivo (promocional, se houver; sem desconto PIX)"
}
```

</details>

**🎸 Tom:** Temos sim! Atualmente temos dois violões com promoção ativa na categoria:  
  
• *Crafter HT-100 Folk Aço Natural*  
  De *R$ 2.399,00* por *R$ 1.967,18* (18% de desconto)  
  
• *Taylor 110e Dreadnought Natural*  
  De *R$ 5.999,00* por *R$ 5.519,08* (8% de desconto)  
  
*(Lembrando que o desconto extra de 5% do PIX não acumula com o preço promocional).*  
  
Algum desses modelos te interessa ou gostaria de ver outras opções de violão no nosso catálogo? 🎸

---
