import re
import sys
import io
from pathlib import Path
from contextlib import redirect_stdout
from typing import Callable

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QWidget, QInputDialog,
    QVBoxLayout, QHBoxLayout, QPushButton, QPlainTextEdit,
    QTextBrowser, QLabel, QSplitter, QStyle, QSizePolicy, QLineEdit
)
from PySide6.QtCore import Qt, QObject
from PySide6.QtGui import QValidator, QAction, QFont, QTextCursor, QKeyEvent, QTextCharFormat, QColor
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


class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None, execute_callback: Callable = None, tab_width: int = 4):
        super().__init__(parent)
        self.execute_callback = execute_callback
        self.tab_width = tab_width

        # Font
        font = QFont("Consolas", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setTabStopDistance(self.tab_width * self.fontMetrics().horizontalAdvance(' '))

        # Format for highlighting brackets
        self.bracket_format = QTextCharFormat()
        self.bracket_format.setBackground(QColor("#d0d0ff"))
        self.bracket_format.setForeground(QColor("black"))

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        modifiers = event.modifiers()

        if key == Qt.Key.Key_Return and modifiers & Qt.KeyboardModifier.ControlModifier:
            if self.execute_callback:
                self.execute_callback()
            return

        elif key == Qt.Key.Key_Return:
            self.handle_auto_indent()
            return

        elif key == Qt.Key.Key_Tab:
            self.insertPlainText(" " * self.tab_width)
            return

        super().keyPressEvent(event)
        self.highlight_matching_brackets()

    def handle_auto_indent(self):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock, QTextCursor.MoveMode.KeepAnchor)
        line = cursor.selectedText()
        indent = re.match(r"\s*", line).group()
        super().keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier))
        self.insertPlainText(indent)

    def highlight_matching_brackets(self):
        cursor = self.textCursor()
        pos = cursor.position()
        doc = self.document()

        pairs = {'(': ')', '{': '}', '[': ']'}
        openers = pairs.keys()
        closers = pairs.values()

        # Clear previous formatting
        cursor.select(QTextCursor.SelectionType.Document)
        default_format = QTextCharFormat()
        cursor.setCharFormat(default_format)
        cursor.clearSelection()

        def highlight(pos1, pos2):
            for p in (pos1, pos2):
                c = QTextCursor(doc)
                c.setPosition(p)
                c.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
                c.setCharFormat(self.bracket_format)

        # Look left for opener
        if pos > 0:
            char = doc.characterAt(pos - 1)
            if char in openers:
                match = self.find_matching_bracket(pos - 1, forward=True)
                if match is not None:
                    highlight(pos - 1, match)
            elif char in closers:
                match = self.find_matching_bracket(pos - 1, forward=False)
                if match is not None:
                    highlight(pos - 1, match)

    def find_matching_bracket(self, pos, forward=True):
        doc = self.document()
        pairs = {'(': ')', '{': '}', '[': ']'}
        inverse = {v: k for k, v in pairs.items()}

        open_char = doc.characterAt(pos)
        match_char = pairs.get(open_char) if forward else inverse.get(open_char)

        if not match_char:
            return None

        stack = 1
        step = 1 if forward else -1
        p = pos + step
        while 0 <= p < doc.characterCount():
            c = doc.characterAt(p)
            if c == open_char:
                stack += 1
            elif c == match_char:
                stack -= 1
                if stack == 0:
                    return p
            p += step

        return None


class CodeViewer(QTextBrowser):
    def __init__(self, parent=None, font_family="Consolas", font_size=11):
        super().__init__(parent)

        self.code_font = QFont(font_family, font_size)
        self.code_font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(self.code_font)

        # Optional: disable word wrap for more code-like behavior
        self.setLineWrapMode(QTextBrowser.LineWrapMode.NoWrap)


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
        self.setWindowTitle('XPathfinder')

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
        self.file_history = HistoryManager(max_size=10)

        # LLM integration
        self.llm = LLMClient()

        self._setup_ui()
        self.path = None
        if xml_file:
            if self.load_xml(xml_file):
                self.path = xml_file
                self.revert_act.setDisabled(False)
                self.save_act.setDisabled(False)
                self.save_as_act.setDisabled(False)

    def showEvent(self, event):
        super().showEvent(event)
        if self.first_render:
            self.first_render = False
            self._resize_splitter()
            self.resize(self.width() * 2, self.height())

    def _resize_splitter(self):
        total_h = self.height()
        top_h = int(total_h * 0.18)  # 18% for LLM+XPath
        bot_h = int(total_h * 0.32)  # 32% for history
        mid_h = total_h - top_h - bot_h
        self.splitter.setSizes([top_h, mid_h, bot_h])

    def _setup_ui(self):
        self.splitter = QSplitter(Qt.Orientation.Vertical)

        # Top panel: LLM + XPath, no resizing
        top_split = QSplitter(Qt.Orientation.Horizontal)

        # LLM box (#1)
        llm_widget = QWidget()
        llm_widget.setContentsMargins(0, 0, -2, 0)
        llm_box = QVBoxLayout(llm_widget)
        # LLM controls
        llm_ctrl = QHBoxLayout()
        llm_ctrl.setContentsMargins(0, 0, 0, 0)
        llm_ctrl.setSpacing(2)
        llm_ctrl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.llm_run = QPushButton()
        self.llm_run.setToolTip('Run - Ctrl+Enter')
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
        # LLM label
        llm_ctrl.addStretch()
        llm_label = QLabel('LLM Query')
        llm_label.setStyleSheet("padding-right: 8px;")
        llm_ctrl.addWidget(llm_label)
        llm_box.addLayout(llm_ctrl)
        # LLM query field
        self.llm_query = CodeEditor(execute_callback=self._run_llm)
        self.llm_query.setPlaceholderText('Enter LLM query here...')
        llm_box.addWidget(self.llm_query)
        top_split.addWidget(llm_widget)

        # XPath box (#2)
        xpath_widget = QWidget()
        xpath_widget.setContentsMargins(0, 0, -2, 0)
        xpath_box = QVBoxLayout(xpath_widget)
        # XPath controls
        xpath_ctrl = QHBoxLayout()
        xpath_ctrl.setContentsMargins(0, 0, 0, 0)
        xpath_ctrl.setSpacing(2)
        xpath_ctrl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.xpath_run = QPushButton()
        self.xpath_run.setToolTip('Run - Ctrl+Enter')
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
        # XPath label
        xpath_ctrl.addStretch()
        xpath_label = QLabel('XPath Query')
        xpath_label.setStyleSheet("padding-right: 8px;")
        xpath_ctrl.addWidget(xpath_label)
        self.xpath_ns_edit = QLineEdit()
        self.xpath_ns_edit.setPlaceholderText('ns')
        self.xpath_ns_edit.setFixedWidth(100)
        self.xpath_ns_edit.setValidator(self.NameSpaceValidator(self))
        xpath_ctrl.addWidget(self.xpath_ns_edit)
        self.xpath_ns_edit.hide()
        xpath_box.addLayout(xpath_ctrl)
        # XPath query field
        self.xpath_query = CodeEditor(execute_callback=self._run_xpath, tab_width=2)
        self.xpath_query.setPlaceholderText('Enter XPath expression here...\n`.` for current node\n`/` for document root')
        xpath_box.addWidget(self.xpath_query)
        top_split.addWidget(xpath_widget)

        self.splitter.addWidget(top_split)

        # Middle panel: Code + Selection, splitter for resizing
        mid_split = QSplitter(Qt.Orientation.Horizontal)

        # Code box (#3)
        code_widget = QWidget()
        code_widget.setContentsMargins(0, 0, -2, 0)
        code_box = QVBoxLayout(code_widget)
        # Code controls
        code_ctrl = QHBoxLayout()
        code_ctrl.setContentsMargins(0, 0, 0, 0)
        code_ctrl.setSpacing(2)
        code_ctrl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.code_run = QPushButton()
        self.code_run.setToolTip('Run - Ctrl+Enter')
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
        # Code label
        code_ctrl.addStretch()
        code_label = QLabel('Python Code Editor')
        code_label.setStyleSheet("padding-right: 8px;")
        code_ctrl.addWidget(code_label)
        code_box.addLayout(code_ctrl)
        # Code editor
        self.code_editor = CodeEditor(execute_callback=self._run_code)
        self.code_editor.setPlaceholderText(
            'Write Python code here...\n\n'
            '`etree` is imported from `lxml`\n'
            '`doc` is the XML document (`_ElementTree`)\n'
            '`xpath_expr` is the last XPath (`str`)\n'
            '`xpath_result` is the last XPath result (`list[_Element]`)\n'
            '`nsmap` is the namespace map, to be passed as `namespaces`')
        code_box.addWidget(self.code_editor)
        mid_split.addWidget(code_widget)

        # Selection box (#4)
        sel_widget = QWidget()
        sel_widget.setContentsMargins(0, 0, -2, 0)
        sel_box = QVBoxLayout(sel_widget)
        # Selection controls above the view
        sel_ctrl = QHBoxLayout()
        sel_ctrl.setContentsMargins(0, 0, 0, 0)
        sel_ctrl.setSpacing(2)
        sel_ctrl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.strip_ns_toggle = QPushButton()
        self.strip_ns_toggle.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogResetButton))
        self.strip_ns_toggle.setCheckable(True)
        self.strip_ns_toggle.setChecked(False)
        self.strip_ns_toggle.setToolTip('Strip namespace declarations')
        for btn in [self.strip_ns_toggle]:
            btn.setFixedSize(32,32)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.strip_ns_toggle.toggled.connect(self._run_xpath)
        self.strip_ns_toggle.setStyleSheet("""
            QPushButton {
                border: 1px solid #ccc;
                padding: 4px 10px;
            }
            QPushButton:checked {
                background-color: #ddd;
                border-style: inset;
            }
            QPushButton:checked:focus {
                outline: none;
            }
        """)
        sel_ctrl.addWidget(self.strip_ns_toggle)
        # Selection label
        sel_ctrl.addStretch()
        sel_label = QLabel('Selection Viewer')
        sel_label.setStyleSheet("padding-right: 8px;")
        sel_ctrl.addWidget(sel_label)
        sel_box.addLayout(sel_ctrl)
        # Selection viewer
        self.selection_view = CodeViewer()
        self.selection_view.setPlaceholderText('XPath selection output... (currently None)')
        sel_box.addWidget(self.selection_view)
        mid_split.addWidget(sel_widget)

        self.splitter.addWidget(mid_split)

        # Bottom panel: output and messages (#5)
        bottom_split = QSplitter(Qt.Orientation.Horizontal)

        # Output box
        out_widget = QWidget()
        out_widget.setContentsMargins(0, 0, -2, 0)
        out_box = QVBoxLayout(out_widget)
        out_ctrl = QHBoxLayout()
        out_ctrl.setContentsMargins(0, 0, 0, 0)
        out_ctrl.setSpacing(2)
        out_ctrl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.output_clear = QPushButton()
        self.output_clear.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogDiscardButton))
        self.output_clear.setFixedSize(32, 32)
        self.output_clear.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.output_clear.clicked.connect(self._clear_output)
        out_ctrl.addWidget(self.output_clear)
        # Output label
        out_ctrl.addStretch()
        out_label = QLabel('Output')
        out_label.setStyleSheet("padding-right: 8px;")
        out_ctrl.addWidget(out_label)
        out_box.addLayout(out_ctrl)
        self.output_view = CodeViewer()
        out_box.addWidget(self.output_view)
        bottom_split.addWidget(out_widget)

        # Messages box
        msg_widget = QWidget()
        out_widget.setContentsMargins(0, 0, 0, 0)
        msg_box = QVBoxLayout(msg_widget)
        msg_ctrl = QHBoxLayout()
        msg_ctrl.setContentsMargins(0, 0, 0, 0)
        msg_ctrl.setSpacing(2)
        msg_ctrl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.messages_clear = QPushButton()
        self.messages_clear.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogDiscardButton))
        self.messages_clear.setFixedSize(32, 32)
        self.messages_clear.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.messages_clear.clicked.connect(self._clear_messages)
        msg_ctrl.addWidget(self.messages_clear)
        # Messages label
        msg_ctrl.addStretch()
        msg_label = QLabel('Messages')
        msg_label.setStyleSheet("padding-right: 8px;")
        msg_ctrl.addWidget(msg_label)
        msg_box.addLayout(msg_ctrl)
        self.messages_view = CodeViewer()
        msg_box.addWidget(self.messages_view)
        bottom_split.addWidget(msg_widget)

        self.splitter.addWidget(bottom_split)

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
        file_menu = self.menuBar().addMenu('File')
        open_act = file_menu.addAction('Open...')
        open_act.triggered.connect(self._open_file)
        self.revert_act = file_menu.addAction('Revert / Reload')
        self.revert_act.setDisabled(True)
        self.revert_act.triggered.connect(self._revert_file)
        self.save_act = file_menu.addAction('Save (Overwrite)')
        self.save_act.setDisabled(True)
        self.save_act.triggered.connect(self._save_file)
        self.save_as_act = file_menu.addAction('Save As...')
        self.save_as_act.setDisabled(True)
        self.save_as_act.triggered.connect(self._save_as_file)
        file_menu.addSeparator()
        self.file_undo_act = file_menu.addAction('Undo (Code change)')
        self.file_undo_act.setDisabled(True)
        self.file_undo_act.triggered.connect(self._undo_last)
        self.file_redo_act = file_menu.addAction('Redo')
        self.file_redo_act.setDisabled(True)
        self.file_redo_act.triggered.connect(self._redo_last)
        file_menu.addSeparator()
        file_exit = file_menu.addAction('Exit')
        file_exit.triggered.connect(self.close)

        file_menu = self.menuBar().addMenu('LLM (OpenAI)')
        if self.llm.api_key:
            if self.llm.api_key_env:
                self.key_status_act = QAction('API Key: Environment', self)
            else:
                self.key_status_act = QAction('API Key: From Store', self)
        else:
            self.key_status_act = QAction('API Key: None', self)
        file_menu.addAction(self.key_status_act)
        set_key_act = file_menu.addAction('Set API key...')
        set_key_act.triggered.connect(self._set_api_key)
        unset_key_act = file_menu.addAction('Unset API key')
        unset_key_act.triggered.connect(self._unset_api_key)

    def _set_api_key(self):
        text, ok = QInputDialog.getText(self, 'Enter your API key',
                                        'OpenAI API Key:', QLineEdit.EchoMode.Normal,
                                        '')
        if ok and text:
            store_api_key('OpenAI API Key', text)
            self.llm.api_key = text
            self.llm.api_key_env = False
            self.key_status_act.setText('API Key: From Store')

    def _unset_api_key(self):
        delete_api_key('OpenAI API Key')
        self.llm.api_key = None
        self.llm.api_key_env = False
        self.key_status_act.setText('API Key: None')

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Open XML File', filter='XML Files (*.xml);;All Files (*)')
        if path:
            self.load_xml(path)
            self.path = path
            self.file_undo_act.setDisabled(True)
            self.file_redo_act.setDisabled(True)
            self.save_act.setDisabled(False)
            self.save_as_act.setDisabled(False)
            self.revert_act.setDisabled(False)

    def _save_as_file(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Save XML File', filter='XML Files (*.xml);;All Files (*)')
        if path and self.doc:
            with open(path, 'wb') as f:
                f.write(etree.tostring(self.doc, pretty_print=True, xml_declaration=True, encoding='UTF-8'))
            self.path = path
            self.messages_view.append(f'Saved XML to: {path}')

    def _save_file(self):
        with open(self.path, 'wb') as f:
            f.write(etree.tostring(self.doc, pretty_print=True, xml_declaration=True, encoding='UTF-8'))
        self.messages_view.append(f'Saved XML to: {self.path}')

    def _revert_file(self):
        if self.path is None:
            self.messages_view.append('<span style="color: red;">No file to revert</span>')
            return
        if not Path(self.path).exists():
            self.messages_view.append(f'<span style="color: red;">File does not exist: {self.path}</span>')
            return
        if not self.load_xml(self.path):
            self.messages_view.append(f'<span style="color: red;">Failed to revert file: {self.path}</span>')
            return
        self.messages_view.append(f'Reloaded XML from file: {self.path}')
        self.file_history.clear()
        self.file_undo_act.setDisabled(True)
        self.file_redo_act.setDisabled(True)

    def _undo_last(self):
        prev = self.file_history.undo()
        if prev is None:
            self.file_undo_act.setDisabled(True)
            return
        self.doc = prev
        self.file_redo_act.setDisabled(False)
        if self.file_history.index < 1:
            self.file_undo_act.setDisabled(True)

    def _redo_last(self):
        _next = self.file_history.redo()
        if _next is None:
            self.file_redo_act.setDisabled(True)
            return
        self.doc = _next
        self.file_undo_act.setDisabled(False)
        if self.file_history.can_redo:
            self.file_redo_act.setDisabled(True)

    def load_xml(self, path) -> bool:
        try:
            self.doc, self.nsmap, self.ns = parse_xml(path)
        except OSError:
            self.messages_view.append(f'<span style="color: red;">Error loading XML from: {path}</span>')
            return False

        if self.ns is not None:
            self.xpath_ns_edit.setText(self.ns)
            self.xpath_ns_edit.show()
        else:
            self.xpath_ns_edit.hide()
        self.messages_view.append(f'Loaded XML from: {path}')
        return True

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

    def _clear_output(self):
        self.output_view.clear()

    def _clear_messages(self):
        self.messages_view.clear()

    def _run_xpath(self):
        expr = self.xpath_query.toPlainText().strip()
        if not expr or not self.doc:
            return
        self.xpath_history.add(expr)
        self.xpath_expr = expr
        try:
            self.xpath_result = apply_xpath(self.doc, expr, self.nsmap)
            strip_ns = self.strip_ns_toggle.isChecked()
            self.selection_view.setPlainText('\n'.join(pretty_print(node, strip_ns) for node in self.xpath_result))
            self.messages_view.append(f'XPath executed: {expr}')
        except etree.XPathEvalError as e:
            error = f'  Error: {e}' if str(e) != 'Invalid expression' else ''
            self.messages_view.append(f'<span style="color: red;">Invalid XPath expression: {expr}{error}</span>')

    def _run_code(self):
        code = self.code_editor.toPlainText()
        if not code or not self.doc:
            return
        self.code_history.add(code)
        buf = io.StringIO()
        self.file_history.add(self.doc)
        self.file_undo_act.setDisabled(False)
        self.file_redo_act.setDisabled(True)
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
                self.output_view.append(output)
            self.messages_view.append('Code executed successfully.')
            self._run_xpath()
        except Exception as e:
            self.messages_view.append(f'<span style="color: red;">Code execution error: {e}</span>')

    def _run_llm(self):
        prompt = self.llm_query.toPlainText().strip()
        if not prompt:
            return
        self.llm_history.add(prompt)
        self.messages_view.append(f'LLM prompt: {prompt}')
        xml_text = etree.tostring(self.doc, pretty_print=False, encoding='unicode') if self.doc else ''
        response = self.llm.query(prompt, {'xml': xml_text, 'xpath': self.xpath_expr, 'code': self.code_editor.toPlainText()}, self.ns)
        if 'xpath' in response:
            self.xpath_query.setPlainText(response['xpath'])
            self._run_xpath()
        if 'code' in response:
            self.code_editor.setPlainText(response['code'])
            # not running the code automatically
        if 'text' in response:
            self.output_view.append(response['text'])
