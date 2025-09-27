import os
import shlex
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .runner import JudgeConfig, JudgeResult, JudgeRunner


class RunThread(QThread):
    progress = Signal(object)
    finished_all = Signal(list)
    compile_failed = Signal(str)

    def __init__(self, config: JudgeConfig) -> None:
        super().__init__()
        self._config = config
        self._runner = JudgeRunner()

    def run(self) -> None:
        compile_error = self._runner.prepare(self._config)
        if compile_error is not None:
            self.compile_failed.emit(compile_error)
            return
        results: List[JudgeResult] = []
        for res in self._runner.run_all(self._config, on_progress=self.progress.emit):
            results.append(res)
        self.finished_all.emit(results)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Local Judge")
        self._thread: Optional[RunThread] = None
        self._build_ui()
        self._wire_actions()

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)

        # Solution selection
        solution_group = QGroupBox("Solution")
        sg = QGridLayout(solution_group)
        self.solution_path = QLineEdit()
        self.solution_browse = QPushButton("Browse…")
        self.language = QComboBox()
        self.language.addItems(["Auto", "Python", "C", "C++"]) 
        sg.addWidget(QLabel("Solution file:"), 0, 0)
        sg.addWidget(self.solution_path, 0, 1)
        sg.addWidget(self.solution_browse, 0, 2)
        sg.addWidget(QLabel("Language:"), 1, 0)
        sg.addWidget(self.language, 1, 1)

        # Tests selection
        tests_group = QGroupBox("Tests")
        tg = QGridLayout(tests_group)
        self.tests_dir = QLineEdit()
        self.tests_browse = QPushButton("Browse…")
        self.input_pattern = QLineEdit("{num}.in")
        self.output_pattern = QLineEdit("{num}.out")
        tg.addWidget(QLabel("Directory:"), 0, 0)
        tg.addWidget(self.tests_dir, 0, 1)
        tg.addWidget(self.tests_browse, 0, 2)
        tg.addWidget(QLabel("Input pattern:"), 1, 0)
        tg.addWidget(self.input_pattern, 1, 1)
        tg.addWidget(QLabel("Output pattern:"), 2, 0)
        tg.addWidget(self.output_pattern, 2, 1)

        # Checker
        checker_group = QGroupBox("Checker (optional)")
        cg = QGridLayout(checker_group)
        self.checker_path = QLineEdit()
        self.checker_browse = QPushButton("Browse…")
        self.checker_args = QLineEdit("{in} {ans} {out}")
        cg.addWidget(QLabel("Checker executable:"), 0, 0)
        cg.addWidget(self.checker_path, 0, 1)
        cg.addWidget(self.checker_browse, 0, 2)
        cg.addWidget(QLabel("Args template:"), 1, 0)
        cg.addWidget(self.checker_args, 1, 1)

        # Limits and options
        limits_group = QGroupBox("Limits & Options")
        lg = QGridLayout(limits_group)
        self.time_limit = QDoubleSpinBox()
        self.time_limit.setDecimals(2)
        self.time_limit.setRange(0.1, 300.0)
        self.time_limit.setValue(2.0)
        self.mem_limit = QSpinBox()
        self.mem_limit.setRange(16, 8192)
        self.mem_limit.setValue(256)
        self.ignore_ws = QCheckBox("Ignore whitespace when no checker")
        lg.addWidget(QLabel("Time limit (s):"), 0, 0)
        lg.addWidget(self.time_limit, 0, 1)
        lg.addWidget(QLabel("Memory limit (MB):"), 1, 0)
        lg.addWidget(self.mem_limit, 1, 1)
        lg.addWidget(self.ignore_ws, 2, 0, 1, 2)

        # Actions
        actions_row = QHBoxLayout()
        self.run_button = QPushButton("Run")
        actions_row.addWidget(self.run_button)

        # Results table
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Test", "Verdict", "Time (ms)", "Mem (MB)", "Details"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(solution_group)
        layout.addWidget(tests_group)
        layout.addWidget(checker_group)
        layout.addWidget(limits_group)
        layout.addLayout(actions_row)
        layout.addWidget(self.table)

        # Menu (optional minimal)
        file_menu = self.menuBar().addMenu("File")
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    def _wire_actions(self) -> None:
        self.solution_browse.clicked.connect(self._browse_solution)
        self.tests_browse.clicked.connect(self._browse_tests)
        self.checker_browse.clicked.connect(self._browse_checker)
        self.run_button.clicked.connect(self._on_run)
        self.solution_path.textChanged.connect(self._maybe_autodetect_lang)

    def _browse_solution(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select solution")
        if path:
            self.solution_path.setText(path)

    def _browse_tests(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select tests directory")
        if path:
            self.tests_dir.setText(path)

    def _browse_checker(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select checker executable")
        if path:
            self.checker_path.setText(path)

    def _maybe_autodetect_lang(self) -> None:
        if self.language.currentText() != "Auto":
            return
        path = self.solution_path.text().strip()
        ext = os.path.splitext(path)[1].lower()
        if ext == ".py":
            self.language.setCurrentText("Python")
        elif ext == ".c":
            self.language.setCurrentText("C")
        elif ext in (".cc", ".cpp", ".cxx"): 
            self.language.setCurrentText("C++")

    def _collect_config(self) -> Optional[JudgeConfig]:
        sol = self.solution_path.text().strip()
        if not sol:
            QMessageBox.warning(self, "Missing", "Please select a solution file.")
            return None
        tests_dir = self.tests_dir.text().strip()
        if not tests_dir:
            QMessageBox.warning(self, "Missing", "Please select a tests directory.")
            return None
        input_pat = self.input_pattern.text().strip()
        output_pat = self.output_pattern.text().strip()
        if "{num}" not in input_pat or "{num}" not in output_pat:
            QMessageBox.warning(self, "Pattern error", "Both patterns must contain {num}.")
            return None
        lang = self.language.currentText()
        checker = self.checker_path.text().strip() or None
        checker_args = self.checker_args.text().strip() or None
        config = JudgeConfig(
            solution_path=sol,
            language=(lang if lang != "Auto" else None),
            tests_dir=tests_dir,
            input_pattern=input_pat,
            ans_pattern=output_pat,
            checker_path=checker,
            checker_args_template=checker_args,
            time_limit_s=float(self.time_limit.value()),
            memory_limit_mb=int(self.mem_limit.value()),
            ignore_whitespace=self.ignore_ws.isChecked(),
        )
        return config

    def _on_run(self) -> None:
        if self._thread and self._thread.isRunning():
            QMessageBox.information(self, "Busy", "A run is already in progress.")
            return
        config = self._collect_config()
        if config is None:
            return
        self.table.setRowCount(0)
        self._thread = RunThread(config)
        self._thread.progress.connect(self._on_progress)
        self._thread.compile_failed.connect(self._on_compile_failed)
        self._thread.finished_all.connect(self._on_finished)
        self._thread.start()

    def _on_compile_failed(self, message: str) -> None:
        QMessageBox.critical(self, "Compilation failed", message)

    def _on_progress(self, res: JudgeResult) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        items = [
            QTableWidgetItem(res.test_id),
            QTableWidgetItem(res.verdict),
            QTableWidgetItem(str(res.time_ms)),
            QTableWidgetItem(f"{res.memory_mb:.1f}"),
            QTableWidgetItem(res.details or ""),
        ]
        for col, item in enumerate(items):
            if col == 1:
                # Bold verdict
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            self.table.setItem(row, col, item)
        self.table.scrollToBottom()

    def _on_finished(self, results: List[JudgeResult]) -> None:
        total = len(results)
        ac = sum(1 for r in results if r.verdict == "AC")
        QMessageBox.information(self, "Done", f"Finished {total} test(s). Accepted: {ac}.")

