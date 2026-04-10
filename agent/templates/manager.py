from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Optional, List
import json
import re

from agent.parser.router import FileRouter
from agent.parser.schema import ParsedDocument

class TemplateManager:
    def __init__(self, templates_dir: str = "data/templates"):
        # 确保模板目录路径是相对于项目根目录的
        self.templates_dir = Path(__file__).resolve().parents[2] / templates_dir
        self.router = FileRouter()
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        config_file = self.templates_dir / "templates_config.json"
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def get_template_path(self, template_name: str) -> Path:
        template_info = self.config.get(template_name, {})
        filename = template_info.get("filename", f"{template_name}.docx")
        return self.templates_dir / filename
    
    def get_field_mapping(self, template_name: str) -> Dict[str, str]:
        template_info = self.config.get(template_name, {})
        return template_info.get("field_mapping", {})
    
    def validate_template(self, template_name: str) -> Dict[str, Any]:
        try:
            # 直接使用模板名称作为文件名
            template_path = self.templates_dir / template_name
            if not template_path.exists():
                # 尝试从配置中获取
                template_info = self.config.get(template_name, {})
                filename = template_info.get("filename", template_name)
                template_path = self.templates_dir / filename
                
                if not template_path.exists():
                    return {
                        "valid": False,
                        "issues": [f"Template file not found: {template_path}"],
                        "placeholders": [],
                        "sections_count": 0,
                        "tables_count": 0,
                        "template_type": "unknown"
                    }
            
            doc = self.router.parse_file(str(template_path))
            
            placeholders = self._extract_placeholders(doc)
            
            issues = []
            if not doc.sections and not doc.tables:
                issues.append("Template is empty: no sections or tables")
            
            if not placeholders:
                issues.append("Warning: no placeholders found")
            
            return {
                "valid": len(issues) == 0,
                "issues": issues,
                "placeholders": placeholders,
                "sections_count": len(doc.sections),
                "tables_count": len(doc.tables),
                "template_type": doc.content_type
            }
            
        except Exception as e:
            return {
                "valid": False,
                "issues": [str(e)],
                "placeholders": [],
                "sections_count": 0,
                "tables_count": 0,
                "template_type": "unknown"
            }
    
    def _extract_placeholders(self, doc: ParsedDocument) -> List[str]:
        placeholders = []
        
        patterns = [
            r'\{\{([\w\u4e00-\u9fa5]+)\}\}',
            r'\[([\w\u4e00-\u9fa5]+)\]',
            r'__(([\w\u4e00-\u9fa5]+)__)'
        ]
        
        for section in doc.sections:
            for pattern in patterns:
                matches = re.findall(pattern, section.content)
                placeholders.extend(matches)
        
        for table in doc.tables:
            for row in table.rows:
                for cell in row:
                    if isinstance(cell, str):
                        for pattern in patterns:
                            matches = re.findall(pattern, cell)
                            placeholders.extend(matches)
        
        return list(set(placeholders))
    
    def preview_template(self, template_name: str) -> Dict[str, Any]:
        try:
            # 直接使用模板名称作为文件名
            template_path = self.templates_dir / template_name
            if not template_path.exists():
                # 尝试从配置中获取
                template_info = self.config.get(template_name, {})
                filename = template_info.get("filename", template_name)
                template_path = self.templates_dir / filename
                
                if not template_path.exists():
                    return {
                        "template_name": template_name,
                        "error": f"Template file not found: {template_path}"
                    }
            
            doc = self.router.parse_file(str(template_path))
            
            placeholders = self._extract_placeholders(doc)
            
            return {
                "template_name": template_name,
                "title": doc.title,
                "content_type": doc.content_type,
                "sections": [
                    {
                        "heading": s.heading,
                        "level": s.level,
                        "content_preview": s.content[:100] + "..." if len(s.content) > 100 else s.content
                    }
                    for s in doc.sections[:5]
                ],
                "tables": [
                    {
                        "table_id": t.meta.table_id if hasattr(t.meta, 'table_id') else 'unknown',
                        "headers": t.headers,
                        "row_count": len(t.rows),
                        "preview_rows": t.rows[:3] if t.rows else []
                    }
                    for t in doc.tables[:3]
                ],
                "placeholders": placeholders,
                "warnings": [w.to_dict() for w in doc.warnings],
                "errors": [e.to_dict() for e in doc.errors]
            }
        except Exception as e:
            return {
                "template_name": template_name,
                "error": str(e)
            }
    
    def list_templates(self) -> List[Dict[str, Any]]:
        templates = []
        
        # 转换生成器为列表再连接
        template_files = list(self.templates_dir.glob("*.docx")) + list(self.templates_dir.glob("*.xlsx"))
        
        for template_file in template_files:
            # 跳过临时文件和隐藏文件
            if template_file.name.startswith('~$') or template_file.name.startswith('.'):
                continue
                
            try:
                validation = self.validate_template(template_file.name)
                templates.append({
                    "name": template_file.name,
                    "path": str(template_file),
                    "type": template_file.suffix,
                    **validation
                })
            except Exception as e:
                templates.append({
                    "name": template_file.name,
                    "path": str(template_file),
                    "type": template_file.suffix,
                    "valid": False,
                    "issues": [str(e)]
                })
        
        return templates
    
    def search_templates(self, query: str) -> List[Dict[str, Any]]:
        """
        基于模板元数据模糊匹配模板
        """
        matched_templates = []
        all_templates = self.list_templates()
        
        # 转换查询为小写，进行不区分大小写的匹配
        query_lower = query.lower()
        
        for template in all_templates:
            # 检查模板名称是否匹配
            if query_lower in template.get("name", "").lower():
                matched_templates.append(template)
                continue
            
            # 检查模板类型是否匹配
            if query_lower in template.get("type", "").lower():
                matched_templates.append(template)
                continue
            
            # 检查占位符是否匹配
            placeholders = template.get("placeholders", [])
            for placeholder in placeholders:
                if isinstance(placeholder, str) and query_lower in placeholder.lower():
                    matched_templates.append(template)
                    break
        
        # 去重
        unique_templates = []
        seen_names = set()
        for template in matched_templates:
            if template.get("name") not in seen_names:
                seen_names.add(template.get("name"))
                unique_templates.append(template)
        
        return unique_templates
    
    def get_template_by_metadata(self, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        基于元数据匹配模板
        """
        all_templates = self.list_templates()
        
        for template in all_templates:
            # 检查模板类型匹配
            if "content_type" in metadata:
                if template.get("template_type") != metadata["content_type"]:
                    continue
            
            # 检查占位符匹配
            if "required_placeholders" in metadata:
                template_placeholders = set(template.get("placeholders", []))
                required_placeholders = set(metadata["required_placeholders"])
                if not required_placeholders.issubset(template_placeholders):
                    continue
            
            # 检查文件类型匹配
            if "file_type" in metadata:
                if template.get("type") != metadata["file_type"]:
                    continue
            
            return template
        
        return None
    
    def read_template(self, template_name: str) -> Optional[ParsedDocument]:
        """
        基于确定模板读取
        """
        try:
            # 直接使用模板名称作为文件名
            template_path = self.templates_dir / template_name
            if not template_path.exists():
                # 尝试从配置中获取
                template_info = self.config.get(template_name, {})
                filename = template_info.get("filename", template_name)
                template_path = self.templates_dir / filename
                
                if not template_path.exists():
                    return None
            
            return self.router.parse_file(str(template_path))
        except Exception as e:
            return None