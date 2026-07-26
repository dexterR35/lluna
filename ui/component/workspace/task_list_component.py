import os
from pathlib import Path
from enum import Enum, unique
from dataclasses import dataclass
from functools import cached_property

from PySide6.QtWidgets import QWidget, QVBoxLayout, QMenu, QAbstractItemView, QTableWidgetItem, QHeaderView, QStackedLayout
from PySide6.QtCore import Qt, Signal
from qfluentwidgets import TableWidget, BodyLabel, InfoBar
from PySide6.QtGui import QAction, QBrush, QColor, QKeySequence, QShortcut
from showinfm import show_in_file_manager

from backend.config import config, tr
from backend.tools.common_tools import is_image_file
from ui.component.utils.confirm_dialog import ask_confirm
from ui.theme import STATUS, TEXT_SECONDARY

@unique
class TaskStatus(Enum):
    PENDING = tr['TaskList']['Pending']
    PROCESSING = tr['TaskList']['Processing']
    COMPLETED = tr['TaskList']['Completed']
    FAILED = tr['TaskList']['Failed']
    STOPPED = tr['TaskList'].get('Stopped', 'Stopped')


@unique
class TaskOptions(Enum):
    AB_SECTIONS = "ab_sections"
    SUB_AREAS = "sub_areas"

@dataclass
class Task:
    path: str
    name: str
    progress: int
    status: TaskStatus
    options: dict
    # Read-only output path, set after task completes / is saved
    _output_path: str = None
    # Filename stem suffix before extension (e.g. "_no_sub", "_nobg")
    output_suffix: str = "_no_sub"
    # Unsaved preview (temp PNG) for BG remove - not the final save path
    preview_temp_path: str = None
    # Pre-remove keep-mask (temp L PNG) - painted areas stay opaque after cutout
    protect_mask_path: str = None
    saved: bool = False

    @property
    def output_path(self):
        """Get output path"""
        if self._output_path is not None:
            return self._output_path
        save_directory = os.path.dirname(self.path) if not config.saveDirectory.value else config.saveDirectory.value
        if self.is_image:
            output_path = os.path.abspath(os.path.join(save_directory, f'{Path(self.path).stem}{self.output_suffix}.png'))
        else:
            output_path = os.path.abspath(os.path.join(save_directory, f'{Path(self.path).stem}{self.output_suffix}.mp4'))
        return output_path

    @output_path.setter
    def output_path(self, value):
        self._output_path = value

    @cached_property
    def is_image(self):
        """Whether this is an image file"""
        return is_image_file(self.path)

class TaskListComponent(QWidget):
    """Task list component"""
    
    # Define signals
    task_selected = Signal(int, str)  # Emitted when a task is selected (index, video path)
    task_deleted = Signal(int, object)  # Emitted after delete (old index, removed Task)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TaskListComponent")
        
        # Initialize variables
        self.tasks = []  # Task list storage
        self.current_task_index = -1  # Currently selected task index
        
        # Create layout
        self.__init_widgets()
        
    def __init_widgets(self):
        """Initialize widgets"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        stack_host = QWidget(self)
        self._stack = QStackedLayout(stack_host)
        self._stack.setContentsMargins(0, 0, 0, 0)

        # Empty-state hint
        self.empty_hint = BodyLabel(tr['TaskList']['EmptyListHint'], stack_host)
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_hint.setWordWrap(True)
        self.empty_hint.setStyleSheet(f"color: {TEXT_SECONDARY}; padding: 24px;")
        self._stack.addWidget(self.empty_hint)

        # Create table
        self.table = TableWidget(stack_host)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels([tr['TaskList']['Name'], tr['TaskList']['Progress'], tr['TaskList']['Status']])
        
        # Set table style
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        
        # Set column resize modes
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)           # Name column stretches
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Progress column fits content
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Status column fits content
        
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        # Connect signals
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.clicked.connect(self.on_task_clicked)

        self._stack.addWidget(self.table)
        self._stack.setCurrentWidget(self.empty_hint)
        layout.addWidget(stack_host)

        # Delete selected task (Backspace / Delete)
        self._shortcut_delete = QShortcut(QKeySequence.StandardKey.Delete, self)
        self._shortcut_delete.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._shortcut_delete.activated.connect(self._delete_selected_task)
        self._shortcut_backspace = QShortcut(QKeySequence(Qt.Key.Key_Backspace), self)
        self._shortcut_backspace.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._shortcut_backspace.activated.connect(self._delete_selected_task)

    def _refresh_empty_state(self):
        """Show empty hint when there are no tasks."""
        if self.tasks:
            self._stack.setCurrentWidget(self.table)
        else:
            self._stack.setCurrentWidget(self.empty_hint)
        
    def add_task(self, video_path, output_suffix: str = "_no_sub"):
        """Add a task to the list
        
        Args:
            video_path: video/image file path
            output_suffix: stem suffix for output filename (e.g. "_no_sub", "_nobg")
        """
        # Replace task with the same path
        for row, task in enumerate(self.tasks[:]):
            if task.path == video_path:
                self.delete_task(row)
                continue
                
        # Get file name
        file_name = os.path.basename(video_path)
        
        # Add to task list
        task = Task(
            path=video_path,
            name=file_name,
            progress=0,
            status=TaskStatus.PENDING,
            options={},
            output_suffix=output_suffix,
        )
        self.tasks.append(task)
        
        # Update table
        row = len(self.tasks) - 1
        self.table.setRowCount(len(self.tasks))
        
        item0 = QTableWidgetItem(file_name)
        item1 = QTableWidgetItem("0%")
        item2 = QTableWidgetItem(TaskStatus.PENDING.value)
        
        # Elide file name in the middle
        item0.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        item0.setToolTip(video_path)  # Full path as tooltip
        # Set table text elide mode
        self.table.setTextElideMode(Qt.ElideMiddle)
        
        item1.setTextAlignment(Qt.AlignCenter)
        item2.setTextAlignment(Qt.AlignCenter)
        
        self.table.setItem(row, 0, item0)
        self.table.setItem(row, 1, item1)
        self.table.setItem(row, 2, item2)
        
        # Scroll to the newly added row
        self.table.scrollToBottom()
        self._refresh_empty_state()
        return True
        
    def update_task_progress(self, index, progress):
        """Update task progress
        
        Args:
            index: task index
            progress: progress value (0-100)
        """
        if 0 <= index < len(self.tasks):
            self.tasks[index].progress = progress
            
            # Update progress cell
            progress_item = self.table.item(index, 1)
            if progress_item:
                progress_item.setText(f"{progress}%")
            
            # Scroll current processing task into view
            if index == self.current_task_index:
                self.table.scrollTo(self.table.model().index(index, 0))
                
    def update_task_status(self, index, status):
        """Update task status
        
        Args:
            index: task index
            status: task status
        """
        if 0 <= index < len(self.tasks):
            self.tasks[index].status = status
            status_item = self.table.item(index, 2)
            if status_item:
                status_item.setText(status.value)
                
                # Color by status
                if status == TaskStatus.COMPLETED:
                    status_item.setForeground(QBrush(QColor(STATUS["success"])))
                elif status == TaskStatus.PROCESSING:
                    status_item.setForeground(QBrush(QColor(STATUS["processing"])))
                elif status == TaskStatus.FAILED:
                    status_item.setForeground(QBrush(QColor(STATUS["error"])))
                elif status == TaskStatus.STOPPED:
                    status_item.setForeground(QBrush(QColor(STATUS["warning"])))
                else:
                    status_item.setForeground(QBrush(QColor(STATUS["muted"])))
            
            # Scroll current processing task into view
            if index == self.current_task_index:
                self.table.scrollTo(self.table.model().index(index, 0))
                
            # Select current row
            self.table.selectRow(index)
    
    def get_pending_tasks(self):
        """Get tasks that are ready to run (Pending or Stopped).
        
        Returns:
            list: runnable tasks as (index, task) tuples
        """
        return [
            (i, task)
            for i, task in enumerate(self.tasks)
            if task.status in (TaskStatus.PENDING, TaskStatus.STOPPED)
        ]
    
    def get_all_tasks(self):
        """Get all tasks
        
        Returns:
            list: all tasks
        """
        return self.tasks

    def get_task(self, index):
        """Get task at index

        Args:
            index: task index

        Returns:
            Task: task object
        """
        if 0 <= index < len(self.tasks):
            return self.tasks[index]
        return None
    
    def find_task_index_by_path(self, path):
        tasks = self.get_all_tasks()
        for idx, task in enumerate(tasks):
            if task.path == path:
                return idx
        return -1  # Not found
        
    def show_context_menu(self, pos):
        """Show context menu
        
        Args:
            pos: mouse position
        """
        index = self.table.indexAt(pos)
        if index.isValid():
            menu = QMenu(self)
            
            # Open source video location
            open_video_location_action = QAction(tr['TaskList']['OpenSourceVideoLocation'], self)
            open_video_location_action.triggered.connect(lambda: self.open_file_location(self.tasks[index.row()].path))
            menu.addAction(open_video_location_action)
            
            # Open target file location
            def open_target_location():
                task = self.tasks[index.row()]
                path = task._output_path if task.saved else None
                if not path or not os.path.isfile(path):
                    InfoBar.warning(
                        title=tr['TaskList']['Warning'],
                        content=tr['TaskList']['TargetFileNotFound'],
                        parent=self.get_root_parent(),
                        duration=config.infoBarDurationMs
                    )
                    return
                self.open_file_location(path)
            open_target_location_action = QAction(tr['TaskList']['OpenTargetVideoLocation'], self)
            open_target_location_action.triggered.connect(open_target_location)
            menu.addAction(open_target_location_action)

            reset_task_status_action = QAction(tr['TaskList']['ResetTaskStatus'], self)
            reset_task_status_action.triggered.connect((lambda: (
                    self.update_task_status(index.row(), TaskStatus.PENDING), 
                    self.update_task_progress(index.row(), 0)
                )
            ))
            menu.addAction(reset_task_status_action)
            
            # Delete task
            delete_action = QAction(tr['TaskList']['DeleteTask'], self)
            delete_action.triggered.connect(lambda: self.confirm_delete_task(index.row()))
            menu.addAction(delete_action)
            
            # Show menu
            menu.exec_(self.table.viewport().mapToGlobal(pos))

    def confirm_delete_task(self, row):
        """Ask for confirmation before deleting a task."""
        if not (0 <= row < len(self.tasks)):
            return
        if ask_confirm(
            tr['TaskList']['DeleteConfirmTitle'],
            tr['TaskList']['DeleteConfirmDesc'],
            self.get_root_parent(),
        ):
            self.delete_task(row)

    def _delete_selected_task(self):
        row = self.current_task_index
        if row < 0:
            rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
            if rows:
                row = rows[0].row()
        if 0 <= row < len(self.tasks):
            self.confirm_delete_task(row)

    def delete_task(self, row):
        """Delete a task and emit task_deleted(old_index, removed_task)."""
        if not (0 <= row < len(self.tasks)):
            return None

        removed = self.tasks.pop(row)
        self.table.removeRow(row)

        if self.current_task_index == row:
            self.current_task_index = -1
        elif self.current_task_index > row:
            self.current_task_index -= 1

        self.task_deleted.emit(row, removed)
        self._refresh_empty_state()
        return removed

    def clear_all(self):
        """Remove every task from the list. Returns tasks that were removed."""
        removed = list(self.tasks)
        self.tasks.clear()
        self.table.setRowCount(0)
        self.current_task_index = -1
        self._refresh_empty_state()
        return removed
    
    def on_task_clicked(self, index):
        """Handle task click
        
        Args:
            index: index
        """
        row = index.row()
        if 0 <= row < len(self.tasks):
            self.current_task_index = row
            # Notify external listener to load the video
            self.task_selected.emit(row, self.tasks[row].path)
            
    def set_current_task(self, index):
        """Set the currently processing task
        
        Args:
            index: task index
        """
        if 0 <= index < len(self.tasks):
            self.current_task_index = index
            self.table.selectRow(index)
            self.table.scrollTo(self.table.model().index(index, 0))
        
    def get_current_task_index(self):
        """Get the currently processing task index

        Returns:
            int: task index
        """
        return self.current_task_index
            
    def select_task(self, index):
        """Select the specified task
        
        Args:
            index: task index
        """
        self.set_current_task(index)
        if 0 <= index < len(self.tasks):
            self.task_selected.emit(index, self.tasks[index].path)

    def open_file_location(self, path):
        """Open the file location
        
        Args:
            row: row index
            path: target path
        """                
        # Check whether the file exists
        if not os.path.exists(path):
            InfoBar.warning(
                title=tr['TaskList']['Warning'],
                content=tr['TaskList']['UnableToLocateFile'],
                parent=self.get_root_parent(),
                duration=config.infoBarDurationMs
            )
            return
            
        show_in_file_manager(os.path.abspath(path))

    def get_root_parent(self):
        parent = self
        while parent.parent():
            parent = parent.parent()
        return parent

    def update_task_option(self, index, task_option: TaskOptions, value):
        """Update a task option

        Args:
            index: task index
            task_option: option name
            value: option value
        """
        if 0 <= index < len(self.tasks):
            self.tasks[index].options[task_option.value] = value

    def get_task_option(self, index, task_option: TaskOptions, default=None):
        """Get a task option
        Args:
            index: task index
            task_option: option name
            default: default value
        Returns:
            option value
        """
        if 0 <= index < len(self.tasks):
            return self.tasks[index].options.get(task_option.value, default)