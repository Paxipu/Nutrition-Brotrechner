"""Hauptfenster: Navigation, Menü und Verdrahtung aller Seiten.

Das Fenster besitzt den Datenbestand und ist die einzige Stelle, die speichert.
Die Seiten kennen weder Dateien noch Pfade - sie melden Absichten über Signale
und bekommen fertige Daten zurück. Diese Trennung ist der Grund, warum sich die
Fachlogik ohne Qt testen lässt.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QByteArray, QSize
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from brotrechner import __version__, paths
from brotrechner.core.analysis import RecipeAnalysis
from brotrechner.core.models import Ingredient
from brotrechner.core.validation import Severity, validate_database
from brotrechner.data import portable
from brotrechner.data.repository import (
    IngredientStore,
    RecipeStore,
    RepositoryError,
    load_ingredients,
    load_recipes,
    save_ingredients,
    save_recipes,
)
from brotrechner.data.seed import ensure_user_database
from brotrechner.export import report, table
from brotrechner.gui.dialogs.ingredient_dialog import IngredientDialog
from brotrechner.gui.dialogs.label_dialog import LabelDialog
from brotrechner.gui.dialogs.simple_dialogs import (
    AboutDialog,
    ImportDialog,
    ScaleDialog,
    ValidationDialog,
)
from brotrechner.gui.pages.calculator import CalculatorPage
from brotrechner.gui.pages.ingredients import IngredientsPage
from brotrechner.gui.pages.recipes import RecipesPage
from brotrechner.gui.theme import SPACING, ThemeMode, Tokens, build_stylesheet, resolve_tokens
from brotrechner.settings import Settings, load_settings, save_settings

__all__ = ["MainWindow"]

log = logging.getLogger(__name__)

_PAGES: tuple[tuple[str, str, str], ...] = (
    ("Rechner", "Rezept zusammenstellen und auswerten", "🥖"),
    ("Zutaten", "Zutatendatenbank pflegen", "🌾"),
    ("Rezepte", "Gespeicherte Rezepte", "📖"),
)


class MainWindow(QMainWindow):
    """Fenster des Programms."""

    def __init__(self, *, data_dir: Path | None = None) -> None:
        super().__init__()
        self._data_dir = data_dir or paths.data_dir()
        self._ingredients_path = self._data_dir / paths.INGREDIENTS_FILE
        self._recipes_path = self._data_dir / paths.RECIPES_FILE
        self._settings_path = self._data_dir / paths.SETTINGS_FILE

        self._settings: Settings = load_settings(self._settings_path)
        self._tokens: Tokens = resolve_tokens(ThemeMode(self._settings.theme))
        self._ingredients = IngredientStore()
        self._recipes = RecipeStore()
        self._analysis = RecipeAnalysis()

        self.setWindowTitle(f"Brotrechner {__version__}")
        self.setMinimumSize(QSize(1120, 720))

        self._build_ui()
        self._build_menu()
        self._apply_theme()
        self._restore_geometry()
        self._load_data()

    # ── Aufbau ────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_nav())

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(
            SPACING["xl"], SPACING["lg"], SPACING["xl"], SPACING["lg"]
        )
        content_layout.setSpacing(SPACING["md"])

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.lbl_page_title = QLabel(_PAGES[0][0])
        self.lbl_page_title.setObjectName("PageTitle")
        self.lbl_page_subtitle = QLabel(_PAGES[0][1])
        self.lbl_page_subtitle.setObjectName("PageSubtitle")
        titles.addWidget(self.lbl_page_title)
        titles.addWidget(self.lbl_page_subtitle)
        header.addLayout(titles)
        header.addStretch(1)

        self.btn_save_recipe = QPushButton("Rezept speichern")
        self.btn_report = QPushButton("PDF-Bericht …")
        self.btn_label = QPushButton("Etikett …")
        self.btn_label.setProperty("accent", True)
        for button in (self.btn_save_recipe, self.btn_report, self.btn_label):
            header.addWidget(button)
        content_layout.addLayout(header)

        self.stack = QStackedWidget()
        self.page_calculator = CalculatorPage(self._tokens)
        self.page_ingredients = IngredientsPage(self._tokens)
        self.page_recipes = RecipesPage(self._tokens)
        for page in (self.page_calculator, self.page_ingredients, self.page_recipes):
            self.stack.addWidget(page)
        content_layout.addWidget(self.stack, 1)

        layout.addWidget(content, 1)
        self.setCentralWidget(central)

        self.statusBar().showMessage("Bereit")
        self._connect()

    def _build_nav(self) -> QWidget:
        rail = QWidget()
        rail.setFixedWidth(216)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        rail.setAutoFillBackground(True)
        rail.setStyleSheet(f"background: {self._tokens.sidebar};")
        self._rail = rail

        brand = QLabel("Brotrechner")
        brand.setObjectName("NavBrand")
        layout.addWidget(brand)

        self.nav = QListWidget()
        self.nav.setObjectName("NavRail")
        self.nav.setFrameShape(QListWidget.Shape.NoFrame)
        for title, subtitle, icon in _PAGES:
            item = QListWidgetItem(f"  {icon}   {title}")
            item.setToolTip(subtitle)
            self.nav.addItem(item)
        self.nav.setCurrentRow(0)
        layout.addWidget(self.nav, 1)

        version = QLabel(f"Version {__version__}")
        version.setObjectName("NavVersion")
        layout.addWidget(version)
        return rail

    def _build_menu(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("&Datei")
        self._add_action(file_menu, "Sicherung anlegen", self._on_backup, "Ctrl+B")
        self._add_action(
            file_menu, "Datenverzeichnis öffnen", self._on_open_data_dir, "Ctrl+Shift+O"
        )
        file_menu.addSeparator()
        self._add_action(file_menu, "Zutaten als CSV …", self._on_export_csv)
        self._add_action(file_menu, "PDF-Bericht …", self._on_report, "Ctrl+P")
        self._add_action(file_menu, "Etikett …", self._on_label, "Ctrl+E")
        file_menu.addSeparator()
        self._add_action(file_menu, "Beenden", self.close, "Ctrl+Q")

        recipe_menu = menu.addMenu("&Rezept")
        self._add_action(recipe_menu, "Speichern", self._on_save_recipe, "Ctrl+S")
        self._add_action(recipe_menu, "Neu / leeren", self._on_new_recipe, "Ctrl+N")

        data_menu = menu.addMenu("&Zutaten")
        self._add_action(data_menu, "Neue Zutat …", self._on_create_ingredient, "Ctrl+Shift+N")
        self._add_action(data_menu, "Importieren …", self._on_import, "Ctrl+I")
        self._add_action(data_menu, "Datenprüfung …", self._on_validate, "Ctrl+Shift+P")

        view_menu = menu.addMenu("&Ansicht")
        for mode in ThemeMode:
            action = QAction(mode.label, self)
            action.setCheckable(True)
            action.setChecked(mode.value == self._settings.theme)
            action.triggered.connect(lambda _=False, m=mode: self._on_theme_changed(m))
            view_menu.addAction(action)
        self._theme_actions = view_menu.actions()

        help_menu = menu.addMenu("&Hilfe")
        self._add_action(help_menu, "Über Brotrechner", self._on_about, "F1")

    def _add_action(self, menu: object, text: str, slot: object, shortcut: str = "") -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        menu.addAction(action)  # type: ignore[attr-defined]
        return action

    def _connect(self) -> None:
        self.nav.currentRowChanged.connect(self._on_page_changed)

        self.btn_save_recipe.clicked.connect(self._on_save_recipe)
        self.btn_report.clicked.connect(self._on_report)
        self.btn_label.clicked.connect(self._on_label)

        self.page_calculator.analysis_changed.connect(self._on_analysis_changed)
        self.page_calculator.status_message.connect(self._flash)

        self.page_ingredients.create_requested.connect(self._on_create_ingredient)
        self.page_ingredients.edit_requested.connect(self._on_edit_ingredient)
        self.page_ingredients.duplicate_requested.connect(self._on_duplicate_ingredient)
        self.page_ingredients.delete_requested.connect(self._on_delete_ingredient)
        self.page_ingredients.import_requested.connect(self._on_import)
        self.page_ingredients.export_requested.connect(self._on_export_ingredients)
        self.page_ingredients.csv_requested.connect(self._on_export_csv)
        self.page_ingredients.validate_requested.connect(self._on_validate)

        self.page_recipes.load_requested.connect(self._on_load_recipe)
        self.page_recipes.scale_requested.connect(self._on_scale_recipe)
        self.page_recipes.rename_requested.connect(self._on_rename_recipe)
        self.page_recipes.delete_requested.connect(self._on_delete_recipe)

        if not report.is_available():
            self.btn_report.setEnabled(False)
            self.btn_report.setToolTip(
                "Für den PDF-Bericht fehlt das Paket reportlab.\n"
                "Installation:  pip install reportlab"
            )

    # ── Daten laden und speichern ─────────────────────────────────────────

    def _load_data(self) -> None:
        """Lädt Zutaten und Rezepte, legt sie beim ersten Start an."""
        try:
            seed = ensure_user_database(
                self._ingredients_path,
                self._recipes_path,
                legacy_dir=Path.cwd(),
            )
            self._ingredients, ingredient_result = load_ingredients(self._ingredients_path)
            self._recipes, recipe_result = load_recipes(self._recipes_path, self._ingredients)
        except RepositoryError as exc:
            QMessageBox.critical(
                self,
                "Daten konnten nicht geladen werden",
                f"{exc}\n\nDas Programm startet mit leerer Datenbank. Die vorhandene "
                f"Datei wurde nicht verändert - eine Sicherung liegt in\n"
                f"{paths.backup_dir(self._data_dir)}",
            )
            self._ingredients, self._recipes = IngredientStore(), RecipeStore()
            self._refresh_all()
            return

        notes = list(seed.notes) + ingredient_result.notes + recipe_result.notes
        self._refresh_all()

        if seed.imported_from_legacy:
            QMessageBox.information(
                self,
                "Altdaten übernommen",
                "Die Dateien der Vorgängerversion wurden gefunden und übernommen:\n\n"
                + "\n".join(f"• {note}" for note in notes[:10])
                + f"\n\nDie Daten liegen ab jetzt in\n{self._data_dir}\n\n"
                "Die alten Dateien bleiben unverändert liegen.",
            )
        elif notes:
            log.info("Hinweise beim Laden: %s", notes)

        self._flash(f"{len(self._ingredients)} Zutaten, {len(self._recipes)} Rezepte geladen")

    def _save_ingredients(self) -> bool:
        """Schreibt die Zutatendatenbank; meldet Fehler an den Anwender."""
        try:
            save_ingredients(self._ingredients_path, self._ingredients)
        except RepositoryError as exc:
            QMessageBox.critical(self, "Speichern fehlgeschlagen", str(exc))
            return False
        return True

    def _save_recipes(self) -> bool:
        try:
            save_recipes(self._recipes_path, self._recipes)
        except RepositoryError as exc:
            QMessageBox.critical(self, "Speichern fehlgeschlagen", str(exc))
            return False
        return True

    def _refresh_all(self) -> None:
        """Reicht den Datenbestand an alle Seiten durch."""
        ingredients = self._ingredients.sorted()
        self.page_calculator.set_ingredients(ingredients)
        self.page_ingredients.set_ingredients(ingredients)
        self.page_recipes.set_data(self._recipes.sorted_by_date(), ingredients)
        self._update_status()

    def _update_status(self) -> None:
        findings = validate_database(self._ingredients)
        errors = sum(1 for f in findings if f.severity is Severity.ERROR)
        warnings = sum(1 for f in findings if f.severity is Severity.WARNING)
        without_price = sum(1 for i in self._ingredients if not i.has_price)

        parts = [f"{len(self._ingredients)} Zutaten", f"{len(self._recipes)} Rezepte"]
        if errors or warnings:
            parts.append(f"Datenprüfung: {errors} Fehler, {warnings} Warnungen")
        else:
            parts.append("Datenprüfung ohne Befund")
        if without_price:
            parts.append(f"{without_price} ohne Preis")
        self.statusBar().showMessage("   ·   ".join(parts))

    def _flash(self, message: str) -> None:
        """Kurze Rückmeldung in der Statuszeile."""
        self.statusBar().showMessage(message, 6000)

    # ── Navigation und Aussehen ───────────────────────────────────────────

    def _on_page_changed(self, row: int) -> None:
        if not 0 <= row < len(_PAGES):
            return
        self.stack.setCurrentIndex(row)
        title, subtitle, _ = _PAGES[row]
        self.lbl_page_title.setText(title)
        self.lbl_page_subtitle.setText(subtitle)

        on_calculator = row == 0
        for button in (self.btn_save_recipe, self.btn_label):
            button.setVisible(on_calculator)
        self.btn_report.setVisible(on_calculator and report.is_available())

    def _on_theme_changed(self, mode: ThemeMode) -> None:
        self._settings.theme = mode.value
        for action in self._theme_actions:
            action.setChecked(action.text() == mode.label)
        self._tokens = resolve_tokens(mode)
        self._apply_theme()
        self.page_calculator.set_tokens(self._tokens)
        self._refresh_all()

    def _apply_theme(self) -> None:
        self.setStyleSheet(build_stylesheet(self._tokens))
        self._rail.setStyleSheet(f"background: {self._tokens.sidebar};")

    def _restore_geometry(self) -> None:
        if not self._settings.window_geometry:
            return
        try:
            self.restoreGeometry(
                QByteArray.fromBase64(self._settings.window_geometry.encode("ascii"))
            )
        except (ValueError, UnicodeEncodeError):  # pragma: no cover - defekte Einstellung
            log.info("Gespeicherte Fenstergeometrie war unlesbar")

    # ── Rezeptaktionen ────────────────────────────────────────────────────

    def _on_analysis_changed(self, analysis: RecipeAnalysis) -> None:
        self._analysis = analysis
        usable = not analysis.is_empty and analysis.baked_weight_g > 0
        self.btn_label.setEnabled(usable)
        self.btn_report.setEnabled(usable and report.is_available())
        if not usable:
            self.btn_label.setToolTip(
                "Erst Zutaten eintragen und das Gewicht des gebackenen Brots angeben."
            )
        else:
            self.btn_label.setToolTip("Etikett anzeigen, speichern oder drucken")

    def _on_new_recipe(self) -> None:
        self.page_calculator.clear()
        self.nav.setCurrentRow(0)
        self._flash("Rechner geleert")

    def _on_save_recipe(self) -> None:
        recipe = self.page_calculator.to_recipe()
        if not recipe.items:
            QMessageBox.information(
                self, "Nichts zu speichern", "Bitte zuerst Zutaten in den Rechner eintragen."
            )
            return

        name, accepted = QInputDialog.getText(
            self, "Rezept speichern", "Name des Rezepts:", text=recipe.name
        )
        if not accepted or not name.strip():
            return
        recipe.name = name.strip()

        if recipe.name in self._recipes:
            answer = QMessageBox.question(
                self,
                "Überschreiben?",
                f"Ein Rezept mit dem Namen „{recipe.name}“ existiert bereits.\n\n"
                "Soll es überschrieben werden?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer is not QMessageBox.StandardButton.Yes:
                return
            existing = self._recipes.get(recipe.name)
            if existing is not None:
                recipe.created_at = existing.created_at
                recipe.notes = existing.notes

        notes, accepted = QInputDialog.getMultiLineText(
            self, "Notizen", "Notizen zum Rezept (optional):", recipe.notes
        )
        if accepted:
            recipe.notes = notes

        self._recipes.add(recipe, replace_existing=True)
        if self._save_recipes():
            self._refresh_all()
            self._flash(f"Rezept „{recipe.name}“ gespeichert")

    def _on_load_recipe(self, name: str) -> None:
        recipe = self._recipes.get(name)
        if recipe is None:  # pragma: no cover - Liste war veraltet
            return
        missing = self.page_calculator.load_recipe(recipe)
        self.nav.setCurrentRow(0)
        if missing:
            names = "\n".join(f"• {item.display_name}" for item in missing)
            QMessageBox.warning(
                self,
                "Zutaten fehlen",
                f"Folgende Zutaten des Rezepts stehen nicht mehr in der Datenbank und "
                f"wurden übersprungen:\n\n{names}\n\n"
                "Die Auswertung ist dadurch unvollständig.",
            )
        else:
            self._flash(f"Rezept „{recipe.name}“ geladen")

    def _on_scale_recipe(self, name: str) -> None:
        recipe = self._recipes.get(name)
        if recipe is None:  # pragma: no cover
            return
        if recipe.baked_weight_g <= 0:
            QMessageBox.information(
                self,
                "Kein Bezugsgewicht",
                "Für dieses Rezept ist kein gebackenes Gewicht hinterlegt. "
                "Bitte es zuerst im Rechner ergänzen und erneut speichern.",
            )
            return

        dialog = ScaleDialog(recipe, self)
        if dialog.exec() != ScaleDialog.DialogCode.Accepted:
            return

        scaled = recipe.scaled(dialog.factor)
        while scaled.name in self._recipes:
            scaled.name += " (2)"
        self._recipes.add(scaled)
        if self._save_recipes():
            self._refresh_all()
            self._flash(f"„{scaled.name}“ angelegt (Faktor {dialog.factor:.3f})")

    def _on_rename_recipe(self, name: str) -> None:
        recipe = self._recipes.get(name)
        if recipe is None:  # pragma: no cover
            return
        new_name, accepted = QInputDialog.getText(
            self, "Rezept umbenennen", "Neuer Name:", text=recipe.name
        )
        new_name = new_name.strip()
        if not accepted or not new_name or new_name == recipe.name:
            return
        if new_name in self._recipes:
            QMessageBox.warning(
                self, "Name vergeben", f"Es gibt bereits ein Rezept namens „{new_name}“."
            )
            return
        self._recipes.remove(recipe.name)
        recipe.name = new_name
        self._recipes.add(recipe)
        if self._save_recipes():
            self._refresh_all()
            self._flash(f"Umbenannt in „{new_name}“")

    def _on_delete_recipe(self, name: str) -> None:
        recipe = self._recipes.get(name)
        if recipe is None:  # pragma: no cover
            return
        answer = QMessageBox.question(
            self,
            "Rezept löschen",
            f"„{recipe.name}“ endgültig löschen?\n\n"
            "Eine Sicherung der Rezeptdatei wird vorher angelegt.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            return
        self._recipes.remove(recipe.name)
        if self._save_recipes():
            self._refresh_all()
            self._flash(f"„{recipe.name}“ gelöscht")

    # ── Zutatenaktionen ───────────────────────────────────────────────────

    def _on_create_ingredient(self) -> None:
        dialog = IngredientDialog(
            self._tokens,
            known_manufacturers=self._ingredients.manufacturers,
            taken_keys=[i.key for i in self._ingredients],
            parent=self,
        )
        if dialog.exec() != IngredientDialog.DialogCode.Accepted:
            return
        ingredient = dialog.result_ingredient()
        self._ingredients.add(ingredient, replace_existing=True)
        if self._save_ingredients():
            self._refresh_all()
            self.nav.setCurrentRow(1)
            self.page_ingredients.select_key(ingredient.key)
            self._flash(f"„{ingredient.display_name}“ angelegt")

    def _on_edit_ingredient(self, key: str) -> None:
        ingredient = self._ingredients.get(key)
        if ingredient is None:  # pragma: no cover
            return
        dialog = IngredientDialog(
            self._tokens,
            ingredient=ingredient,
            known_manufacturers=self._ingredients.manufacturers,
            taken_keys=[i.key for i in self._ingredients],
            parent=self,
        )
        if dialog.exec() != IngredientDialog.DialogCode.Accepted:
            return
        updated = dialog.result_ingredient()
        try:
            self._ingredients.replace(key, updated)
        except KeyError as exc:  # pragma: no cover - im Dialog bereits abgefangen
            QMessageBox.warning(self, "Nicht gespeichert", str(exc))
            return
        if self._save_ingredients():
            self._refresh_all()
            self.page_ingredients.select_key(updated.key)
            self._flash(f"„{updated.display_name}“ gespeichert")

    def _on_duplicate_ingredient(self, key: str) -> None:
        ingredient = self._ingredients.get(key)
        if ingredient is None:  # pragma: no cover
            return
        dialog = IngredientDialog(
            self._tokens,
            template=ingredient,
            known_manufacturers=self._ingredients.manufacturers,
            taken_keys=[i.key for i in self._ingredients],
            parent=self,
        )
        if dialog.exec() != IngredientDialog.DialogCode.Accepted:
            return
        copy = dialog.result_ingredient()
        self._ingredients.add(copy, replace_existing=True)
        if self._save_ingredients():
            self._refresh_all()
            self.page_ingredients.select_key(copy.key)
            self._flash(f"„{copy.display_name}“ angelegt")

    def _on_delete_ingredient(self, key: str) -> None:
        ingredient = self._ingredients.get(key)
        if ingredient is None:  # pragma: no cover
            return

        used_in = [r.name for r in self._recipes if any(i.ingredient_key == key for i in r.items)]
        warning = (
            f"\n\nAchtung: Die Zutat wird in {len(used_in)} Rezept(en) verwendet:\n"
            + "\n".join(f"• {name}" for name in used_in[:6])
            if used_in
            else ""
        )
        answer = QMessageBox.question(
            self,
            "Zutat löschen",
            f"„{ingredient.display_name}“ endgültig löschen?{warning}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            return
        self._ingredients.remove(key)
        if self._save_ingredients():
            self._refresh_all()
            self._flash(f"„{ingredient.display_name}“ gelöscht")

    def _on_import(self) -> None:
        target, _ = QFileDialog.getOpenFileName(
            self,
            "Zutaten importieren",
            str(self._data_dir),
            "Zutatendateien (*.json);;Alle Dateien (*)",
        )
        if not target:
            return
        try:
            imported = portable.parse_ingredient_file(Path(target))
        except RepositoryError as exc:
            QMessageBox.critical(self, "Import fehlgeschlagen", str(exc))
            return

        preview = portable.preview_import(imported, self._ingredients)
        dialog = ImportDialog(preview, self)
        if dialog.exec() != ImportDialog.DialogCode.Accepted:
            return

        result = portable.apply_import(imported, self._ingredients, dialog.policy)
        if result.changed and not self._save_ingredients():
            return
        self._refresh_all()
        self.nav.setCurrentRow(1)
        self._flash(f"Import abgeschlossen: {result.summary()}")

    def _on_export_ingredients(self, ingredients: Sequence[Ingredient]) -> None:
        default_name = (
            f"{ingredients[0].name}.json"
            if len(ingredients) == 1
            else f"zutaten_{len(ingredients)}.json"
        )
        safe = "".join(c if c.isalnum() or c in " -_." else "_" for c in default_name)
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Zutaten exportieren",
            str(self._export_dir() / safe),
            "Zutatendateien (*.json)",
        )
        if not target:
            return
        path = Path(target)
        if path.suffix.lower() != ".json":
            path = path.with_suffix(".json")
        try:
            portable.export_ingredients(path, list(ingredients))
        except (RepositoryError, ValueError) as exc:
            QMessageBox.critical(self, "Export fehlgeschlagen", str(exc))
            return
        self._flash(f"{len(ingredients)} Zutat(en) nach {path.name} exportiert")

    def _on_export_csv(self) -> None:
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Zutaten als CSV",
            str(self._export_dir() / "zutaten.csv"),
            "CSV-Datei (*.csv)",
        )
        if not target:
            return
        try:
            count = table.write_ingredients_csv(Path(target), self._ingredients)
        except OSError as exc:
            QMessageBox.critical(self, "Export fehlgeschlagen", str(exc))
            return
        self._flash(f"{count} Zutaten nach {Path(target).name} exportiert")

    def _on_validate(self) -> None:
        findings = validate_database(self._ingredients)
        ValidationDialog(findings, self._tokens, self).exec()

    # ── Ausgabe ───────────────────────────────────────────────────────────

    def _export_dir(self) -> Path:
        """Standardordner für Ausgaben, bei Bedarf angelegt."""
        configured = self._settings.export_dir
        path = Path(configured) if configured else paths.default_export_dir()
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:  # pragma: no cover - z. B. schreibgeschützt
            path = self._data_dir
        return path

    def _on_label(self) -> None:
        if self._analysis.is_empty or self._analysis.baked_weight_g <= 0:
            QMessageBox.information(
                self,
                "Noch nichts zu zeigen",
                "Für ein Etikett braucht es Zutaten und das Gewicht des gebackenen Brots.",
            )
            return
        LabelDialog(
            self._analysis,
            recipe_name=self.page_calculator.recipe_name,
            default_dir=self._export_dir(),
            parent=self,
        ).exec()

    def _on_report(self) -> None:
        if self._analysis.is_empty:
            QMessageBox.information(
                self, "Kein Rezept", "Bitte zuerst Zutaten in den Rechner eintragen."
            )
            return
        name = self.page_calculator.recipe_name
        safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in name).strip()
        target, _ = QFileDialog.getSaveFileName(
            self,
            "PDF-Bericht speichern",
            str(self._export_dir() / f"{safe or 'Bericht'}.pdf"),
            "PDF-Datei (*.pdf)",
        )
        if not target:
            return
        path = Path(target)
        if path.suffix.lower() != ".pdf":
            path = path.with_suffix(".pdf")
        try:
            report.write_report(path, self._analysis, recipe_name=name)
        except report.ReportError as exc:
            QMessageBox.critical(self, "Bericht fehlgeschlagen", str(exc))
            return
        self._flash(f"Bericht gespeichert: {path.name}")

    # ── Sonstiges ─────────────────────────────────────────────────────────

    def _on_backup(self) -> None:
        ok = self._save_ingredients() and self._save_recipes()
        if ok:
            QMessageBox.information(
                self,
                "Sicherung angelegt",
                f"Zutaten und Rezepte wurden gespeichert. Die vorherigen Stände liegen in\n\n"
                f"{paths.backup_dir(self._data_dir)}",
            )

    def _on_open_data_dir(self) -> None:
        from PySide6.QtCore import QUrl  # noqa: PLC0415 - nur hier gebraucht
        from PySide6.QtGui import QDesktopServices  # noqa: PLC0415

        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._data_dir))):
            QMessageBox.information(self, "Datenverzeichnis", str(self._data_dir))

    def _on_about(self) -> None:
        AboutDialog(
            data_dir=str(self._data_dir),
            ingredient_count=len(self._ingredients),
            recipe_count=len(self._recipes),
            parent=self,
        ).exec()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt-Vertrag
        """Speichert Einstellungen und Daten beim Beenden."""
        self._settings.window_geometry = bytes(self.saveGeometry().toBase64().data()).decode(
            "ascii"
        )
        save_settings(self._settings_path, self._settings)
        self._save_ingredients()
        self._save_recipes()
        super().closeEvent(event)
