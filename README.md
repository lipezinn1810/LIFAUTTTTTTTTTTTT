# Palestrantes do Integra 2026

Trabalho de Linguagens Formais e Autômatos, do curso de Engenharia de Computação. O programa lê a página do [Integra 2026](https://eventos.ifgoiano.edu.br/integra2026/), salva o HTML em um TXT e usa expressões regulares para coletar os dados dos palestrantes. Depois, baixa as fotos e grava os registros no SQLite.

O projeto usa apenas a biblioteca padrão do Python. Não precisa de BeautifulSoup, pandas, servidor de banco de dados nem instalação de pacotes pelo pip.

## Como executar no Windows

Instale o Python 3.10 ou superior e extraia o ZIP. Abra o terminal na pasta `integra-2026-regex-sqlite` e execute:

```powershell
python main.py
python consultar_banco.py
```

Se o comando `python` não estiver disponível, use `py -3` no lugar dele. Também é possível abrir `executar_windows.bat` com dois cliques. A janela fica aberta para mostrar o resultado ou a mensagem de erro.

Para aproveitar o HTML que já está salvo:

```powershell
python main.py --usar-txt
```

Essa opção ainda precisa de internet para baixar as imagens. Para apenas consultar os resultados entregues, use `consultar_banco.py`, que funciona sem conexão.

Os caminhos são calculados a partir da pasta dos scripts. Por isso, executar o programa a partir de outra pasta não muda o lugar onde os arquivos são salvos.

## Arquivos

```text
integra-2026-regex-sqlite/
├── main.py                 Coleta, extração, imagens e gravação
├── consultar_banco.py      Consulta dos registros pelo terminal
├── verificar_resultado.py  Comparação entre TXT, banco e imagens
├── executar_windows.bat    Atalho de execução no Windows
├── requirements.txt        Informa que não há dependências externas
├── pagina_evento.txt       HTML real, salvo em UTF-8
├── event.db                Banco SQLite da coleta
├── download/               Fotos dos palestrantes
├── tests/test_main.py      Testes com dados fictícios
├── VALIDACAO.md            Resultado das verificações da entrega
└── .gitignore
```

## Etapas do trabalho

| Tarefa | Implementação |
| --- | --- |
| 1. Acessar a página | `requisitar()` usa `urllib.request`, timeout de 30 segundos e verificação HTTPS padrão. |
| 2. Salvar o código-fonte | `baixar_html()` grava a resposta em `pagina_evento.txt`, com codificação UTF-8. |
| 3. Extrair os dados com regex | `extrair_dados()` lê o TXT e encontra nome, descrição profissional, e-mail e URL da imagem. |
| 4. Baixar as imagens | `baixar_imagens()` salva as fotos em `download/`. |
| 5. Criar o banco e a tabela | `salvar_no_banco()` cria `event.db` e a tabela `speaker`. |
| 6. Inserir e consultar os registros | A inserção usa parâmetros e transação; `consultar_banco.py` mostra os dados salvos. |

## Como a extração funciona

O site usa IDs como `Palestrante1` no cartão e `modal1` na janela com os detalhes. O programa encontra as tags de abertura `div` com regex, lê seus IDs e aplica o padrão `(Palestrante|modal)(\d+)`. O primeiro grupo identifica o tipo de bloco; o segundo guarda o número usado para associar cartão e modal. Os números vêm do próprio HTML, sem uma quantidade fixa no código.

Cada trecho é limitado pelo próximo cartão ou modal. Dentro do cartão, a extração termina no fechamento do link. Dentro do modal, termina antes de `modal-footer`. Esse limite é necessário para não pegar o e-mail do próximo palestrante ou do rodapé geral, principalmente no último registro.

No modal, padrões como `<h4\b[^>]*>(.*?)</h4\s*>` recuperam o nome; o mesmo formato com `h6` recupera a descrição profissional. `re.S` permite que o conteúdo tenha quebras de linha e `re.I` aceita variações de maiúsculas e minúsculas. O `.*?` para na primeira ocorrência do fechamento esperado.

O e-mail é procurado somente no texto do modal, com um padrão formado por uma parte local, `@` e um domínio com pontos. Se houver mais de um endereço diferente, o programa informa a ambiguidade em vez de escolher um. A regex atende aos endereços publicados nessa página; não pretende validar todos os formatos permitidos pelos padrões de e-mail.

Os atributos aceitam aspas simples ou duplas. `texto_limpo()` remove tags internas, converte entidades com `html.unescape()` e reduz sequências de espaços e quebras de linha. `urljoin()` transforma o `src` relativo da imagem em URL absoluta.

O campo `name` mantém o texto do `h4`. Na página atual, alguns títulos usam nomes públicos, como Bia Kalunga e Dona Fiota. O programa não troca esses títulos por nomes encontrados na biografia. O campo `work` também mantém a descrição do `h6`, sem completar informações por conta própria.

As regex foram feitas para essa estrutura observada. HTML em geral permite aninhamento e variações que não são cobertos por esses padrões. Se os IDs, os títulos ou o rodapé dos modais mudarem, a coleta pode precisar de ajuste. Estruturas não reconhecidas, campos vazios e associações incompletas interrompem a execução com uma mensagem.

## Imagens e banco

As fotos são baixadas primeiro para uma pasta temporária. O programa confere o tipo HTTP e a assinatura de PNG, JPEG, GIF ou WebP. Essa conferência detecta respostas HTML e formatos inesperados; não faz uma decodificação completa da imagem.

O nome salvo tem um prefixo seguro, uma parte do nome original e um resumo SHA-256 do conteúdo. Assim, fotos diferentes que tenham o mesmo nome na URL não se sobrescrevem. O banco guarda somente esse nome, sem caminho nem URL. Fotos de coletas antigas podem permanecer na pasta, mas a tabela aponta para as fotos da coleta atual.

```sql
CREATE TABLE IF NOT EXISTS speaker (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) NOT NULL,
    work VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    image VARCHAR(255) NOT NULL
);
```

A gravação acontece depois da extração e de todos os downloads. Uma transação substitui os registros de `speaker` pelos da coleta atual, usando `DELETE` e `INSERT` parametrizado. Se a inserção falhar, o SQLite desfaz a transação e mantém os registros anteriores. Se a extração ou um download falhar, a gravação nem começa.

Isso evita duplicação ao executar novamente. Os IDs podem aumentar a cada execução, porque a coluna usa `AUTOINCREMENT`; eles identificam linhas do banco, não os números dos cartões do site. A tabela é uma fotografia da coleta atual, não um histórico de edições.

## Testes e conferência

```powershell
python -m unittest discover -s tests -v
python verificar_resultado.py
```

Os testes não acessam a internet. Os nomes, endereços `example.org` e bytes de imagem usados nas amostras são fictícios e ficam separados dos dados reais. Há testes de associação fora de ordem, acentos, entidades, URLs relativas, campos ausentes, e-mail de outro bloco, IDs repetidos, falhas de rede, colisão de nomes de fotos, transação e reexecução sem duplicação.

`verificar_resultado.py` conta os cartões do TXT, compara o total extraído com o banco, confere os dados e verifica se cada imagem existe e tem conteúdo. Também consulta `PRAGMA table_info(speaker)` e `PRAGMA integrity_check`.

Os resultados da execução no site real estão em `VALIDACAO.md`. Uma mudança futura no site pode alterar a quantidade de palestrantes.

## GitHub

O repositório local usa a branch `main`. O ZIP não inclui a pasta `.git`, caches, ambiente virtual ou credenciais. Os arquivos reais da coleta fazem parte da entrega e são incluídos no versionamento.

Para publicar uma cópia extraída do ZIP em um repositório privado, caso ele ainda não exista na sua conta:

```powershell
gh auth login -h github.com
git init -b main
git add .
git commit -m "feat: coleta palestrantes do Integra 2026 com regex e SQLite"
gh repo create integra-2026-regex-sqlite --private --source=. --remote=origin --push
```

Se o repositório já estiver publicado, clone a versão existente em vez de tentar criá-lo novamente. Antes de enviar alterações futuras, confira `git status` e execute os testes.
