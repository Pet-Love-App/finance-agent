from __future__ import annotations

import re
from pathlib import Path
from typing import Any, List, Dict

from agent.parser.base import BaseParser
from agent.parser.schema import (
    ParsedDocument, TableBlock, TableMeta, Section, 
    Warning, Error, Loc, LocType
)

class TemplateParser(BaseParser):
    supported_extensions = [".docx", ".xlsx"]
    
    def __init__(self, kb_name: str = ""):
        self.kb_name = kb_name
        self.placeholder_patterns = [
            r'\{\{([\w\u4e00-\u9fa5]+)\}\}',
            r'\[([\w\u4e00-\u9fa5]+)\]',
            r'__(([\w\u4e00-\u9fa5]+)__)'
        ]
    
    def parse(self, file_path: str, **kwargs) -> ParsedDocument:
        from agent.parser.router import FileRouter
        
        router = FileRouter(kb_name=self.kb_name)
        base_doc = router.parse_file(file_path)
        
        template_info = self._extract_template_info(base_doc)
        
        base_doc.metadata.update({
            "template_type": self._detect_template_type(base_doc),
            "placeholders": template_info["placeholders"],
            "field_mapping": template_info["field_mapping"],
            "validation_rules": template_info["validation_rules"],
            "structure_preserved": True
        })
        
        return base_doc
    
    def _extract_template_info(self, doc: ParsedDocument) -> Dict[str, Any]:
        placeholders = []
        field_mapping = {}
        validation_rules = {}
        
        for section in doc.sections:
            found = self._find_placeholders(section.content)
            placeholders.extend(found)
        
        for table in doc.tables:
            for row in table.rows:
                for cell in row:
                    if isinstance(cell, str):
                        found = self._find_placeholders(cell)
                        placeholders.extend(found)
        
        for placeholder in placeholders:
            field_name = self._normalize_field_name(placeholder)
            field_mapping[field_name] = placeholder
        
        return {
            "placeholders": list(set(placeholders)),
            "field_mapping": field_mapping,
            "validation_rules": validation_rules
        }
    
    def _find_placeholders(self, text: str) -> List[str]:
        found = []
        for pattern in self.placeholder_patterns:
            matches = re.findall(pattern, text)
            found.extend(matches)
        return found
    
    def _normalize_field_name(self, placeholder: str) -> str:
        mapping = {
            "经办人姓名": "student_name",
            "经办人联系方式": "contact",
            "活动时间": "activity_time",
            "活动地点": "location",
            "参与人员": "participants",
            "活动主要内容": "description",
            "报销内容及金额": "expense_detail"
        }
        return mapping.get(placeholder, placeholder.lower())
    
    def _detect_template_type(self, doc: ParsedDocument) -> str:
        if doc.content_type == "word":
            return "word_template"
        elif doc.content_type == "excel":
            return "excel_template"
        return "unknown"