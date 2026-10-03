"""Amostras inteiramente fictícias: não representam os palestrantes do evento."""

import sqlite3
from contextlib import closing
import tempfile
import unittest
from email.message import Message
from http.client import IncompleteRead
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import main


def cartao(numero, imagem="/fotos/retrato.png"):
    return f"""<div id='Palestrante{numero}' class='palestrante-item'>
    <a href='#modal{numero}'><div><img alt='foto' src='{imagem}'></div></a></div>"""


def modal(numero, nome="Ana <em>Fictícia</em> &amp; Silva", email="ana@example.org"):
    return f"""<div class='modal fade' id='modal{numero}'>
    <div class='modal-header'><h4>{nome}</h4><h6>Instituto&nbsp;Fictício<br>de Pesquisa</h6></div>
    <div class='modal-body'><p>{email}</p></div>
    <div class='modal-footer'><button>Fechar</button></div></div>"""


AMOSTRA = cartao(1) + modal(1)
PNG = b"\x89PNG\r\n\x1a\n" + b"conteudo ficticio apenas para testar o download"


class ProjetoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def extrair(self, conteudo):
        arquivo = self.base / "pagina_evento.txt"
        arquivo.write_text(conteudo, encoding="utf-8")
        return main.extrair_dados(arquivo)

    def test_associa_por_numero_mesmo_com_modais_fora_de_ordem(self):
        dados = self.extrair(cartao(2) + cartao(1) + modal(1) + modal(2, "Bruno Exemplo", "bruno@example.org"))
        self.assertEqual([p.nome for p in dados], ["Ana Fictícia & Silva", "Bruno Exemplo"])
        self.assertEqual(dados[1].email, "bruno@example.org")

    def test_entidades_tags_acentos_aspas_e_urls_relativas(self):
        for fonte in [AMOSTRA, AMOSTRA.replace("'", '"')]:
            with self.subTest(fonte=fonte):
                dado = self.extrair(fonte)[0]
                self.assertEqual(dado.nome, "Ana Fictícia & Silva")
                self.assertEqual(dado.trabalho, "Instituto Fictício de Pesquisa")
                self.assertEqual(dado.imagem_url, "https://eventos.ifgoiano.edu.br/fotos/retrato.png")

    def test_cada_campo_ausente_identifica_registro(self):
        casos = [("<h4>.*?</h4>", "nome"), ("<h6>.*?</h6>", "trabalho"),
                 ("ana@example.org", "e-mail"), ("<img[^>]*>", "imagem")]
        for padrao, campo in casos:
            with self.subTest(campo=campo):
                fonte = main.re.sub(padrao, "", AMOSTRA)
                with self.assertRaisesRegex(main.ErroProjeto, "Palestrante1.*" + campo):
                    self.extrair(fonte)

    def test_nao_empresta_email_do_rodape_ou_de_outro_modal(self):
        fonte = cartao(1) + modal(1, email="") + cartao(2) + modal(2)
        fonte += "<footer>geral@example.org</footer>"
        with self.assertRaisesRegex(main.ErroProjeto, "Palestrante1.*e-mail"):
            self.extrair(fonte)
        with self.assertRaisesRegex(main.ErroProjeto, "Palestrante1.*e-mail"):
            self.extrair(cartao(1) + modal(1, email="") + "<footer>geral@example.org</footer>")

    def test_estrutura_incompativel_e_ids_duplicados(self):
        for fonte in ["<html>Sem cartões</html>", cartao(1), modal(1),
                      AMOSTRA + AMOSTRA, AMOSTRA.replace("modal-footer", "rodape"),
                      cartao(1).replace("#modal1", "#modal2") + modal(1)]:
            with self.subTest(fonte=fonte):
                with self.assertRaises(main.ErroProjeto):
                    self.extrair(fonte)

    def test_email_ambiguo_nao_e_escolhido_silenciosamente(self):
        with self.assertRaisesRegex(main.ErroProjeto, "Palestrante1.*e-mail"):
            self.extrair(cartao(1) + modal(1, email="a@example.org b@example.org"))

    def test_comentarios_e_scripts_nao_geram_registros(self):
        dados = self.extrair(AMOSTRA + "<!--" + AMOSTRA + "-->" + "<script>" + AMOSTRA + "</script>")
        self.assertEqual(len(dados), 1)

    def test_banco_sem_duplicacao_parametros_e_esquema(self):
        dados = self.extrair(cartao(1) + modal(1, "Ana D'Exemplo"))
        banco = self.base / "event.db"
        for _ in range(2):
            main.salvar_no_banco(dados, {1: "foto.png"}, banco)
        with closing(sqlite3.connect(banco)) as con:
            self.assertEqual(con.execute("SELECT name, image FROM speaker").fetchall(), [("Ana D'Exemplo", "foto.png")])
            colunas = con.execute("PRAGMA table_info(speaker)").fetchall()
            self.assertEqual([(c[1], c[2], c[3], c[5]) for c in colunas],
                             [("id", "INTEGER", 0, 1)] + [(c, "VARCHAR(255)", 1, 0) for c in ["name", "work", "email", "image"]])

    def test_transacao_preserva_dados_se_insercao_falhar(self):
        dados = self.extrair(AMOSTRA)
        banco = self.base / "event.db"
        main.salvar_no_banco(dados, {1: "foto.png"}, banco)
        with closing(sqlite3.connect(banco)) as con:
            con.execute("CREATE TRIGGER falhar BEFORE INSERT ON speaker BEGIN SELECT RAISE(ABORT, 'falha simulada'); END")
        with self.assertRaises(sqlite3.Error):
            main.salvar_no_banco(dados, {1: "outra.png"}, banco)
        with closing(sqlite3.connect(banco)) as con:
            self.assertEqual(con.execute("SELECT image FROM speaker").fetchone()[0], "foto.png")

    def test_lista_vazia_nao_apaga_banco(self):
        banco = self.base / "event.db"
        main.salvar_no_banco(self.extrair(AMOSTRA), {1: "foto.png"}, banco)
        with self.assertRaises(main.ErroProjeto):
            main.salvar_no_banco([], {}, banco)
        with closing(sqlite3.connect(banco)) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM speaker").fetchone()[0], 1)

    def test_imagens_com_mesmo_nome_nao_se_sobrescrevem(self):
        dados = self.extrair(cartao(1, "/a/foto.png") + modal(1) + cartao(2, "/b/foto.png") + modal(2))
        with patch("main.requisitar", side_effect=[(PNG, "image/png", None), (PNG + b"2", "image/png", None)]):
            nomes = main.baixar_imagens(dados, self.base / "download")
        self.assertNotEqual(nomes[1], nomes[2])
        self.assertTrue(all((self.base / "download" / n).stat().st_size > 0 for n in nomes.values()))

    def test_falha_de_download_preserva_banco_e_imagens(self):
        dados = self.extrair(cartao(1) + modal(1) + cartao(2) + modal(2))
        banco = self.base / "event.db"
        main.salvar_no_banco(dados, {1: "antiga.png", 2: "antiga.png"}, banco)
        pasta = self.base / "download"
        pasta.mkdir()
        (pasta / "antiga.png").write_bytes(PNG)
        anterior = banco.read_bytes()
        with patch("main.baixar_html"), patch("main.extrair_dados", return_value=dados), \
             patch("main.requisitar", side_effect=[(PNG, "image/png", None), main.ErroProjeto("sem conexão")]):
            with self.assertRaises(main.ErroProjeto):
                main.executar(base=self.base)
        self.assertEqual(banco.read_bytes(), anterior)
        self.assertEqual(list(pasta.iterdir()), [pasta / "antiga.png"])

    def test_html_disfarcado_de_imagem_e_rejeitado(self):
        with patch("main.requisitar", return_value=(b"<html>erro</html>", "image/png", None)):
            with self.assertRaises(main.ErroProjeto):
                main.baixar_imagens(self.extrair(AMOSTRA), self.base / "download")

    def test_download_html_utf8_e_resposta_invalida(self):
        destino = self.base / "pagina_evento.txt"
        with patch("main.requisitar", return_value=("<html>á</html>".encode("latin-1"), "text/html", "latin-1")):
            main.baixar_html(destino)
        self.assertEqual(destino.read_text(encoding="utf-8"), "<html>á</html>")
        with patch("main.requisitar", return_value=(b"{}", "application/json", None)):
            with self.assertRaises(main.ErroProjeto):
                main.baixar_html(destino)
        self.assertEqual(destino.read_text(encoding="utf-8"), "<html>á</html>")

    def test_falha_de_extracao_preserva_banco(self):
        dados = self.extrair(AMOSTRA)
        banco = self.base / "event.db"
        main.salvar_no_banco(dados, {1: "foto.png"}, banco)
        anterior = banco.read_bytes()
        (self.base / "pagina_evento.txt").write_text(cartao(1), encoding="utf-8")
        with self.assertRaises(main.ErroProjeto):
            main.executar(usar_txt=True, base=self.base)
        self.assertEqual(banco.read_bytes(), anterior)

    def test_rede_indisponivel_timeout_e_download_interrompido(self):
        for erro in [URLError("sem conexão"), TimeoutError("tempo esgotado"), IncompleteRead(b"abc", 10)]:
            with self.subTest(erro=erro), patch("main.urlopen", side_effect=erro):
                with self.assertRaises(main.ErroProjeto):
                    main.requisitar(main.URL_EVENTO)

    def test_requisicao_valida_tamanho_status_e_conteudo(self):
        for status, conteudo, tamanho in [(200, b"", "0"), (200, b"abc", "10"), (204, b"abc", "3")]:
            with self.subTest(status=status, conteudo=conteudo):
                resposta = MagicMock()
                resposta.status = status
                resposta.read.return_value = conteudo
                resposta.headers = Message()
                resposta.headers["Content-Length"] = tamanho
                resposta.__enter__.return_value = resposta
                with patch("main.urlopen", return_value=resposta) as abrir:
                    with self.assertRaises(main.ErroProjeto):
                        main.requisitar(main.URL_EVENTO)
                    self.assertEqual(abrir.call_args.kwargs["timeout"], 30)

    def test_url_de_imagem_nao_http_e_rejeitada(self):
        with self.assertRaisesRegex(main.ErroProjeto, "imagem com URL inválida"):
            self.extrair(cartao(1, "file:///arquivo.png") + modal(1))


if __name__ == "__main__":
    unittest.main()
