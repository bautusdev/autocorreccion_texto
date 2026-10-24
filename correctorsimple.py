#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Notas rápidas — editor con autocorrección en tiempo real (español).

PyQt5 + LanguageTool. Interfaz moderna estilo «Notas rápidas» (sticky notes):
tarjetas de colores pastel, barra lateral oscura con buscador, subrayado
ondulado de errores y corrección palabra a palabra mientras escribes.
"""

import json
import os
import sys

from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QTextCharFormat, QTextCursor
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPushButton, QShortcut, QSplitter, QTextEdit, QToolButton, QVBoxLayout,
    QWidget,
)

import language_tool_python

ARCHIVO_NOTAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notas.json")

ROL_DATOS = Qt.UserRole

# Colores estilo "sticky notes": (nombre, fondo, borde)
COLORES_NOTA = [
    ("Amarillo",  "#fff4ad", "#e3d27d"),
    ("Rosa",      "#ffd9e2", "#ecb2c2"),
    ("Verde",     "#d9f4d2", "#aedaa2"),
    ("Azul",      "#dcebff", "#aecbef"),
    ("Lila",      "#e9defc", "#c6b1ea"),
    ("Melocotón", "#ffe6c7", "#eec493"),
]

SEPARADORES = set(" \n\t\r.,;:!?¡¿()[]{}\"'«»—–-…/")

QSS = """
* { font-family: 'Segoe UI', 'Noto Sans', 'DejaVu Sans', sans-serif; }
QMainWindow { background: #eceff3; }
QSplitter::handle { background: #dfe4ea; }

QWidget#barraLateral { background: #212b36; }
QLabel#logoApp   { color: #f8fafc; font-size: 19px; font-weight: 700; padding: 4px 2px 0 2px; }
QLabel#subLogo   { color: #8b98a9; font-size: 11px; padding-bottom: 6px; }

QLineEdit#buscador {
    background: #2b3644; color: #e8edf4; border: 1px solid #39455a;
    border-radius: 9px; padding: 8px 12px; font-size: 13px;
}
QLineEdit#buscador:focus { border: 1px solid #4f8ef7; }

QListWidget#listaNotas { background: transparent; border: none; outline: none; font-size: 13px; }
QListWidget#listaNotas::item {
    background: #2b3644; color: #dbe3ee; border-radius: 10px;
    padding: 9px 11px; margin: 3px 8px;
}
QListWidget#listaNotas::item:hover:!selected { background: #32404f; }
QListWidget#listaNotas::item:selected { background: #4f8ef7; color: #ffffff; }
QListWidget#listaNotas QScrollBar:vertical { background: transparent; width: 8px; }
QListWidget#listaNotas QScrollBar::handle:vertical { background: #4a586c; border-radius: 4px; min-height: 30px; }
QListWidget#listaNotas QScrollBar::add-line:vertical,
QListWidget#listaNotas QScrollBar::sub-line:vertical { height: 0px; }

QPushButton#btnNueva {
    background: #4f8ef7; color: white; border: none; border-radius: 10px;
    padding: 11px; font-size: 14px; font-weight: 600;
}
QPushButton#btnNueva:hover  { background: #3f79e0; }
QPushButton#btnNueva:pressed { background: #3468c4; }

QWidget#panelNota { background: #eceff3; }

QLineEdit#tituloNota {
    background: transparent; border: none; font-size: 21px; font-weight: 700;
    color: #26303b; padding: 2px 2px 6px 2px;
}

QTextEdit#editorNota {
    background: transparent; border: none; font-size: 15px; color: #2a3542;
    selection-background-color: rgba(15, 23, 42, 0.18);
}
QTextEdit#editorNota QScrollBar:vertical { background: transparent; width: 9px; margin: 4px 2px; }
QTextEdit#editorNota QScrollBar::handle:vertical { background: rgba(15,23,42,0.28); border-radius: 4px; min-height: 34px; }
QTextEdit#editorNota QScrollBar::handle:vertical:hover { background: rgba(15,23,42,0.42); }
QTextEdit#editorNota QScrollBar::add-line:vertical,
QTextEdit#editorNota QScrollBar::sub-line:vertical { height: 0px; }

QToolButton#btnTarjeta {
    background: rgba(15,23,42,0.07); color: #26303b; border: none;
    border-radius: 8px; padding: 6px 10px; font-size: 14px;
}
QToolButton#btnTarjeta:hover { background: rgba(15,23,42,0.16); }
QToolButton#btnBorrar {
    background: rgba(15,23,42,0.07); color: #26303b; border: none;
    border-radius: 8px; padding: 6px 10px; font-size: 14px;
}
QToolButton#btnBorrar:hover { background: #e5484d; color: white; }

QCheckBox { color: #3f4b5c; font-size: 13px; spacing: 7px; }
QCheckBox::indicator {
    width: 15px; height: 15px; border-radius: 4px;
    border: 2px solid #9aa7b8; background: white;
}
QCheckBox::indicator:checked { background: #4f8ef7; border-color: #4f8ef7; }

QPushButton#btnCorregir {
    background: #17222e; color: white; border: none; border-radius: 9px;
    padding: 8px 16px; font-size: 13px; font-weight: 600;
}
QPushButton#btnCorregir:hover { background: #0d151d; }

QLabel#estado   { color: #5a6878; font-size: 12px; }
QLabel#contador { color: #8794a5; font-size: 12px; }
"""


# ---------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------
def _texto_item(titulo, contenido):
    """Texto de dos líneas para la lista lateral: título + extracto."""
    snippet = " ".join((contenido or "").split())[:60]
    return f"{titulo}\n{snippet if snippet else '…'}"


def _capitalizar(original, sugerencia):
    """Respeta la capitalización de la palabra escrita por el usuario."""
    if original.isupper() and len(original) > 1:
        return sugerencia.upper()
    if original[:1].isupper():
        return sugerencia[:1].upper() + sugerencia[1:]
    return sugerencia


def _sugerencia_palabra(palabra, matches):
    """Devuelve una corrección ortográfica simple para la palabra, o None."""
    for m in matches:
        rid = getattr(m, "rule_id", "") or ""
        tipo = getattr(m, "rule_issue_type", "") or ""
        if tipo != "misspelling" and "MORFOLOGIK" not in rid:
            continue  # solo errores ortográficos al corregir palabra suelta
        reps = getattr(m, "replacements", [])
        if not reps:
            continue
        sug = reps[0].strip()
        if not sug or " " in sug:
            continue
        if sug.lower() == palabra.lower():
            continue
        return sug
    return None


# ---------------------------------------------------------------------
# Hilos de trabajo (LanguageTool sin congelar la interfaz)
# ---------------------------------------------------------------------
class CargarCorrector(QThread):
    listo = pyqtSignal(object)
    fallo = pyqtSignal(str)

    def run(self):
        try:
            self.listo.emit(language_tool_python.LanguageTool("es"))
        except Exception as exc:  # noqa: BLE001
            self.fallo.emit(str(exc))


class RevisarTexto(QThread):
    resultado = pyqtSignal(object, str)  # matches, texto_original
    fallo = pyqtSignal(str)

    def __init__(self, tool, texto, parent=None):
        super().__init__(parent)
        self.tool = tool
        self.texto = texto

    def run(self):
        try:
            self.resultado.emit(self.tool.check(self.texto), self.texto)
        except Exception as exc:  # noqa: BLE001
            self.fallo.emit(str(exc))


class RevisarPalabra(QThread):
    resultado = pyqtSignal(int, int, int, str, object)  # token, ini, fin, palabra, matches

    def __init__(self, tool, palabra, token, ini, fin, parent=None):
        super().__init__(parent)
        self.tool = tool
        self.palabra = palabra
        self.token = token
        self.ini = ini
        self.fin = fin

    def run(self):
        try:
            matches = self.tool.check(self.palabra)
        except Exception:  # noqa: BLE001
            matches = []
        self.resultado.emit(self.token, self.ini, self.fin, self.palabra, matches)


# ---------------------------------------------------------------------
# Editor con subrayado ondulado de errores
# ---------------------------------------------------------------------
class EditorNota(QTextEdit):
    def __init__(self):
        super().__init__()
        self.matches = []
        self.mostrar_errores = True
        self.setAcceptRichText(False)
        self.setPlaceholderText("Escribe tu nota aquí… se irá autocorrigiendo sola ✨")

    def resaltar_errores(self, matches):
        self.matches = matches
        self.blockSignals(True)
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        limpio = QTextCharFormat()
        cursor.select(QTextCursor.Document)
        cursor.setCharFormat(limpio)
        cursor.clearSelection()
        if self.mostrar_errores:
            texto = self.toPlainText()
            fmt = QTextCharFormat()
            fmt.setUnderlineColor(QColor("#e5484d"))
            fmt.setUnderlineStyle(QTextCharFormat.SpellCheckUnderline)
            for m in matches:
                ini = m.offset
                fin = min(m.offset + m.error_length, len(texto))
                if ini >= fin:
                    continue
                c = QTextCursor(self.document())
                c.setPosition(ini)
                c.setPosition(fin, QTextCursor.KeepAnchor)
                c.setCharFormat(fmt)
        cursor.endEditBlock()
        self.blockSignals(False)


# ---------------------------------------------------------------------
# Ventana principal
# ---------------------------------------------------------------------
class GestorNotas(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Notas rápidas · Autocorrección en tiempo real")
        self.resize(1100, 720)
        self.setMinimumSize(900, 600)

        self.tool = None
        self.worker_texto = None
        self._hilos = []
        self._token_palabra = 0
        self._cache_palabras = {}      # palabra.lower() -> sugerencia | None
        self._modo_forzado = False

        self._construir_ui()
        self._aplicar_color(0)
        self._cargar_notas()

        # Debounce: revisión completa tras una breve pausa al escribir
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(700)
        self.timer.timeout.connect(self.corregir_texto)

        # Cargar LanguageTool en segundo plano (la primera vez tarda un poco)
        self.estado.setText("⏳ Cargando corrector ortográfico…")
        cargador = CargarCorrector(self)
        cargador.listo.connect(self._corrector_listo)
        cargador.fallo.connect(self._corrector_fallo)
        self._lanzar(cargador)

        QShortcut("Ctrl+N", self, activated=self.nueva_nota)

    # ------------------------------------------------------------ UI
    def _construir_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        raiz = QHBoxLayout(central)
        raiz.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)
        raiz.addWidget(splitter)

        # ---------------- Barra lateral oscura ----------------
        lat = QWidget()
        lat.setObjectName("barraLateral")
        v_lat = QVBoxLayout(lat)
        v_lat.setContentsMargins(14, 16, 14, 14)
        v_lat.setSpacing(10)

        v_lat.addWidget(QLabel("📝 Notas rápidas", objectName="logoApp"))
        v_lat.addWidget(QLabel("con autocorrección en español", objectName="subLogo"))

        self.buscador = QLineEdit(objectName="buscador")
        self.buscador.setPlaceholderText("🔍  Buscar notas…")
        self.buscador.setClearButtonEnabled(True)
        self.buscador.textChanged.connect(self._filtrar_notas)
        v_lat.addWidget(self.buscador)

        self.lista = QListWidget(objectName="listaNotas")
        self.lista.currentItemChanged.connect(self._seleccionar_nota)
        v_lat.addWidget(self.lista)

        btn_nueva = QPushButton("＋  Nueva nota", objectName="btnNueva")
        btn_nueva.setCursor(Qt.PointingHandCursor)
        btn_nueva.clicked.connect(self.nueva_nota)
        v_lat.addWidget(btn_nueva)

        # ---------------- Panel de la nota (sticky note) ----------------
        panel = QWidget()
        panel.setObjectName("panelNota")
        v_panel = QVBoxLayout(panel)
        v_panel.setContentsMargins(26, 22, 26, 18)
        v_panel.setSpacing(12)

        self.tarjeta = QFrame(objectName="tarjetaNota")
        sombra = QGraphicsDropShadowEffect(self)
        sombra.setBlurRadius(28)
        sombra.setXOffset(0)
        sombra.setYOffset(8)
        sombra.setColor(QColor(15, 23, 42, 45))
        self.tarjeta.setGraphicsEffect(sombra)

        v_card = QVBoxLayout(self.tarjeta)
        v_card.setContentsMargins(18, 14, 18, 16)
        v_card.setSpacing(8)

        # Barra superior: paleta de colores + acciones
        fila_top = QHBoxLayout()
        fila_top.setSpacing(8)
        self.botones_color = []
        for i, (nombre, base, borde) in enumerate(COLORES_NOTA):
            b = QToolButton()
            b.setFixedSize(22, 22)
            b.setToolTip(nombre)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _chk=False, idx=i: self._cambiar_color(idx))
            self.botones_color.append(b)
            fila_top.addWidget(b)
        fila_top.addStretch()

        btn_copiar = QToolButton(objectName="btnTarjeta")
        btn_copiar.setText("📋 Copiar")
        btn_copiar.setCursor(Qt.PointingHandCursor)
        btn_copiar.setToolTip("Copiar el contenido de la nota")
        btn_copiar.clicked.connect(self._copiar_nota)
        fila_top.addWidget(btn_copiar)

        btn_borrar = QToolButton(objectName="btnBorrar")
        btn_borrar.setText("🗑 Eliminar")
        btn_borrar.setCursor(Qt.PointingHandCursor)
        btn_borrar.setToolTip("Eliminar esta nota")
        btn_borrar.clicked.connect(self.eliminar_nota)
        fila_top.addWidget(btn_borrar)
        v_card.addLayout(fila_top)

        self.titulo = QLineEdit(objectName="tituloNota")
        self.titulo.setPlaceholderText("Título…")
        self.titulo.textChanged.connect(self._guardar_actual)
        v_card.addWidget(self.titulo)

        self.editor = EditorNota()
        self.editor.setObjectName("editorNota")
        self.editor.textChanged.connect(self._texto_cambiado)
        v_card.addWidget(self.editor)

        v_panel.addWidget(self.tarjeta)

        # Franja inferior: opciones + estado
        fila_bottom = QHBoxLayout()
        fila_bottom.setSpacing(14)

        self.chk_auto = QCheckBox("⚡ Autocorrección en tiempo real")
        self.chk_auto.setChecked(True)
        self.chk_auto.toggled.connect(self._toggle_auto)
        fila_bottom.addWidget(self.chk_auto)

        self.chk_resaltar = QCheckBox("Subrayar errores")
        self.chk_resaltar.setChecked(True)
        self.chk_resaltar.toggled.connect(self._toggle_resaltado)
        fila_bottom.addWidget(self.chk_resaltar)

        self.btn_corregir = QPushButton("✨ Corregir ahora", objectName="btnCorregir")
        self.btn_corregir.setCursor(Qt.PointingHandCursor)
        self.btn_corregir.clicked.connect(lambda: self.corregir_texto(forzar=True))
        fila_bottom.addWidget(self.btn_corregir)

        fila_bottom.addStretch()

        self.estado = QLabel("Listo", objectName="estado")
        fila_bottom.addWidget(self.estado)

        self.contador = QLabel("0 palabras · 0 caracteres", objectName="contador")
        fila_bottom.addWidget(self.contador)

        v_panel.addLayout(fila_bottom)

        splitter.addWidget(lat)
        splitter.addWidget(panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 840])

    # ------------------------------------------------------------ Hilos
    def _lanzar(self, worker):
        self._hilos.append(worker)
        worker.finished.connect(lambda w=worker: self._hilos.remove(w)
                                if w in self._hilos else None)
        worker.start()

    def _corrector_listo(self, tool):
        self.tool = tool
        self.estado.setText("✔ Corrector listo — escribe y el texto se autocorrige")
        if self.chk_auto.isChecked():
            self.corregir_texto()

    def _corrector_fallo(self, msg):
        self.estado.setText("❌ No se pudo iniciar LanguageTool")
        self.chk_auto.setEnabled(False)
        self.chk_resaltar.setEnabled(False)
        self.btn_corregir.setEnabled(False)
        QMessageBox.critical(
            self, "Corrector no disponible",
            "No se pudo iniciar LanguageTool.\n\n" + msg
        )

    # ------------------------------------------------------------ Notas
    def _nuevo_item(self, titulo, contenido, color):
        it = QListWidgetItem(_texto_item(titulo, contenido))
        it.setData(ROL_DATOS, {"titulo": titulo, "contenido": contenido, "color": color})
        return it

    def nueva_nota(self):
        color = self.lista.count() % len(COLORES_NOTA)
        it = self._nuevo_item("Nueva nota", "", color)
        self.lista.insertItem(0, it)
        self.lista.setCurrentItem(it)
        self.titulo.setFocus()
        self.titulo.selectAll()
        self._guardar_notas()

    def eliminar_nota(self):
        it = self.lista.currentItem()
        if it is None:
            return
        datos = it.data(ROL_DATOS) or {}
        resp = QMessageBox.question(
            self, "Eliminar nota",
            f"¿Eliminar «{datos.get('titulo', 'Nota')}»?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return
        self.lista.takeItem(self.lista.row(it))
        if self.lista.count() == 0:
            self.nueva_nota()
        else:
            self._guardar_notas()

    def _seleccionar_nota(self, actual, _anterior):
        if actual is None:
            return
        datos = actual.data(ROL_DATOS) or {}
        self.titulo.blockSignals(True)
        self.editor.blockSignals(True)
        self.titulo.setText(datos.get("titulo", ""))
        self.editor.setPlainText(datos.get("contenido", ""))
        self.editor.document().clearUndoRedoStacks()
        self.titulo.blockSignals(False)
        self.editor.blockSignals(False)
        self.editor.resaltar_errores([])
        self._aplicar_color(datos.get("color", 0))
        self._actualizar_contador()

    def _guardar_actual(self):
        it = self.lista.currentItem()
        if it is None:
            return
        datos = it.data(ROL_DATOS) or {}
        datos["titulo"] = self.titulo.text().strip() or "Nota sin título"
        datos["contenido"] = self.editor.toPlainText()
        it.setData(ROL_DATOS, datos)
        it.setText(_texto_item(datos["titulo"], datos["contenido"]))
        self._guardar_notas()

    def _guardar_notas(self):
        notas = []
        for i in range(self.lista.count()):
            d = self.lista.item(i).data(ROL_DATOS) or {}
            notas.append({
                "titulo": d.get("titulo", "Nota sin título"),
                "contenido": d.get("contenido", ""),
                "color": d.get("color", 0),
            })
        try:
            with open(ARCHIVO_NOTAS, "w", encoding="utf-8") as f:
                json.dump(notas, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _cargar_notas(self):
        notas = []
        if os.path.exists(ARCHIVO_NOTAS):
            try:
                with open(ARCHIVO_NOTAS, "r", encoding="utf-8") as f:
                    notas = json.load(f)
            except (OSError, json.JSONDecodeError):
                notas = []
        for n in notas:
            self.lista.addItem(self._nuevo_item(
                n.get("titulo", "Nota"),
                n.get("contenido", ""),
                n.get("color", 0),
            ))
        if self.lista.count():
            self.lista.setCurrentRow(0)
        else:
            self._nota_demo()
        self._guardar_notas()

    def _nota_demo(self):
        it = self._nuevo_item(
            "👋 Bienvenido",
            "Mi amigo de sía que la comerzialización de estas notas era facil.\n"
            "La ortografia te acompaña en tiempo real: escribe y observa cómo el texto "
            "se corrige solo.\n"
            "Prueba con palabras como «memento», «haver» o «tubieron».",
            0,
        )
        self.lista.addItem(it)
        self.lista.setCurrentItem(it)

    def _filtrar_notas(self, texto):
        q = texto.strip().lower()
        for i in range(self.lista.count()):
            it = self.lista.item(i)
            d = it.data(ROL_DATOS) or {}
            visible = (q in d.get("titulo", "").lower()
                       or q in d.get("contenido", "").lower())
            it.setHidden(not visible)

    # ------------------------------------------------------------ Color
    def _cambiar_color(self, idx):
        it = self.lista.currentItem()
        if it is not None:
            datos = it.data(ROL_DATOS) or {}
            datos["color"] = idx
            it.setData(ROL_DATOS, datos)
            self._guardar_notas()
        self._aplicar_color(idx)

    def _aplicar_color(self, idx):
        idx = max(0, min(idx, len(COLORES_NOTA) - 1))
        _nombre, base, borde = COLORES_NOTA[idx]
        self.tarjeta.setStyleSheet(
            f"QFrame#tarjetaNota {{ background: {base}; border: 1px solid {borde}; "
            f"border-radius: 16px; }}"
        )
        for i, b in enumerate(self.botones_color):
            _n, b_base, b_borde = COLORES_NOTA[i]
            sel = "2px solid #111827" if i == idx else f"2px solid {b_borde}"
            b.setStyleSheet(
                f"QToolButton {{ background: {b_base}; border: {sel}; "
                f"border-radius: 11px; }}"
            )

    def _copiar_nota(self):
        QApplication.clipboard().setText(self.editor.toPlainText())
        self.estado.setText("📋 Nota copiada al portapapeles")

    # ------------------------------------------------------------ Corrección
    def _toggle_auto(self, activo):
        if activo and self.tool is not None:
            self.corregir_texto()

    def _toggle_resaltado(self, activo):
        self.editor.mostrar_errores = activo
        if activo and self.tool is not None:
            self.corregir_texto()
        else:
            self.editor.resaltar_errores([])

    def _texto_cambiado(self):
        self._guardar_actual()
        self._actualizar_contador()
        if self.tool is None:
            return
        if self.chk_auto.isChecked():
            self._iniciar_revision_palabra()   # corrección palabra a palabra
        if self.chk_auto.isChecked() or self.chk_resaltar.isChecked():
            self.timer.start()                  # revisión completa con debounce

    def _actualizar_contador(self):
        texto = self.editor.toPlainText()
        self.contador.setText(f"{len(texto.split())} palabras · {len(texto)} caracteres")

    # ---------------- Corrección instantánea palabra a palabra
    def _palabra_antes_del_cursor(self):
        """Si lo último escrito fue un separador, devuelve (ini, fin, palabra)."""
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            return None
        texto = self.editor.toPlainText()
        pos = cursor.position()
        if pos < 2 or pos > len(texto):
            return None
        if texto[pos - 1] not in SEPARADORES:
            return None
        fin = pos - 1
        ini = fin
        while ini > 0 and texto[ini - 1] not in SEPARADORES:
            ini -= 1
        palabra = texto[ini:fin]
        if len(palabra) < 3 or len(palabra) > 30:
            return None
        if not palabra[0].isalpha() or any(ch.isdigit() for ch in palabra):
            return None
        if palabra.isupper() and len(palabra) > 1:
            return None  # siglas / mayúsculas
        return ini, fin, palabra

    def _iniciar_revision_palabra(self):
        hallazgo = self._palabra_antes_del_cursor()
        if hallazgo is None:
            return
        ini, fin, palabra = hallazgo
        clave = palabra.lower()
        if clave in self._cache_palabras:
            sugerencia = self._cache_palabras[clave]
            if sugerencia:
                self._reemplazar_palabra(
                    ini, fin, palabra, _capitalizar(palabra, sugerencia))
            return
        self._token_palabra += 1
        worker = RevisarPalabra(self.tool, palabra, self._token_palabra, ini, fin)
        worker.resultado.connect(self._palabra_revisada)
        self._lanzar(worker)

    def _palabra_revisada(self, token, ini, fin, palabra, matches):
        if token != self._token_palabra:
            return  # llegó tarde: el usuario siguió escribiendo
        sugerencia = _sugerencia_palabra(palabra, matches)
        if len(self._cache_palabras) > 400:
            self._cache_palabras.clear()
        self._cache_palabras[palabra.lower()] = (
            sugerencia.lower() if sugerencia else None)
        if sugerencia:
            self._reemplazar_palabra(
                ini, fin, palabra, _capitalizar(palabra, sugerencia))

    def _reemplazar_palabra(self, ini, fin, original, nueva):
        texto = self.editor.toPlainText()
        if fin > len(texto) or texto[ini:fin] != original:
            return  # el usuario ya modificó esa zona
        pos = self.editor.textCursor().position()
        delta = len(nueva) - len(original)
        if pos > fin:
            pos += delta
        elif pos > ini:
            pos = ini + len(nueva)

        self.editor.blockSignals(True)
        c = QTextCursor(self.editor.document())
        c.setPosition(ini)
        c.setPosition(fin, QTextCursor.KeepAnchor)
        c.insertText(nueva)  # queda en el historial de deshacer (Ctrl+Z)
        nuevo = self.editor.textCursor()
        nuevo.setPosition(max(0, min(pos, len(self.editor.toPlainText()))))
        self.editor.setTextCursor(nuevo)
        self.editor.blockSignals(False)

        self._guardar_actual()
        self.estado.setText(f"⚡ {original} → {nueva}")

    # ---------------- Revisión completa del texto (debounce / botón)
    def corregir_texto(self, forzar=False):
        texto = self.editor.toPlainText()
        if self.tool is None:
            self.estado.setText("⏳ El corrector aún se está cargando…")
            return
        if not texto.strip():
            self.estado.setText("Nada que corregir")
            return
        if self.worker_texto is not None and self.worker_texto.isRunning():
            return
        self._modo_forzado = forzar or self.chk_auto.isChecked()
        self.estado.setText("🔍 Revisando…")
        worker = RevisarTexto(self.tool, texto)
        self.worker_texto = worker
        worker.resultado.connect(self._aplicar_resultado)
        worker.fallo.connect(
            lambda e: self.estado.setText(f"Error del corrector: {e}"))
        self._lanzar(worker)

    def _aplicar_resultado(self, matches, texto_original):
        if self.editor.toPlainText() != texto_original:
            # El usuario siguió escribiendo durante la revisión: reintentar
            self.estado.setText("⌨️ Escribiendo… se revisará al hacer una pausa")
            if self.chk_auto.isChecked() or self.chk_resaltar.isChecked():
                self.timer.start()
            return

        if not matches:
            self.editor.resaltar_errores([])
            self.estado.setText("✔ Texto sin errores")
            return

        if self._modo_forzado:
            self._aplicar_correcciones(matches, texto_original)
        else:
            self.editor.resaltar_errores(matches)
            self.estado.setText(
                f"⚠ {len(matches)} posible(s) error(es) — pulsa «✨ Corregir ahora»")

    def _aplicar_correcciones(self, matches, texto_original):
        validas = [m for m in matches if getattr(m, "replacements", [])]
        if not validas:
            self.editor.resaltar_errores(matches)
            return

        # Desplazamiento del cursor por correcciones situadas antes de él
        pos = self.editor.textCursor().position()
        delta = 0
        for m in validas:
            if m.offset + m.error_length <= pos:
                delta += len(m.replacements[0]) - m.error_length

        # Aplicar de atrás hacia delante manteniendo un solo paso de deshacer
        doc = self.editor.document()
        self.editor.blockSignals(True)
        bloque = QTextCursor(doc)
        bloque.beginEditBlock()
        for m in reversed(validas):
            c = QTextCursor(doc)
            c.setPosition(m.offset)
            c.setPosition(m.offset + m.error_length, QTextCursor.KeepAnchor)
            c.insertText(m.replacements[0])
        bloque.endEditBlock()
        corregido_len = len(self.editor.toPlainText())
        nuevo = self.editor.textCursor()
        nuevo.setPosition(max(0, min(pos + delta, corregido_len)))
        self.editor.setTextCursor(nuevo)
        self.editor.blockSignals(False)

        self.editor.resaltar_errores([])
        self._guardar_actual()
        self._actualizar_contador()
        self.estado.setText(f"✨ {len(validas)} corrección(es) aplicada(s)")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    ventana = GestorNotas()
    ventana.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
