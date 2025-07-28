import sys
import io
from contextlib import redirect_stdout

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QWidget, QInputDialog,
    QVBoxLayout, QHBoxLayout, QPushButton, QPlainTextEdit,
    QTextBrowser, QLabel, QSplitter, QStyle, QSizePolicy, QLineEdit
)
from PySide6.QtCore import Qt, QObject, QDir
from PySide6.QtGui import QValidator, QAction
from lxml import etree
from .llm import LLMClient, store_api_key, delete_api_key
from .history import HistoryManager
from .xml_utils import parse_xml, apply_xpath, pretty_print

class XPathFinderApp:
    def __init__(self, xml_file=None):
        self.qt_app = QApplication(sys.argv)
        self.window = MainWindow(xml_file)

    def run(self):
        self.window.show()
        sys.exit(self.qt_app.exec())

class MainWindow(QMainWindow):
    class NameSpaceValidator(QValidator):
        def __init__(self, parent: QObject = None):
            assert isinstance(parent, MainWindow)
            self.mainWindow: MainWindow = parent
            super().__init__(parent)

        def validate(self, v: str, pos: int):
            if v != self.mainWindow.ns and v in self.mainWindow.nsmap:
                return QValidator.State.Invalid, v, pos
            else:
                self.mainWindow.nsmap[v] = self.mainWindow.nsmap.get(self.mainWindow.ns)
                if v != self.mainWindow.ns:
                    del self.mainWindow.nsmap[self.mainWindow.ns]
                    self.mainWindow.ns = v
                return QValidator.State.Acceptable, v, pos

    def __init__(self, xml_file=None):
        super().__init__()
        self.first_render = True
        self.setWindowTitle("XPathfinder")

        # XML document state
        self.doc = None
        self.nsmap = None
        self.ns = None
        self.xpath_expr = ''
        self.xpath_result = []

        # History managers for undo/redo
        self.llm_history = HistoryManager()
        self.xpath_history = HistoryManager()
        self.code_history = HistoryManager()

        # LLM integration
        self.llm = LLMClient()

        self._setup_ui()
        if xml_file:
            self.load_xml(xml_file)

    def showEvent(self, event):
        super().showEvent(event)
        if self.first_render:
            self.first_render = False
            self._resize_splitter()

    def _resize_splitter(self):
        total_h = self.height()
        top_h = int(total_h * 0.15)  # 15% for LLM+XPath
        bot_h = int(total_h * 0.30)  # 30% for history
        mid_h = total_h - top_h - bot_h
        self.splitter.setSizes([top_h, mid_h, bot_h])

    def _setup_ui(self):
        self.splitter = QSplitter(Qt.Orientation.Vertical)

        # Top panel: LLM + XPath, no resizing
        top_panel = QWidget()
        top_layout = QHBoxLayout(top_panel)

        # LLM box (#1)
        llm_box = QVBoxLayout()
        # LLM label
        llm_box.addWidget(QLabel("LLM Query"))
        # LLM controls
        llm_ctrl = QHBoxLayout()
        llm_ctrl.setContentsMargins(0, 0, 0, 0)
        llm_ctrl.setSpacing(2)
        llm_ctrl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.llm_run = QPushButton()
        self.llm_run.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.llm_undo = QPushButton()
        self.llm_undo.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
        self.llm_redo = QPushButton()
        self.llm_redo.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward))
        self.llm_clear = QPushButton()
        self.llm_clear.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogDiscardButton))
        for btn in (self.llm_run, self.llm_undo, self.llm_redo, self.llm_clear):
            btn.setFixedSize(32,32)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.llm_run.clicked.connect(self._run_llm)
        self.llm_undo.clicked.connect(self._undo_llm)
        self.llm_redo.clicked.connect(self._redo_llm)
        self.llm_clear.clicked.connect(self._clear_llm)
        llm_ctrl.addWidget(self.llm_run)
        llm_ctrl.addWidget(self.llm_undo)
        llm_ctrl.addWidget(self.llm_redo)
        llm_ctrl.addWidget(self.llm_clear)
        llm_box.addLayout(llm_ctrl)
        # LLM query field
        self.llm_query = QPlainTextEdit()
        self.llm_query.setPlaceholderText("Enter LLM query here...")
        llm_box.addWidget(self.llm_query)

        top_layout.addLayout(llm_box)

        # XPath box (#2)
        xpath_box = QVBoxLayout()
        # XPath label
        xpath_box.addWidget(QLabel("XPath Expression"))
        # XPath controls
        xpath_ctrl = QHBoxLayout()
        xpath_ctrl.setContentsMargins(0, 0, 0, 0)
        xpath_ctrl.setSpacing(2)
        xpath_ctrl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.xpath_run = QPushButton()
        self.xpath_run.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.xpath_undo = QPushButton()
        self.xpath_undo.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
        self.xpath_redo = QPushButton()
        self.xpath_redo.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward))
        self.xpath_clear = QPushButton()
        self.xpath_clear.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogDiscardButton))
        for btn in (self.xpath_run, self.xpath_undo, self.xpath_redo, self.xpath_clear):
            btn.setFixedSize(32,32)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.xpath_run.clicked.connect(self._run_xpath)
        self.xpath_undo.clicked.connect(self._undo_xpath)
        self.xpath_redo.clicked.connect(self._redo_xpath)
        self.xpath_clear.clicked.connect(self._clear_xpath)
        xpath_ctrl.addWidget(self.xpath_run)
        xpath_ctrl.addWidget(self.xpath_undo)
        xpath_ctrl.addWidget(self.xpath_redo)
        xpath_ctrl.addWidget(self.xpath_clear)
        self.xpath_ns_edit = QLineEdit()
        self.xpath_ns_edit.setPlaceholderText("ns")
        self.xpath_ns_edit.setFixedWidth(100)
        self.xpath_ns_edit.setValidator(self.NameSpaceValidator(self))
        xpath_ctrl.addWidget(self.xpath_ns_edit)
        self.xpath_ns_edit.hide()
        xpath_box.addLayout(xpath_ctrl)
        # XPath query field
        self.xpath_query = QPlainTextEdit()
        self.xpath_query.setPlaceholderText("Enter XPath expression here...")
        xpath_box.addWidget(self.xpath_query)

        top_layout.addLayout(xpath_box)

        self.splitter.addWidget(top_panel)

        # Middle panel: Code + Selection, splitter for resizing
        mid_split = QSplitter(Qt.Orientation.Horizontal)

        # Code box (#3)
        code_widget = QWidget()
        code_box = QVBoxLayout(code_widget)
        # Code label
        code_box.addWidget(QLabel("Python Code"))
        # Code controls
        code_ctrl = QHBoxLayout()
        code_ctrl.setContentsMargins(0, 0, 0, 0)
        code_ctrl.setSpacing(2)
        code_ctrl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.code_run = QPushButton()
        self.code_run.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.code_undo = QPushButton()
        self.code_undo.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
        self.code_redo = QPushButton()
        self.code_redo.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward))
        self.code_clear = QPushButton()
        self.code_clear.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogDiscardButton))
        for btn in (self.code_run, self.code_undo, self.code_redo, self.code_clear):
            btn.setFixedSize(32,32)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.code_run.clicked.connect(self._run_code)
        self.code_undo.clicked.connect(self._undo_code)
        self.code_redo.clicked.connect(self._redo_code)
        self.code_clear.clicked.connect(self._clear_code)
        code_ctrl.addWidget(self.code_run)
        code_ctrl.addWidget(self.code_undo)
        code_ctrl.addWidget(self.code_redo)
        code_ctrl.addWidget(self.code_clear)
        code_box.addLayout(code_ctrl)
        # Code editor
        self.code_editor = QPlainTextEdit()
        self.code_editor.setPlaceholderText("Write Python code here...\n`doc` is the XML document,\n`xpath_expr` is the last XPath,\n`xpath_result` is the last XPath result.")
        code_box.addWidget(self.code_editor)
        mid_split.addWidget(code_widget)

        # Selection box (#4)
        sel_widget = QWidget()
        sel_box = QVBoxLayout(sel_widget)
        # Selection label
        sel_box.addWidget(QLabel("Selection Viewer"))
        # Selection viewer
        self.selection_view = QTextBrowser()
        self.selection_view.setPlaceholderText("XPath selection output...")
        sel_box.addWidget(self.selection_view)
        mid_split.addWidget(sel_widget)

        self.splitter.addWidget(mid_split)

        # Bottom panel: Output history (#5)
        hist_widget = QWidget()
        hist_box = QVBoxLayout(hist_widget)
        # History label
        hist_box.addWidget(QLabel("Output History"))
        # History controls above the view
        hist_ctrl = QHBoxLayout()
        hist_ctrl.setContentsMargins(0, 0, 0, 0)
        hist_ctrl.setSpacing(2)
        hist_ctrl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.history_clear = QPushButton()
        self.history_clear.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogDiscardButton))
        self.history_clear.setFixedSize(32,32)
        self.history_clear.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.history_clear.clicked.connect(self._clear_history)
        hist_ctrl.addWidget(self.history_clear)
        hist_box.addLayout(hist_ctrl)
        self.history_view = QTextBrowser()
        hist_box.addWidget(self.history_view)
        self.splitter.addWidget(hist_widget)

        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setStretchFactor(2, 1)
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(2, False)

        self.splitter.setStyleSheet("""
        QSplitter::handle:vertical {
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #f0f0f0, stop:1 #c0c0c0
            );
            margin: 2px 2px;           
        }
        QSplitter::handle:horizontal {
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #f0f0f0, stop:1 #c0c0c0
            );
            margin: 2px 2px;           
        }
        """)

        self.setCentralWidget(self.splitter)

        # File menu
        file_menu = self.menuBar().addMenu("File")
        open_act = file_menu.addAction("Open...")
        open_act.triggered.connect(self._open_file)
        save_act = file_menu.addAction("Save As...")
        save_act.triggered.connect(self._save_file)

        file_menu = self.menuBar().addMenu("LLM (OpenAI)")
        if self.llm.api_key:
            if self.llm.api_key_env:
                self.key_status_act = QAction("API Key: Environment", self)
            else:
                self.key_status_act = QAction("API Key: From Store", self)
        else:
            self.key_status_act = QAction("API Key: None", self)
        file_menu.addAction(self.key_status_act)
        set_key_act = file_menu.addAction("Set API key...")
        set_key_act.triggered.connect(self._set_api_key)
        unset_key_act = file_menu.addAction("Unset API key")
        unset_key_act.triggered.connect(self._unset_api_key)

    def _set_api_key(self):
        text, ok = QInputDialog.getText(self, "Enter your API key",
                                        "OpenAI API Key:", QLineEdit.EchoMode.Normal,
                                        "")
        if ok and text:
            store_api_key('OpenAI API Key', text)
            self.llm.api_key = text
            self.llm.api_key_env = False
            self.key_status_act.setText("API Key: From Store")

    def _unset_api_key(self):
        delete_api_key('OpenAI API Key')
        self.llm.api_key = None
        self.llm.api_key_env = False
        self.key_status_act.setText("API Key: None")

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open XML File", filter="XML Files (*.xml);;All Files (*)")
        if path:
            self.load_xml(path)

    def _save_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save XML File", filter="XML Files (*.xml);;All Files (*)")
        if path and self.doc:
            with open(path, 'wb') as f:
                f.write(etree.tostring(self.doc, pretty_print=True, xml_declaration=True, encoding='UTF-8'))
            self.history_view.append(f"Saved XML to: {path}")

    def load_xml(self, path):
        self.doc, self.nsmap, self.ns = parse_xml(path)
        if self.ns is not None:
            self.xpath_ns_edit.setText(self.ns)
            self.xpath_ns_edit.show()
        else:
            self.xpath_ns_edit.hide()
        self.history_view.append(f"Loaded XML from: {path}")

    # Undo/Redo/Clear handlers
    def _undo_llm(self):
        cur = self.llm_query.toPlainText()
        if self.llm_history.current() != cur:
            self.llm_history.add(cur)
        prev = self.llm_history.undo()
        if prev is not None:
            self.llm_query.setPlainText(prev)

    def _redo_llm(self):
        nxt = self.llm_history.redo()
        if nxt is not None:
            self.llm_query.setPlainText(nxt)

    def _clear_llm(self):
        self.llm_query.clear()

    def _undo_xpath(self):
        cur = self.xpath_query.toPlainText()
        if self.xpath_history.current() != cur:
            self.xpath_history.add(cur)
        prev = self.xpath_history.undo()
        if prev is not None:
            self.xpath_query.setPlainText(prev)

    def _redo_xpath(self):
        nxt = self.xpath_history.redo()
        if nxt is not None:
            self.xpath_query.setPlainText(nxt)

    def _clear_xpath(self):
        self.xpath_query.clear()

    def _undo_code(self):
        cur = self.code_editor.toPlainText()
        if self.code_history.current() != cur:
            self.code_history.add(cur)
        prev = self.code_history.undo()
        if prev is not None:
            self.code_editor.setPlainText(prev)

    def _redo_code(self):
        nxt = self.code_history.redo()
        if nxt is not None:
            self.code_editor.setPlainText(nxt)

    def _clear_code(self):
        self.code_editor.clear()

    def _clear_history(self):
        self.history_view.clear()

    def _run_xpath(self):
        expr = self.xpath_query.toPlainText().strip()
        if not expr or not self.doc:
            return
        self.xpath_history.add(expr)
        self.xpath_expr = expr
        self.xpath_result = apply_xpath(self.doc, expr, self.nsmap)
        self.selection_view.setPlainText("\n".join(pretty_print(node) for node in self.xpath_result))
        self.history_view.append(f"XPath executed: {expr}")

    def _run_code(self):
        code = self.code_editor.toPlainText()
        if not code or not self.doc:
            return
        self.code_history.add(code)
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                exec(f'from lxml import etree\n\n{code}',
                     {'doc': self.doc,
                      'xpath_expr': self.xpath_expr,
                      'xpath_result': self.xpath_result,
                      'nsmap': self.nsmap
                      })
            output = buf.getvalue()
            if output:
                self.history_view.append(output)
            self.history_view.append("Code executed successfully.")
        except Exception as e:
            self.history_view.append(f"Code execution error: {e}")

    def _run_llm(self):
        prompt = self.llm_query.toPlainText().strip()
        if not prompt:
            return
        self.llm_history.add(prompt)
        self.history_view.append(f"LLM prompt: {prompt}")
        xml_text = etree.tostring(self.doc, pretty_print=False, encoding='unicode') if self.doc else ''
        response = self.llm.query(prompt, {'xml': xml_text, 'xpath': self.xpath_expr, 'code': self.code_editor.toPlainText()}, self.ns)
        if 'xpath' in response:
            self.xpath_query.setPlainText(response['xpath'])
            self._run_xpath()
        if 'code' in response:
            self.code_editor.setPlainText(response['code'])
            self._run_code()
        if 'text' in response:
            self.history_view.append(response['text'])
