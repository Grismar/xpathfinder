"""
xpathfinder package
"""
__version__ = "0.1.0"

# Expose key classes and functions at package level
from .cli import main
from .app import XPathFinderApp
from .xml_utils import parse_xml, apply_xpath, pretty_print, Document, Node
from .history import HistoryManager
from .llm import LLMClient

__all__ = [
    "main",
    "XPathFinderApp",
    "parse_xml", "apply_xpath", "pretty_print",
    "Document", "Node",
    "HistoryManager",
    "LLMClient",
    "__version__"
]
