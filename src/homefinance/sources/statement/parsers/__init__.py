"""Parser registry and implementations. The registry dispatches by file
content (extension first, magic-byte fallback). Each parser is lazy-imported
so the lean install (``pip install homefinance``) never transitively loads
heavy deps such as ``docling`` or ``ofxtools``."""
