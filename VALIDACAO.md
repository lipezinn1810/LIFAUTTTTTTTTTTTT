# Conferência da entrega

Coleta realizada em 3 de outubro de 2026, no Windows, com Python 3.12.10.

Fonte: https://eventos.ifgoiano.edu.br/integra2026/

O programa foi executado duas vezes contra o site real. A primeira execução gravou 9 palestrantes; a segunda manteve 9, sem duplicação. O TXT e as imagens desta pasta vieram dessas requisições.

| Verificação | Resultado |
| --- | --- |
| Cartões `PalestranteN` no HTML salvo | 9 |
| Registros extraídos do TXT | 9 |
| `SELECT COUNT(*) FROM speaker` | 9 |
| Fotos referenciadas no banco | 9, todas presentes e não vazias |
| Comparação dos nomes, descrições e e-mails com o TXT | Iguais |
| Esquema de `speaker` | Conforme o solicitado |
| `PRAGMA integrity_check` | `ok` |
| Testes automatizados | 18 aprovados |

Resultado de `PRAGMA table_info(speaker)`:

```text
(0, 'id', 'INTEGER', 0, None, 1)
(1, 'name', 'VARCHAR(255)', 1, None, 0)
(2, 'work', 'VARCHAR(255)', 1, None, 0)
(3, 'email', 'VARCHAR(255)', 1, None, 0)
(4, 'image', 'VARCHAR(255)', 1, None, 0)
```

Para repetir as verificações sem internet:

```powershell
python -m unittest discover -s tests -v
python verificar_resultado.py
python consultar_banco.py
```

O projeto declara compatibilidade com Python 3.10 ou superior, mas a execução desta entrega foi verificada no Python 3.12.10. Mudanças futuras na estrutura do site podem exigir ajuste das regex.
