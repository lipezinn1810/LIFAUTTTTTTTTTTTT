"""Lista os palestrantes sem instalar um programa de acesso ao SQLite."""

import sqlite3
import sys
from pathlib import Path


def main():
    banco = Path(__file__).resolve().parent / "event.db"
    try:
        # mode=ro evita criar um banco vazio quando o arquivo não existe.
        conexao = sqlite3.connect(banco.as_uri() + "?mode=ro", uri=True)
        try:
            linhas = conexao.execute("SELECT id, name, work, email, image FROM speaker ORDER BY id").fetchall()
        finally:
            conexao.close()
    except sqlite3.Error as erro:
        print(f"Não foi possível consultar event.db: {erro}. Execute main.py primeiro.", file=sys.stderr)
        return 1
    for numero, nome, trabalho, email, imagem in linhas:
        print(f"\n{numero}. {nome}\n   Trabalho: {trabalho}\n   E-mail: {email}\n   Imagem: {imagem}")
    print(f"\nTotal: {len(linhas)} palestrantes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
