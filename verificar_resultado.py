"""Confere o TXT, o esquema do banco e os arquivos de imagem, sem internet."""

import re
import sqlite3
from contextlib import closing

from main import PASTA_PROJETO, extrair_dados


def verificar():
    pasta = PASTA_PROJETO
    txt = pasta / "pagina_evento.txt"
    # Contagem independente da função de extração, para comparar os totais.
    cartoes = re.findall(r'''\bid\s*=\s*["']Palestrante\d+["']''', txt.read_text(encoding="utf-8"), re.I)
    pessoas = extrair_dados(txt)
    with closing(sqlite3.connect((pasta / "event.db").as_uri() + "?mode=ro", uri=True)) as con:
        linhas = con.execute("SELECT name, work, email, image FROM speaker ORDER BY id").fetchall()
        esquema = con.execute("PRAGMA table_info(speaker)").fetchall()
        integridade = con.execute("PRAGMA integrity_check").fetchone()[0]
        criacao = con.execute("SELECT sql FROM sqlite_master WHERE name = 'speaker'").fetchone()[0]
    if not (len(cartoes) == len(pessoas) == len(linhas)):
        raise ValueError(f"Totais diferentes: {len(cartoes)} cartões, {len(pessoas)} extraídos, {len(linhas)} no banco.")
    esperado = [("id", "INTEGER", 0, 1)] + [(campo, "VARCHAR(255)", 1, 0) for campo in ("name", "work", "email", "image")]
    if [(c[1], c[2], c[3], c[5]) for c in esquema] != esperado or "AUTOINCREMENT" not in criacao.upper():
        raise ValueError("O esquema de speaker difere do solicitado.")
    if integridade != "ok":
        raise ValueError(f"Falha de integridade no SQLite: {integridade}")
    for pessoa, (nome, trabalho, email, imagem) in zip(pessoas, linhas):
        if (nome, trabalho, email) != (pessoa.nome, pessoa.trabalho, pessoa.email):
            raise ValueError(f"Registro diferente do TXT: {pessoa.nome}.")
        if "/" in imagem or "\\" in imagem or not imagem:
            raise ValueError(f"image precisa conter apenas o nome do arquivo: {imagem}")
        caminho = pasta / "download" / imagem
        if not caminho.is_file() or caminho.stat().st_size == 0:
            raise ValueError(f"Imagem ausente ou vazia: {imagem}")
    print(f"Cartões: {len(cartoes)} | Extraídos: {len(pessoas)} | Banco: {len(linhas)}")
    print(f"Imagens referenciadas: {len(linhas)}; todas existem e têm conteúdo.")
    print("Esquema correto; integridade SQLite: ok; dados iguais aos extraídos do TXT.")
    print("PRAGMA table_info(speaker):")
    for coluna in esquema:
        print(coluna)


if __name__ == "__main__":
    verificar()
