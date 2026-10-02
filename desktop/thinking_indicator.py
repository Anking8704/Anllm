"""Event-driven thinking status with no background animation timer."""
from PySide6.QtWidgets import QLabel

class ThinkingIndicator(QLabel):
    """Keep the theme's status badge while avoiding periodic repaints."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('thinking')
        self.base_text = ''
        self.hide()
    
    def start(self, text='正在思考'):
        """Start the animation with given base text."""
        self.base_text = text
        self.setText(text)
        self.show()
    
    def stop(self):
        """Stop the animation and hide."""
        self.hide()
