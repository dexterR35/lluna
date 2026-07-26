import cv2
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QMenu
from PySide6.QtCore import Qt, Signal, QRect, QRectF, QObject, QEvent, QTimer
from PySide6.QtGui import QAction, QShortcut, QCursor
from PySide6 import QtWidgets, QtGui
from qfluentwidgets import qconfig, HollowHandleStyle, Slider, ToolButton, FluentIcon

from backend.config import config, tr
from ui.theme import CARD_RADIUS, PREVIEW, VIDEO


class VideoDisplayComponent(QWidget):
    """Video display component with preview and selection boxes"""
    
    # Define signals
    selections_changed = Signal(list)  # Selection boxes changed signal
    ab_sections_changed = Signal(list)  # AB sections changed signal
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        
        # Initialize variables
        self.is_drawing = False
        self.selection_rect = (0, 0, 0, 0)  # Selection currently being drawn or resized (ymin, ymax, xmin, xmax)
        self.selection_rects = []  # Store multiple selections; each is (ymin, ymax, xmin, xmax)
        self.active_selection_index = -1  # Index of the active selection
        self.drag_start_pos = None
        self.resize_edge = None
        self.edge_size = config.selectionEdgeSize  # Edge size for resize handles
        self.enable_mouse_events = True  # Whether mouse events are enabled
        
        # AB section marker variables
        self.ab_sections = []  # Store AB section markers [range(start, end), ...]
        self.current_ab_start = -1  # Start frame of the current AB section
        self._playing = False
        
        # Create context menu
        self.__init_context_menu()
        
        # Get screen size
        screen = QtWidgets.QApplication.primaryScreen().size()
        self.screen_width = screen.width()
        self.screen_height = screen.height()
        
        # Set video preview size (adjust by screen width)
        wide = config.videoPreviewWidth
        compact = config.videoPreviewWidthCompact
        self.video_preview_width = wide
        self.video_preview_height = self.video_preview_width * 9 // 16
        if self.screen_width // 2 < wide:
            self.video_preview_width = compact
            self.video_preview_height = self.video_preview_width * 9 // 16
            
        # Video-related parameters
        self.frame_width = None
        self.frame_height = None
        self.scaled_width = None
        self.scaled_height = None
        self.border_left = 0
        self.border_top = 0
        self.fps = 30

        self.__init_widgets()
        self.__init_shotcuts()
        
    def __init_widgets(self):
        """Initialize widgets (outer SectionCard comes from WorkspacePage)."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setAlignment(Qt.AlignCenter)

        # Inner black background container (no radius — SectionCard already frames the area)
        self.black_container = QWidget(self)
        self.black_container.setObjectName('blackContainer')
        self.black_container.setStyleSheet("""
            #blackContainer {
                background-color: black;
                border: none;
            }
        """)
        black_layout = QVBoxLayout()
        black_layout.setContentsMargins(0, 0, 0, 0)
        black_layout.setSpacing(0)
        black_layout.setAlignment(Qt.AlignCenter)
        
        # Video display label
        self.video_display = QtWidgets.QLabel()
        self.video_display.setStyleSheet("""
            background-color: black;
            border: none;
        """)
        self.video_display.setMinimumSize(self.video_preview_width, self.video_preview_height)
        
        self.video_display.setMouseTracking(True)
        self.video_display.setScaledContents(True)
        self.video_display.setAlignment(Qt.AlignCenter)
        self.video_display.mousePressEvent = self.selection_mouse_press
        self.video_display.mouseMoveEvent = self.selection_mouse_move
        self.video_display.mouseReleaseEvent = self.selection_mouse_release
        
        # Video slider — Fluent Slider + hollow handle
        self.video_slider = Slider(Qt.Horizontal, self)
        self.video_slider.setMinimum(1)
        self.video_slider.setFixedHeight(VIDEO["slider_h"])
        self.video_slider.setMaximum(100)  # Default max 100 to match progress percent
        self.video_slider.setValue(1)
        self.video_slider.setStyle(HollowHandleStyle({
            "handle.color": QtGui.QColor(255, 255, 255),
            "handle.ring-width": 4,
            "handle.hollow-radius": 6,
            "handle.margin": 1
        }))
        self.video_slider.sliderPressed.connect(self.pause)
        
        # Video preview area
        self.video_display.setObjectName('videoDisplay')
        # Create a container to keep aspect ratio
        ratio_container = QWidget()
        ratio_layout = QVBoxLayout(ratio_container)
        ratio_layout.setContentsMargins(0, 0, 0, 0)
        ratio_layout.addWidget(self.video_display)

        # Set fixed aspect ratio
        ratio_container.setFixedHeight(ratio_container.width() * 9 // 16)
        ratio_container.setMinimumWidth(self.video_preview_width)

        # Add to layout
        black_layout.addWidget(ratio_container)

        # Add event filter for size changes
        class RatioEventFilter(QObject):
            def eventFilter(self, obj, event):
                if event.type() == QEvent.Resize:
                    obj.setFixedHeight(obj.width() * 9 // 16)
                return False

        ratio_filter = RatioEventFilter(ratio_container)
        ratio_container.installEventFilter(ratio_filter)

        # Classic controls: Play/Pause + scrubber
        self.control_container = QWidget(self)
        control_layout = QHBoxLayout(self.control_container)
        pad = VIDEO["control_pad"]
        control_layout.setContentsMargins(pad, pad, pad, pad)
        control_layout.setSpacing(VIDEO["control_spacing"])

        self.play_button = ToolButton(FluentIcon.PLAY, self.control_container)
        self.play_button.setToolTip(tr["SubtitleExtractorGUI"].get("Play", "Play"))
        self.play_button.clicked.connect(self.toggle_play)
        control_layout.addWidget(self.play_button, 0)
        control_layout.addWidget(self.video_slider, 1)

        r = VIDEO["control_radius"]
        self.control_container.setStyleSheet(f"""
            background-color: {VIDEO["control_bg"]};
            border-bottom-left-radius: {r}px;
            border-bottom-right-radius: {r}px;
        """)
        black_layout.addWidget(self.control_container)

        self._play_timer = QTimer(self)
        self._play_timer.timeout.connect(self._on_play_tick)
        
        self.black_container.setLayout(black_layout)
        main_layout.addWidget(self.black_container)

    def set_controls_visible(self, visible: bool):
        """Show/hide play + scrubber (hidden for still-image before pane)."""
        self.control_container.setVisible(visible)
        if not visible:
            self.pause()

    def is_playing(self) -> bool:
        return self._playing

    def toggle_play(self):
        if self._playing:
            self.pause()
        else:
            self.play()

    def play(self):
        if self.video_slider.maximum() <= 1:
            return
        self._playing = True
        self.play_button.setIcon(FluentIcon.PAUSE)
        self.play_button.setToolTip(tr["SubtitleExtractorGUI"].get("Pause", "Pause"))
        interval = max(16, int(1000 / max(1.0, float(self.fps or 30))))
        self._play_timer.start(interval)

    def pause(self):
        self._playing = False
        self._play_timer.stop()
        self.play_button.setIcon(FluentIcon.PLAY)
        self.play_button.setToolTip(tr["SubtitleExtractorGUI"].get("Play", "Play"))

    def _on_play_tick(self):
        if not self._playing:
            return
        nxt = self.video_slider.value() + 1
        if nxt > self.video_slider.maximum():
            self.pause()
            return
        self.video_slider.setValue(nxt)
    
    def __init_shotcuts(self):
        """Initialize shortcuts"""
        self.shortcut_ab_start = QShortcut(QtGui.QKeySequence("["), self)
        self.shortcut_ab_start.activated.connect(self.__handle_mark_for_ab_start)
        self.shortcut_ab_start.setContext(Qt.ApplicationShortcut)

        self.shortcut_ab_end = QShortcut(QtGui.QKeySequence("]"), self)
        self.shortcut_ab_end.activated.connect(self.__handle_mark_for_ab_end)
        self.shortcut_ab_end.setContext(Qt.ApplicationShortcut)

        self.shortcut_ab_delete = QShortcut(QtGui.QKeySequence("\\"), self)
        self.shortcut_ab_delete.activated.connect(self.__handle_delete_ab_section)
        self.shortcut_ab_delete.setContext(Qt.ApplicationShortcut)

        self.shortcut_delete_selection = QShortcut(QtGui.QKeySequence.Delete, self)
        self.shortcut_delete_selection.activated.connect(self.__handle_delete_selection)
        self.shortcut_delete_selection.setContext(Qt.ApplicationShortcut)

        # Left/right arrow shortcuts for the slider
        self.shortcut_right = QShortcut(QtGui.QKeySequence(Qt.Key_Right), self)
        self.shortcut_right.activated.connect(lambda: self.__adjust_slider_value(self.fps))
        self.shortcut_right.setContext(Qt.ApplicationShortcut)
        
        self.shortcut_left = QShortcut(QtGui.QKeySequence(Qt.Key_Left), self)
        self.shortcut_left.activated.connect(lambda: self.__adjust_slider_value(-self.fps))
        self.shortcut_left.setContext(Qt.ApplicationShortcut)
        
        # Ctrl+left/right shortcuts for the slider
        self.shortcut_ctrl_right = QShortcut(QtGui.QKeySequence("Ctrl+Right"), self)
        self.shortcut_ctrl_right.activated.connect(lambda: self.__adjust_slider_value(self.fps*5))
        self.shortcut_ctrl_right.setContext(Qt.ApplicationShortcut)
        
        self.shortcut_ctrl_left = QShortcut(QtGui.QKeySequence("Ctrl+Left"), self)
        self.shortcut_ctrl_left.activated.connect(lambda: self.__adjust_slider_value(-self.fps*5))
        self.shortcut_ctrl_left.setContext(Qt.ApplicationShortcut)
        
        # Shift+left/right shortcuts for the slider
        self.shortcut_shift_right = QShortcut(QtGui.QKeySequence("Shift+Right"), self)
        self.shortcut_shift_right.activated.connect(lambda: self.__adjust_slider_value(1))
        self.shortcut_shift_right.setContext(Qt.ApplicationShortcut)
        
        self.shortcut_shift_left = QShortcut(QtGui.QKeySequence("Shift+Left"), self)
        self.shortcut_shift_left.activated.connect(lambda: self.__adjust_slider_value(-1))
        self.shortcut_shift_left.setContext(Qt.ApplicationShortcut)

    def update_video_display(self, frame, draw_selection=True):
        """Update video display"""
        if frame is None:
            return

        # Resize frame to fit video preview area
        frame = cv2.resize(frame, (self.video_preview_width, self.video_preview_height))
        # Convert OpenCV frame (BGR) to QImage and show on QLabel
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_frame.shape
        bytes_per_line = ch * w
        image = QtGui.QImage(rgb_frame.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
        pix = QtGui.QPixmap.fromImage(image)
        
        # Create rounded-corner image
        rounded_pix = QtGui.QPixmap(pix.size())
        rounded_pix.fill(Qt.transparent)  # Fill transparent background
        
        painter = QtGui.QPainter(rounded_pix)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)  # Antialiasing
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
        
        # Create rounded path
        path = QtGui.QPainterPath()
        rect = QRectF(0, 0, pix.width(), pix.height())
        
        # Manually create path with only top-left and top-right rounding
        radius = CARD_RADIUS
        path.moveTo(radius, 0)
        path.lineTo(pix.width() - radius, 0)
        path.arcTo(pix.width() - radius * 2, 0, radius * 2, radius * 2, 90, -90)
        path.lineTo(pix.width(), pix.height())
        path.lineTo(0, pix.height())
        path.lineTo(0, radius)
        path.arcTo(0, 0, radius * 2, radius * 2, 180, -90)
        path.closeSubpath()
        
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, pix)
        painter.end()
        
        # Save current pixmap for drawing selection boxes
        self.current_pixmap = rounded_pix.copy()
        
        self.video_display.setPixmap(rounded_pix)
            
        # Update video display
        self.update_preview_with_rect(draw_selection=draw_selection)

    def clear_preview(self):
        """Release preview pixmap and selections (start-over clean)."""
        self.pause()
        self.current_pixmap = None
        self.clear_selections()
        self.clear_ab_sections()
        self.video_display.clear()
        self.set_dragger_enabled(False)
    
    def update_preview_with_rect(self, rect=None, draw_selection=True):
        """Update preview with selection boxes"""
        if not hasattr(self, 'current_pixmap') or self.current_pixmap is None:
            return
            
        # Use the new rect if provided
        if rect is not None and self.active_selection_index >= 0:
            self.selection_rects[self.active_selection_index] = rect
            
        # Create a copy for drawing
        pixmap_copy = self.current_pixmap.copy()
        painter = QtGui.QPainter(pixmap_copy)
        
        # Draw all selections
        if draw_selection:
            # Compute scale factors
            display_size = self.video_display.size()
            pixmap_size = self.current_pixmap.size()
            scale_x = pixmap_size.width() / display_size.width()
            scale_y = pixmap_size.height() / display_size.height()
            video_display_width = self.video_display.width()
            video_display_height = self.video_display.height()
            for i, rect in enumerate(self.selection_rects):
                # Set selection box style
                if i == self.active_selection_index:
                    pen = QtGui.QPen(QtGui.QColor(PREVIEW["selection_active"]))
                else:
                    # Inactive selection
                    pen = QtGui.QPen(QtGui.QColor(PREVIEW["selection_idle"]))
                pen.setWidth(2)
                painter.setPen(pen)
                
                # Convert ratio coords to pixel coords
                ymin, ymax, xmin, xmax = rect
                pixel_rect = QRect(
                    int(xmin * scale_x * video_display_width),
                    int(ymin * scale_y * video_display_height),
                    int((xmax - xmin) * scale_x * video_display_width),
                    int((ymax - ymin) * scale_y * video_display_height)
                )
                
                # Draw selection box
                painter.drawRect(pixel_rect)
            
            # Also draw the selection currently being drawn
            if self.is_drawing and any(self.selection_rect):
                pen = QtGui.QPen(QtGui.QColor(PREVIEW["selection_active"]))
                pen.setWidth(2)
                painter.setPen(pen)
                
                # Convert ratio coords to pixel coords
                ymin, ymax, xmin, xmax = self.selection_rect
                pixel_rect = QRect(
                    int(xmin * scale_x * video_display_width),
                    int(ymin * scale_y * video_display_height),
                    int((xmax - xmin) * scale_x * video_display_width),
                    int((ymax - ymin) * scale_y * video_display_height)
                )
                
                painter.drawRect(pixel_rect)
            
        # Draw AB section markers
        total_frames = self.video_slider.maximum()
        if total_frames > 0 and self.ab_sections:
            # Draw AB markers 5px from the bottom of the video display
            ab_rect_height = 5
            ab_rect_y = pixmap_copy.height() - ab_rect_height
            
            # Set semi-transparent white brush
            painter.setPen(Qt.NoPen)
            painter.setBrush(QtGui.QColor(255, 255, 255, 128))  # Semi-transparent white
            
            # Compute available width (with left/right margins)
            left_margin = 15
            right_margin = 15
            available_width = pixmap_copy.width() - left_margin - right_margin
            
            for section_range in self.ab_sections:
                # Compute relative position
                start_x = left_margin + int((section_range.start / total_frames) * available_width)
                end_x = left_margin + int((section_range.stop / total_frames) * available_width)
                
                # Draw AB section rectangle
                painter.drawRect(start_x, ab_rect_y, end_x - start_x, ab_rect_height)
        
        # Draw highlight line for current_ab_start
        if self.current_ab_start >= 0 and total_frames > 0:
            # Compute available width (with left/right margins)
            left_margin = 15
            right_margin = 15
            available_width = pixmap_copy.width() - left_margin - right_margin
            
            # Compute relative position of current_ab_start
            start_x = left_margin + int((self.current_ab_start / total_frames) * available_width)
            
            # Set bright white pen
            pen = QtGui.QPen(QtGui.QColor(255, 255, 255))  # Pure white
            pen.setWidth(2)
            painter.setPen(pen)
            
            # Draw highlight line, 5px tall
            ab_line_height = 5
            ab_line_y = pixmap_copy.height() - ab_line_height
            painter.drawLine(start_x, ab_line_y, start_x, pixmap_copy.height())
        
        painter.end()
        
        # Update display
        self.video_display.setPixmap(pixmap_copy)
    
    def selection_mouse_press(self, event):
        """Handle mouse press"""
        if not self.enable_mouse_events:
            return
        
        # Right-click shows context menu
        if event.button() == Qt.RightButton:
            self.context_menu.exec_(event.globalPos())
            return
        
        video_display_width = self.video_display.width()
        video_display_height = self.video_display.height()

        # Start drawing a new selection
        if event.modifiers() & Qt.ControlModifier:
            self.is_drawing = True
            pos = event.pos()
            
            # Convert to ratio coordinates
            y_ratio = (pos.y() - self.border_top) / video_display_height if video_display_height > 0 else 0
            x_ratio = (pos.x() - self.border_left) / video_display_width if video_display_width > 0 else 0
            
            # Initialize selection as a single point
            self.selection_rect = (y_ratio, y_ratio, x_ratio, x_ratio)
            self.drag_start_pos = (y_ratio, x_ratio)  # Save start point ratio coords
            self.resize_edge = None
            self.active_selection_index = -1
            return
        
        # Double-click clears all selections
        if event.type() == QEvent.MouseButtonDblClick:
            self.clear_selections()
            return
        
        # Check if an existing selection was clicked
        pos = event.pos()
        y_ratio = (pos.y() - self.border_top) / video_display_height if video_display_height > 0 else 0
        x_ratio = (pos.x() - self.border_left) / video_display_width if video_display_width > 0 else 0
        
        clicked_index = -1
        for i, rect in enumerate(self.selection_rects):
            # Convert ratio coords to pixel coords for hit-testing
            ymin, ymax, xmin, xmax = rect
            pixel_rect = QRect(
                int(xmin * video_display_width) + self.border_left,
                int(ymin * video_display_height) + self.border_top,
                int((xmax - xmin) * video_display_width),
                int((ymax - ymin) * video_display_height)
            )
            
            # Check if on selection edge (for resize)
            if self.is_on_rect_edge(pos, pixel_rect):
                clicked_index = i
                self.active_selection_index = i
                self.resize_edge = self.get_resize_edge(pos, pixel_rect)
                self.drag_start_pos = (y_ratio, x_ratio)
                self.update_preview_with_rect()
                return
            # Check if inside selection (for move)
            elif pixel_rect.contains(pos):
                clicked_index = i
                self.active_selection_index = i
                self.resize_edge = "move"
                self.drag_start_pos = (y_ratio, x_ratio)
                self.update_preview_with_rect()
                return
        
        # If no selection clicked, start drawing a new one
        if clicked_index == -1:
            self.is_drawing = True
            self.selection_rect = (y_ratio, y_ratio, x_ratio, x_ratio)
            self.drag_start_pos = (y_ratio, x_ratio)
            self.resize_edge = None
            self.active_selection_index = -1

    def is_on_rect_edge(self, pos, pixel_rect):
        """Check whether a point is on a rectangle edge.
        Note: pixel_rect is already a QRect in pixel coordinates.
        """
        # Bottom-right corner
        if abs(pos.x() - pixel_rect.right()) <= self.edge_size and abs(pos.y() - pixel_rect.bottom()) <= self.edge_size:
            return True
        # Top-right corner
        elif abs(pos.x() - pixel_rect.right()) <= self.edge_size and abs(pos.y() - pixel_rect.top()) <= self.edge_size:
            return True
        # Bottom-left corner
        elif abs(pos.x() - pixel_rect.left()) <= self.edge_size and abs(pos.y() - pixel_rect.bottom()) <= self.edge_size:
            return True
        # Top-left corner
        elif abs(pos.x() - pixel_rect.left()) <= self.edge_size and abs(pos.y() - pixel_rect.top()) <= self.edge_size:
            return True
        # Left edge
        elif abs(pos.x() - pixel_rect.left()) <= self.edge_size and pixel_rect.top() <= pos.y() <= pixel_rect.bottom():
            return True
        # Right edge
        elif abs(pos.x() - pixel_rect.right()) <= self.edge_size and pixel_rect.top() <= pos.y() <= pixel_rect.bottom():
            return True
        # Top edge
        elif abs(pos.y() - pixel_rect.top()) <= self.edge_size and pixel_rect.left() <= pos.x() <= pixel_rect.right():
            return True
        # Bottom edge
        elif abs(pos.y() - pixel_rect.bottom()) <= self.edge_size and pixel_rect.left() <= pos.x() <= pixel_rect.right():
            return True
        return False

    def get_resize_edge(self, pos, rect):
        """Get resize edge type"""
        # Bottom-right corner
        if abs(pos.x() - rect.right()) <= self.edge_size and abs(pos.y() - rect.bottom()) <= self.edge_size:
            return "bottomright"
        # Top-right corner
        elif abs(pos.x() - rect.right()) <= self.edge_size and abs(pos.y() - rect.top()) <= self.edge_size:
            return "topright"
        # Bottom-left corner
        elif abs(pos.x() - rect.left()) <= self.edge_size and abs(pos.y() - rect.bottom()) <= self.edge_size:
            return "bottomleft"
        # Top-left corner
        elif abs(pos.x() - rect.left()) <= self.edge_size and abs(pos.y() - rect.top()) <= self.edge_size:
            return "topleft"
        # Left edge
        elif abs(pos.x() - rect.left()) <= self.edge_size and rect.top() <= pos.y() <= rect.bottom():
            return "left"
        # Right edge
        elif abs(pos.x() - rect.right()) <= self.edge_size and rect.top() <= pos.y() <= rect.bottom():
            return "right"
        # Top edge
        elif abs(pos.y() - rect.top()) <= self.edge_size and rect.left() <= pos.x() <= rect.right():
            return "top"
        # Bottom edge
        elif abs(pos.y() - rect.bottom()) <= self.edge_size and rect.left() <= pos.x() <= rect.right():
            return "bottom"
        return None

    def selection_mouse_move(self, event):
        """Handle mouse move"""
        if not self.enable_mouse_events:
            return
        
        video_display_width = self.video_display.width()
        video_display_height = self.video_display.height()
        
        pos = event.pos()
        y_ratio = (pos.y() - self.border_top) / video_display_height if video_display_height > 0 else 0
        x_ratio = (pos.x() - self.border_left) / video_display_width if video_display_width > 0 else 0
        
        # Clamp ratios to 0-1
        y_ratio = max(0, min(1, y_ratio))
        x_ratio = max(0, min(1, x_ratio))
        
        # Handle mouse move by operation mode
        if self.is_drawing:  # Drawing new selection
            # Update selection bottom-right, keep original drag direction
            start_y, _, start_x, _ = self.selection_rect
            self.selection_rect = (start_y, y_ratio, start_x, x_ratio)
            self.update_preview_with_rect()
        elif self.resize_edge and self.active_selection_index >= 0:  # Resizing or moving selection
            ymin, ymax, xmin, xmax = self.selection_rects[self.active_selection_index]
            start_y, start_x = self.drag_start_pos
            
            if self.resize_edge == "move":
                # Move entire selection
                dy = y_ratio - start_y
                dx = x_ratio - start_x
                
                # Compute new position within bounds
                new_ymin = max(0, min(1 - (ymax - ymin), ymin + dy))
                new_ymax = min(1, max(new_ymin + (ymax - ymin), new_ymin))
                new_xmin = max(0, min(1 - (xmax - xmin), xmin + dx))
                new_xmax = min(1, max(new_xmin + (xmax - xmin), new_xmin))
                
                self.selection_rects[self.active_selection_index] = (new_ymin, new_ymax, new_xmin, new_xmax)
                self.drag_start_pos = (y_ratio, x_ratio)
            else:
                # Resize selection
                if "left" in self.resize_edge:
                    xmin = min(xmax - 0.01, x_ratio)
                if "right" in self.resize_edge:
                    xmax = max(xmin + 0.01, x_ratio)
                if "top" in self.resize_edge:
                    ymin = min(ymax - 0.01, y_ratio)
                if "bottom" in self.resize_edge:
                    ymax = max(ymin + 0.01, y_ratio)
                
                # Keep selection within valid range
                xmin = max(0, min(xmin, 1))
                xmax = max(0, min(xmax, 1))
                ymin = max(0, min(ymin, 1))
                ymax = max(0, min(ymax, 1))
                
                # Ensure xmin < xmax, ymin < ymax
                if xmin > xmax:
                    xmin, xmax = xmax, xmin
                if ymin > ymax:
                    ymin, ymax = ymax, ymin
                
                self.selection_rects[self.active_selection_index] = (ymin, ymax, xmin, xmax)
            
            self.update_preview_with_rect()
        else:
            # Update mouse cursor shape
            self.update_cursor_shape(pos)
    
    def selection_mouse_release(self, event):
        """Handle mouse release"""
        if not self.enable_mouse_events:
            return
            
        # Finish drawing or resizing
        if self.is_drawing:
            # Normalize selection (ensure ymin < ymax, xmin < xmax)
            ymin, ymax, xmin, xmax = self.selection_rect
            if ymin > ymax:
                ymin, ymax = ymax, ymin
            if xmin > xmax:
                xmin, xmax = xmax, xmin
            
            # Update normalized selection
            self.selection_rect = (ymin, ymax, xmin, xmax)
            
            # If selection is valid (not a click), add to list
            # Compute width/height from ratios
            width_ratio = abs(xmax - xmin)
            height_ratio = abs(ymax - ymin)
            
            # Convert to pixel size for threshold check
            pixel_width = width_ratio * self.video_display.width()
            pixel_height = height_ratio * self.video_display.height()
            
            if pixel_width > 5 and pixel_height > 5:
                self.selection_rects.append(self.selection_rect)
                self.active_selection_index = len(self.selection_rects) - 1
                
                # Emit selections-changed signal
                self.selections_changed.emit(self.selection_rects)
            
            self.is_drawing = False
            self.selection_rect = (0, 0, 0, 0)  # Reset to empty selection
        elif self.resize_edge and self.active_selection_index >= 0:
            # Normalize selection
            ymin, ymax, xmin, xmax = self.selection_rects[self.active_selection_index]
            if ymin > ymax:
                ymin, ymax = ymax, ymin
            if xmin > xmax:
                xmin, xmax = xmax, xmin
            
            # Update normalized selection
            self.selection_rects[self.active_selection_index] = (ymin, ymax, xmin, xmax)
                        
            # Emit selections-changed signal
            self.selections_changed.emit(self.selection_rects)
            
            self.resize_edge = None
        
    def update_cursor_shape(self, pos):
        """Update cursor shape from mouse position"""
        video_display_height = self.video_display.height()
        video_display_width = self.video_display.width()
        
        # Prefer checking the active selection first
        if self.active_selection_index >= 0 and self.active_selection_index < len(self.selection_rects):
            # Get active selection
            ymin, ymax, xmin, xmax = self.selection_rects[self.active_selection_index]
            
            # Ensure coordinates are normalized
            if xmin > xmax:
                xmin, xmax = xmax, xmin
            if ymin > ymax:
                ymin, ymax = ymax, ymin
            
            # Convert ratio coords to pixel coords
            pixel_rect = QRect(
                round(xmin * video_display_width) + self.border_left,
                round(ymin * video_display_height) + self.border_top,
                round((xmax - xmin) * video_display_width),
                round((ymax - ymin) * video_display_height)
            )
            
            # Check if mouse is on selection edge
            if self.is_on_rect_edge(pos, pixel_rect):
                # Set cursor by edge type
                edge_type = self.get_resize_edge(pos, pixel_rect)
                if edge_type == "left" or edge_type == "right":
                    self.video_display.setCursor(Qt.SizeHorCursor)
                    return
                elif edge_type == "top" or edge_type == "bottom":
                    self.video_display.setCursor(Qt.SizeVerCursor)
                    return
                elif edge_type == "topleft" or edge_type == "bottomright":
                    self.video_display.setCursor(Qt.SizeFDiagCursor)
                    return
                elif edge_type == "topright" or edge_type == "bottomleft":
                    self.video_display.setCursor(Qt.SizeBDiagCursor)
                    return
            elif pixel_rect.contains(pos):
                self.video_display.setCursor(Qt.SizeAllCursor)
                return
        
        # If no active selection or mouse not on it, check others
        for rect in self.selection_rects:
            # Get selection coordinates
            ymin, ymax, xmin, xmax = rect
            
            # Ensure coordinates are normalized
            if xmin > xmax:
                xmin, xmax = xmax, xmin
            if ymin > ymax:
                ymin, ymax = ymax, ymin
            
            # Convert ratio coords to pixel coords
            pixel_rect = QRect(
                round(xmin * video_display_width) + self.border_left,
                round(ymin * video_display_height) + self.border_top,
                round((xmax - xmin) * video_display_width),
                round((ymax - ymin) * video_display_height)
            )
            
            # Check if mouse is on selection edge
            if self.is_on_rect_edge(pos, pixel_rect):
                # Set cursor by edge type
                edge_type = self.get_resize_edge(pos, pixel_rect)
                if edge_type == "left" or edge_type == "right":
                    self.video_display.setCursor(Qt.SizeHorCursor)
                    return
                elif edge_type == "top" or edge_type == "bottom":
                    self.video_display.setCursor(Qt.SizeVerCursor)
                    return
                elif edge_type == "topleft" or edge_type == "bottomright":
                    self.video_display.setCursor(Qt.SizeFDiagCursor)
                    return
                elif edge_type == "topright" or edge_type == "bottomleft":
                    self.video_display.setCursor(Qt.SizeBDiagCursor)
                    return
            # Check if mouse is inside selection
            elif pixel_rect.contains(pos):
                self.video_display.setCursor(Qt.SizeAllCursor)
                return
        
        # Default cursor when not over any selection
        self.video_display.setCursor(Qt.ArrowCursor)
    
    def set_video_parameters(self, frame_width, frame_height, 
                             scaled_width=None, scaled_height=None, 
                             border_left=0, border_top=0, 
                             fps=30):
        """Set video parameters"""
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.scaled_width = scaled_width
        self.scaled_height = scaled_height
        self.border_left = border_left
        self.border_top = border_top
        self.fps = fps
    
    def get_selection_coordinates(self):
        """Get selection coordinates"""
        return self.selection_rect
    
    def set_selection_rects(self, rects):
        """Set selection boxes"""
        self.selection_rects = rects
        self.selection_rect = rects[-1] if rects else QRect()
        self.active_selection_index = len(rects) - 1
        self.update_preview_with_rect()
    
    def load_selections_from_config(self):
        """Load selection relative positions/sizes from config"""
        # Read selection relative positions/sizes from config
        areas_str = config.subtitleSelectionAreas.value
        
        # Check config value is valid
        if not areas_str:
            return False

        # Clear existing selections
        self.selection_rects = []
        self.selection_ratios = []
        
        # Parse config string
        areas = areas_str.split(";")
        for area in areas:
            try:
                parts = area.split(",")
                ymin, ymax, xmin, xmax = map(float, parts)
                self.selection_rects.append((ymin, ymax, xmin, xmax))
            except ValueError:
                continue
        
        # If selections exist, make the last one active
        if self.selection_rects:
            self.active_selection_index = len(self.selection_rects) - 1
        else:
            self.active_selection_index = -1
        self.selections_changed.emit(self.selection_rects)

        # Update preview
        self.update_preview_with_rect()
        
        return len(self.selection_rects) > 0
    
    def preview_coordinates_to_video_coordinates(self, preview_selection_rects):
        """Get selection coordinates in the original video"""
        selection_rects = []
        video_display_height = self.video_display.height()
        video_display_width = self.video_display.width()
        for rect in preview_selection_rects:
            ymin, ymax, xmin, xmax = rect
                
            # Adjust selection coords for black-bar offset
            x_adjusted = max(0, xmin - self.border_left)
            y_adjusted = max(0, ymin - self.border_top)
            
            # Clamp width/height if selection exceeds actual video area
            w_adjusted = min((xmax - xmin), self.scaled_width - x_adjusted)
            h_adjusted = min((ymax - ymin), self.scaled_height - y_adjusted)
            # Convert to original video coordinates
            scale_x = self.frame_width / (self.scaled_width * video_display_width)
            scale_y = self.frame_height / (self.scaled_height * video_display_height)

            # Use round instead of int to avoid precision loss
            xmin = round(x_adjusted * scale_x * video_display_width)
            xmax = round((x_adjusted + w_adjusted) * scale_x * video_display_width)
            ymin = round(y_adjusted * scale_y * video_display_height)
            ymax = round((y_adjusted + h_adjusted) * scale_y * video_display_height)
            
            # Keep coordinates within valid range
            xmin = max(0, min(xmin, self.frame_width))
            xmax = max(0, min(xmax, self.frame_width))
            ymin = max(0, min(ymin, self.frame_height))
            ymax = max(0, min(ymax, self.frame_height))
            
            # Ensure xmin < xmax, ymin < ymax
            if xmin > xmax:
                xmin, xmax = xmax, xmin
            if ymin > ymax:
                ymin, ymax = ymax, ymin
                
            selection_rects.append((ymin, ymax, xmin, xmax))
        return selection_rects

    def set_dragger_enabled(self, enabled):
        """Enable or disable the selection dragger"""
        self.enable_mouse_events = enabled
        self.video_display.setMouseTracking(enabled)
        self.video_display.setCursor(Qt.ArrowCursor)

    def save_selections_to_config(self):
        """Save all selection relative positions/sizes"""
        areas_str_parts = []
        
        for rect in self.selection_rects:
            ymin, ymax, xmin, xmax = rect
            # Use ratio values rounded to 4 decimals
            areas_str_parts.append(f"{round(ymin,4)},{round(ymax,4)},{round(xmin,4)},{round(xmax,4)}")
        
        # Update config
        config.subtitleSelectionAreas.value = ";".join(areas_str_parts)
        if len(config.subtitleSelectionAreas.value) <= 0:
            config.subtitleSelectionAreas.value = config.subtitleSelectionAreas.defaultValue
        qconfig.save()
    
    def get_selection_rects(self):
        """Get all selections"""
        return self.selection_rects
    
    def clear_selections(self):
        """Clear all selections"""
        self.selection_rects = []
        self.active_selection_index = -1
        self.update_preview_with_rect()
        self.selections_changed.emit(self.selection_rects)

    def __handle_delete_selection(self):
        """Handle deleting the current selection"""
        try:
            if self.active_selection_index >= 0 and self.selection_rects:
                # Delete the active selection
                self.selection_rects.pop(self.active_selection_index)
                
                # If selections remain, make the last one active
                if self.selection_rects:
                    self.active_selection_index = len(self.selection_rects) - 1
                else:
                    self.active_selection_index = -1
                
                # Update display
                self.update_preview_with_rect()
                
                # Emit selections-changed signal
                self.selections_changed.emit(self.selection_rects)
                return True
            return False
        finally:
            # Get current mouse position
            global_pos = QCursor.pos()
            pos = self.video_display.mapFromGlobal(global_pos)
            self.update_cursor_shape(pos)

    def __handle_mark_for_ab_start(self):
        """Handle marking AB section start"""
        current_frame = self.video_slider.value()
        if current_frame >= 0:
            # Check if an existing range needs adjusting
            adjusted = False
            for i, section_range in enumerate(self.ab_sections):
                if current_frame in section_range:
                    # Adjust start of existing range
                    self.ab_sections[i] = range(current_frame, section_range.stop)
                    adjusted = True
                    break
            
            if not adjusted:
                # Record new AB section start
                self.current_ab_start = current_frame
            
            # Update display
            self.update_preview_with_rect()
            return True
        return False

    def __handle_mark_for_ab_end(self):
        """Handle marking AB section end"""
        current_frame = self.video_slider.value()
        if current_frame >= 0 and self.current_ab_start >= 0:
            # Check if an existing range needs adjusting
            adjusted = False
            for i, section_range in enumerate(self.ab_sections):
                if current_frame in section_range:
                    # Adjust end of existing range
                    self.ab_sections[i] = range(section_range.start, current_frame + 1)
                    adjusted = True
                    break
            
            if not adjusted and self.current_ab_start != current_frame:
                # Add new AB section
                self.ab_sections.append(range(self.current_ab_start, current_frame + 1))
                self.current_ab_start = -1  # Reset start
                self.ab_sections_changed.emit(self.ab_sections)
            
            # Update display
            self.update_preview_with_rect()
            return True
        return False

    def __handle_delete_ab_section(self):
        """Handle deleting the current AB section"""
        current_frame = self.video_slider.value()
        if current_frame >= 0 and self.ab_sections:
            # Find AB section containing the current frame
            for i, section_range in enumerate(self.ab_sections):
                if current_frame in section_range:
                    # Delete that AB section
                    self.ab_sections.pop(i)
                    
                    # If marked start is inside deleted section, reset it
                    if self.current_ab_start in section_range:
                        self.current_ab_start = -1
                    
                    # Emit AB sections-changed signal
                    self.ab_sections_changed.emit(self.ab_sections)
                    
                    # Update display
                    self.update_preview_with_rect()
                    return True
        return False
    
    def __adjust_slider_value(self, delta):
        """Adjust video slider value"""
        current_value = self.video_slider.value()
        max_value = self.video_slider.maximum()
        new_value = current_value + int(delta)
        
        # Keep new value within valid range
        if new_value < self.video_slider.minimum():
            new_value = self.video_slider.minimum()
        elif new_value > max_value:
            new_value = max_value
            
        # Set new value
        self.video_slider.setValue(new_value)

    def eventFilter(self, obj, event):
        """Event filter for keyboard events"""
        if event.type() == QEvent.KeyPress:
            # Handle Backspace and Delete
            if event.key() == Qt.Key_Backspace or event.key() == Qt.Key_Delete:
                if self.__handle_delete_selection():
                    return True
        # Pass other events to the parent
        return super().eventFilter(obj, event)

    def __init_context_menu(self):
        """Initialize context menu"""
        self.context_menu = QMenu(self)
        
        # Mark AB start action
        self.action_mark_ab_start = QAction(tr['SubtitleExtractorGUI']['MarkABStart'], self)
        self.action_mark_ab_start.setShortcut("[")
        self.action_mark_ab_start.triggered.connect(self.__handle_mark_for_ab_start)
        self.context_menu.addAction(self.action_mark_ab_start)
        
        # Mark AB end action
        self.action_mark_ab_end = QAction(tr['SubtitleExtractorGUI']['MarkABEnd'], self)
        self.action_mark_ab_end.setShortcut("]")
        self.action_mark_ab_end.triggered.connect(self.__handle_mark_for_ab_end)
        self.context_menu.addAction(self.action_mark_ab_end)

        self.action_mark_ab_delete = QAction(tr['SubtitleExtractorGUI']['DeleteABSection'], self)
        self.action_mark_ab_delete.setShortcut("\\")
        self.action_mark_ab_delete.triggered.connect(self.__handle_delete_ab_section)
        self.context_menu.addAction(self.action_mark_ab_delete)

        self.action_delete_selection = QAction(tr['SubtitleExtractorGUI']['DeleteSelection'], self)
        self.action_delete_selection.setShortcut("DELETE")
        self.action_delete_selection.triggered.connect(self.__handle_delete_selection)
        self.context_menu.addAction(self.action_delete_selection)

    def get_ab_sections(self):
        """Get AB section markers"""
        return self.ab_sections

    def set_ab_sections(self, sections):
        """Set AB section markers"""
        self.ab_sections = sections
        self.update_preview_with_rect()

    def clear_ab_sections(self):
        """Clear all AB section markers"""
        self.ab_sections = []
        self.current_ab_start = -1
        self.update_preview_with_rect()

    def closeEvent(self, event):
        """Disconnect signals on window close"""
        try:
            # Disconnect signals
            self.shortcut_ab_start.activated.disconnect(self.__handle_mark_for_ab_start)
            self.shortcut_ab_end.activated.disconnect(self.__handle_mark_for_ab_end)
            self.shortcut_ab_delete.activated.disconnect(self.__handle_delete_ab_section)
            self.action_mark_ab_start.triggered.disconnect(self.__handle_mark_for_ab_start)
            self.action_mark_ab_end.triggered.disconnect(self.__handle_mark_for_ab_end)
            self.action_mark_ab_delete.triggered.disconnect(self.__handle_delete_ab_section)
            self.action_delete_selection.triggered.disconnect(self.__handle_delete_selection)
            self.shortcut_delete_selection.activated.disconnect(self.__handle_delete_selection)
        except Exception as e:
            print(f"Error during close window:", e)
        super().closeEvent(event)