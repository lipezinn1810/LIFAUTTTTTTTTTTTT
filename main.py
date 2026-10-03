"""Coleta os palestrantes do Integra 2026 usando regex e SQLite."""

import argparse
import hashlib
import html
import re
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import Request, urlopen


URL_EVENTO = "https://eventos.ifgoiano.edu.br/integra2026/"
PASTA_PROJETO = Path(__file__).resolve().parent
TIMEOUT = 30
LIMITE_BYTES = 20 * 1024 * 1024

# Alternativas entre aspas permitem que um atributo contenha o caractere >.
ATRIBUTOS = r'''(?:[^>"']|"[^"]*"|'[^']*')*'''
DIV = re.compile(r"<div\b" + ATRIBUTOS + r">", re.I)
EMAIL = re.compile(r"[\w.!#$%&'*+/=?^`{|}~-]+@[\w-]+(?:\.[\w-]+)+", re.I)

ESQUEMA = """CREATE TABLE IF NOT EXISTS speaker (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) NOT NULL,
    work VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    image VARCHAR(255) NOT NULL
);"""


class ErroProjeto(Exception):
    """Erro de coleta com uma mensagem que pode ser mostrada no terminal."""


@dataclass(frozen=True)
class Palestrante:
    numero: int
    nome: str
    trabalho: str
    email: str
    imagem_url: str


def atributo(tag, nome):
    """Lê um atributo com aspas simples ou duplas, sem confundir id com data-id."""
    padrao = r'''\s''' + re.escape(nome) + r'''\s*=\s*(["'])(.*?)\1'''
    resultado = re.search(padrao, tag, re.I | re.S)
    return html.unescape(resultado.group(2)).strip() if resultado else ""


def texto_limpo(fragmento):
    fragmento = re.sub(r"<[^>]*>", " ", fragmento)
    return re.sub(r"\s+", " ", html.unescape(fragmento)).strip()


def requisitar(url):
    """Faz uma requisição com timeout e mantém a verificação HTTPS padrão."""
    if urlsplit(url).scheme not in {"http", "https"}:
        raise ErroProjeto(f"Endereço HTTP inválido: {url}")
    pedido = Request(url, headers={"User-Agent": "Integra2026-ColetaAcademica/1.0"})
    try:
        with urlopen(pedido, timeout=TIMEOUT) as resposta:
            if resposta.status != 200:
                raise ErroProjeto(f"Resposta HTTP {resposta.status}: {url}")
            conteudo = resposta.read(LIMITE_BYTES + 1)
            if not conteudo or len(conteudo) > LIMITE_BYTES:
                raise ErroProjeto(f"Resposta vazia ou maior que 20 MB: {url}")
            tamanho = resposta.headers.get("Content-Length")
            if tamanho is not None and int(tamanho) != len(conteudo):
                raise ErroProjeto(f"Download incompleto: {url}")
            return (conteudo, resposta.headers.get_content_type(),
                    resposta.headers.get_content_charset())
    except (HTTPError, URLError, HTTPException, OSError, ValueError) as erro:
        raise ErroProjeto(f"Não foi possível baixar {url}: {erro}") from erro


def baixar_html(destino, url=URL_EVENTO):
    conteudo, tipo, codificacao = requisitar(url)
    if tipo not in {"text/html", "application/xhtml+xml"}:
        raise ErroProjeto(f"Era esperado HTML, mas o servidor enviou {tipo}.")
    try:
        texto = conteudo.decode(codificacao or "utf-8")
    except (UnicodeError, LookupError) as erro:
        raise ErroProjeto(f"Não foi possível decodificar o HTML: {erro}") from erro
    # Só substitui o TXT depois que a resposta foi recebida e decodificada.
    gravar_atomico(destino, texto.encode("utf-8"))


def gravar_atomico(destino, conteudo):
    # O temporário fica na pasta de destino para herdar suas permissões no Windows.
    with tempfile.NamedTemporaryFile(dir=destino.parent, delete=False) as arquivo:
        temporario = Path(arquivo.name)
        try:
            arquivo.write(conteudo)
        except OSError:
            arquivo.close()
            temporario.unlink(missing_ok=True)
            raise
    try:
        temporario.replace(destino)
    finally:
        temporario.unlink(missing_ok=True)


def extrair_dados(arquivo_txt, url_base=URL_EVENTO):
    """Lê o TXT e associa PalestranteN a modalN, sem parser HTML."""
    fonte = arquivo_txt.read_text(encoding="utf-8")
    fonte = re.sub(r"<!--.*?-->|<script\b[^>]*>.*?</script\s*>", "", fonte, flags=re.I | re.S)
    marcadores = []
    for tag in DIV.finditer(fonte):
        identificador = atributo(tag.group(), "id")
        encontrado = re.fullmatch(r"(Palestrante|modal)(\d+)", identificador, re.I)
        if encontrado:
            marcadores.append((encontrado.group(1).lower(), int(encontrado.group(2)), tag))
    if not marcadores:
        raise ErroProjeto("Nenhum cartão PalestranteN encontrado. Confira se a estrutura do site mudou.")

    cartoes, modais = {}, {}
    for indice, (tipo, numero, tag) in enumerate(marcadores):
        fim = marcadores[indice + 1][2].start() if indice + 1 < len(marcadores) else len(fonte)
        trecho = fonte[tag.end():fim]
        grupo = cartoes if tipo == "palestrante" else modais
        if numero in grupo:
            raise ErroProjeto(f"ID repetido na página: {tipo}{numero}.")
        if tipo == "palestrante":
            fim_cartao = re.search(r"</a\s*>\s*</div\s*>", trecho, re.I)
            if not fim_cartao:
                raise ErroProjeto(f"Palestrante{numero}: estrutura do cartão não reconhecida.")
            trecho = trecho[:fim_cartao.start()]
            links = re.findall(r"<a\b" + ATRIBUTOS + r">", trecho, re.I)
            if not any(atributo(link, "href").lower() == f"#modal{numero}" for link in links):
                raise ErroProjeto(f"Palestrante{numero}: ligação com modal{numero} ausente ou incorreta.")
        else:
            # O rodapé do modal encerra o trecho de dados. Isso impede que o
            # último modal use, por engano, o e-mail do rodapé geral da página.
            rodape = next((div for div in DIV.finditer(trecho)
                           if "modal-footer" in atributo(div.group(), "class").split()), None)
            if rodape is None:
                raise ErroProjeto(f"Palestrante{numero}: fim do modal não reconhecido (modal-footer ausente).")
            trecho = trecho[:rodape.start()]
        grupo[numero] = trecho

    if cartoes.keys() != modais.keys():
        faltam_modais = sorted(cartoes.keys() - modais.keys())
        faltam_cartoes = sorted(modais.keys() - cartoes.keys())
        raise ErroProjeto(f"Associação incompleta: cartões sem modal {faltam_modais}; modais sem cartão {faltam_cartoes}.")

    palestrantes, erros = [], []
    for numero in sorted(cartoes):
        modal = modais[numero]
        campos = []
        for tag in ("h4", "h6"):
            resultado = re.search(r"<" + tag + r"\b[^>]*>(.*?)</" + tag + r"\s*>", modal, re.I | re.S)
            campos.append(texto_limpo(resultado.group(1)) if resultado else "")
        nome, trabalho = campos
        emails = sorted(set(EMAIL.findall(texto_limpo(modal))))
        imagens = re.findall(r"<img\b" + ATRIBUTOS + r">", cartoes[numero], re.I)
        origens = {atributo(imagem, "src") for imagem in imagens if atributo(imagem, "src")}
        faltantes = [campo for campo, valor in [("nome (h4)", nome), ("trabalho (h6)", trabalho)] if not valor]
        if len(emails) != 1:
            faltantes.append("e-mail ausente" if not emails else "e-mail ambíguo (mais de um endereço)")
        if len(origens) != 1:
            faltantes.append("imagem ausente" if not origens else "imagem ambígua (mais de um src)")
        imagem_url = urljoin(url_base, next(iter(origens), ""))
        if origens and urlsplit(imagem_url).scheme not in {"http", "https"}:
            faltantes.append("imagem com URL inválida")
        if faltantes:
            erros.append(f"Palestrante{numero} ({nome or 'nome ausente'}): " + "; ".join(faltantes))
        else:
            palestrantes.append(Palestrante(numero, nome, trabalho, emails[0], imagem_url))
    if erros:
        raise ErroProjeto("Campos incompletos ou ambíguos:\n" + "\n".join(erros))
    if not palestrantes:
        raise ErroProjeto("Nenhum palestrante completo foi encontrado.")
    return palestrantes


def extensao_imagem(conteudo, tipo):
    """Confere o tipo HTTP e a assinatura dos formatos usados para fotos."""
    if tipo == "image/png" and conteudo.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if tipo == "image/jpeg" and conteudo.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if tipo == "image/gif" and conteudo[:6] in {b"GIF87a", b"GIF89a"}:
        return ".gif"
    if tipo == "image/webp" and conteudo.startswith(b"RIFF") and conteudo[8:12] == b"WEBP":
        return ".webp"
    raise ErroProjeto(f"Resposta não reconhecida como foto PNG, JPEG, GIF ou WebP (tipo: {tipo}).")


def baixar_imagens(palestrantes, pasta):
    pasta.mkdir(parents=True, exist_ok=True)
    nomes = {}
    # Uma falha de rede não substitui nenhuma foto da coleta anterior.
    with tempfile.TemporaryDirectory(dir=pasta.parent) as temporaria:
        for pessoa in palestrantes:
            try:
                conteudo, tipo, _ = requisitar(pessoa.imagem_url)
                extensao = extensao_imagem(conteudo, tipo)
            except ErroProjeto as erro:
                raise ErroProjeto(f"Palestrante{pessoa.numero} ({pessoa.nome}), imagem: {erro}") from erro
            origem = Path(unquote(urlsplit(pessoa.imagem_url).path)).stem
            nome_base = re.sub(r"[^a-zA-Z0-9_-]", "_", origem)[:60] or "imagem"
            resumo = hashlib.sha256(conteudo).hexdigest()[:16]
            nome = f"foto_{nome_base}_{resumo}{extensao}"
            (Path(temporaria) / nome).write_bytes(conteudo)
            nomes[pessoa.numero] = nome
        for nome in set(nomes.values()):
            gravar_atomico(pasta / nome, (Path(temporaria) / nome).read_bytes())
    return nomes


def salvar_no_banco(palestrantes, imagens, banco):
    if not palestrantes:
        raise ErroProjeto("Lista vazia: o banco não será alterado.")
    linhas = [(p.nome, p.trabalho, p.email, imagens[p.numero]) for p in palestrantes]
    conexao = sqlite3.connect(banco)
    try:
        with conexao:
            conexao.execute("BEGIN IMMEDIATE")
            conexao.execute(ESQUEMA)
            # A tabela representa a coleta atual. DELETE e INSERT pertencem à
            # mesma transação: qualquer erro desfaz as duas operações.
            conexao.execute("DELETE FROM speaker")
            conexao.executemany("INSERT INTO speaker (name, work, email, image) VALUES (?, ?, ?, ?)", linhas)
    finally:
        conexao.close()


def executar(usar_txt=False, base=PASTA_PROJETO):
    arquivo = base / "pagina_evento.txt"
    if usar_txt:
        print("Usando o TXT salvo. O download das imagens ainda precisa de internet.")
    else:
        baixar_html(arquivo)
        print(f"HTML salvo em {arquivo}")
    palestrantes = extrair_dados(arquivo)
    print(f"Cartões e modais conferidos: {len(palestrantes)} palestrantes.")
    imagens = baixar_imagens(palestrantes, base / "download")
    salvar_no_banco(palestrantes, imagens, base / "event.db")
    print(f"Concluído: {len(palestrantes)} registros em event.db e todas as imagens salvas.")
    return len(palestrantes)


def main():
    argumentos = argparse.ArgumentParser(description=__doc__)
    argumentos.add_argument("--usar-txt", action="store_true", help="reutiliza pagina_evento.txt; as imagens continuam sendo baixadas")
    opcoes = argumentos.parse_args()
    try:
        executar(opcoes.usar_txt)
    except (ErroProjeto, OSError, UnicodeError, sqlite3.Error) as erro:
        print(f"Erro: {erro}\nA gravação da nova coleta no banco não foi concluída.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
