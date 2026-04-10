"""
模板收集器 - 从指定目录收集模板文件
仿照 parser 实现，完善元数据包括归属文件夹信息
"""
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
import json
import shutil
import hashlib
from datetime import datetime

# 添加项目根目录到Python路径
repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from agent.parser.router import FileRouter
from agent.parser.schema import ParsedDocument, ParseStatus


class TemplateCollector:
    """
    模板收集器
    - 扫描源目录中的所有文件
    - 识别包含模板命名的文件
    - 复制到 templates 目录
    - 生成完整的元数据（包括归属文件夹信息）
    """
    
    # 模板关键词列表
    TEMPLATE_KEYWORDS = [
        "模板", "template", "示例", "example", "sample",
        "学生活动经费使用情况", "决算表", "核对报告", "预算表"
    ]
    
    # 支持的文件类型
    SUPPORTED_EXTENSIONS = {".docx", ".xlsx", ".pdf", ".doc", ".xls"}
    
    def __init__(
        self,
        source_dir: str = "docs/reimbursement_posted_by_teacher",
        templates_dir: str = "data/templates",
        kb_name: str = "finance"
    ):
        self.source_dir = Path(source_dir)
        self.templates_dir = Path(templates_dir)
        self.kb_name = kb_name
        self.router = FileRouter(kb_name=kb_name)
        
        # 确保目标目录存在
        self.templates_dir.mkdir(parents=True, exist_ok=True)
    
    def scan_source_directory(self) -> List[Dict[str, Any]]:
        """
        扫描源目录，识别所有文件
        返回包含完整路径和归属信息的文件列表
        """
        files_info = []
        
        if not self.source_dir.exists():
            print(f"❌ 源目录不存在: {self.source_dir}")
            return files_info
        
        # 递归扫描所有文件
        for file_path in self.source_dir.rglob("*"):
            if not file_path.is_file():
                continue
            
            # 检查文件类型
            if file_path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                continue
            
            # 计算相对路径和归属信息
            rel_path = file_path.relative_to(self.source_dir)
            parent_folders = list(rel_path.parent.parts) if rel_path.parent != Path(".") else []
            
            file_info = {
                "file_path": str(file_path),
                "relative_path": str(rel_path),
                "file_name": file_path.name,
                "file_size": file_path.stat().st_size,
                "file_extension": file_path.suffix.lower(),
                "parent_folders": parent_folders,  # 归属文件夹信息
                "folder_depth": len(parent_folders),
                "is_template": self._is_template_file(file_path),
                "collected": False,
                "collection_info": {}
            }
            
            files_info.append(file_info)
        
        return files_info
    
    def _is_template_file(self, file_path: Path) -> bool:
        """
        判断文件是否为模板文件
        """
        file_name_lower = file_path.name.lower()
        
        # 检查文件名是否包含模板关键词
        for keyword in self.TEMPLATE_KEYWORDS:
            if keyword.lower() in file_name_lower:
                return True
        
        return False
    
    def collect_templates(self, files_info: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        收集模板文件到 templates 目录
        仿照 parser 实现，生成完整的元数据
        """
        collected_templates = []
        
        for file_info in files_info:
            if not file_info["is_template"]:
                continue
            
            source_path = Path(file_info["file_path"])
            
            # 生成目标文件名（添加文件夹前缀避免冲突）
            folder_prefix = "_".join(file_info["parent_folders"]) if file_info["parent_folders"] else "root"
            target_name = f"{folder_prefix}_{source_path.name}" if folder_prefix != "root" else source_path.name
            target_path = self.templates_dir / target_name
            
            # 处理文件名冲突
            counter = 1
            original_target_name = target_name
            while target_path.exists():
                stem = Path(original_target_name).stem
                suffix = Path(original_target_name).suffix
                target_name = f"{stem}_{counter}{suffix}"
                target_path = self.templates_dir / target_name
                counter += 1
            
            try:
                # 复制文件
                shutil.copy2(source_path, target_path)
                
                # 解析文件获取元数据
                parsed_doc = self._parse_template(target_path)
                
                # 生成完整的元数据
                collection_info = {
                    "source_path": str(source_path),
                    "target_path": str(target_path),
                    "target_name": target_name,
                    "collected_at": datetime.now().isoformat(),
                    "file_hash": self._calculate_file_hash(source_path),
                    "original_name": source_path.name,
                    "folder_prefix": folder_prefix,
                    "parent_folders": file_info["parent_folders"],
                    "folder_depth": file_info["folder_depth"],
                    "source_relative_path": file_info["relative_path"],
                    # 解析元数据
                    "parsed_metadata": {
                        "doc_id": parsed_doc.doc_id if parsed_doc else "",
                        "content_type": parsed_doc.content_type if parsed_doc else "",
                        "title": parsed_doc.title if parsed_doc else "",
                        "sections_count": len(parsed_doc.sections) if parsed_doc else 0,
                        "tables_count": len(parsed_doc.tables) if parsed_doc else 0,
                        "status": parsed_doc.status if parsed_doc else "unknown",
                        "parse_duration": parsed_doc.metadata.get("parse_duration_sec", 0) if parsed_doc else 0
                    }
                }
                
                file_info["collected"] = True
                file_info["collection_info"] = collection_info
                collected_templates.append(file_info)
                
                print(f"✅ 已收集: {source_path.name}")
                print(f"   归属: {'/'.join(file_info['parent_folders']) if file_info['parent_folders'] else '根目录'}")
                print(f"   保存为: {target_name}")
                
            except Exception as e:
                print(f"❌ 收集失败: {source_path.name} - {e}")
                file_info["collection_info"] = {"error": str(e)}
        
        return collected_templates
    
    def _parse_template(self, file_path: Path) -> Optional[ParsedDocument]:
        """
        解析模板文件，仿照 parser 实现
        """
        try:
            doc = self.router.parse_file(str(file_path))
            return doc
        except Exception as e:
            print(f"⚠️  解析警告: {file_path.name} - {e}")
            return None
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """
        计算文件哈希值
        """
        try:
            with open(file_path, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return ""
    
    def generate_collection_manifest(self, all_files: List[Dict[str, Any]], collected_templates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        生成收集清单，仿照 parser 的 manifest 格式
        """
        manifest = {
            "generated_at": datetime.now().isoformat(),
            "source_directory": str(self.source_dir),
            "templates_directory": str(self.templates_dir),
            "kb_name": self.kb_name,
            "summary": {
                "total_files_scanned": len(all_files),
                "template_files_found": len([f for f in all_files if f["is_template"]]),
                "templates_collected": len([t for t in collected_templates if t.get("collected", False)]),
                "collection_errors": len([t for t in collected_templates if not t.get("collected", False)])
            },
            "folder_structure": self._analyze_folder_structure(all_files),
            "templates": [
                {
                    "file_name": t["file_name"],
                    "original_path": t["collection_info"].get("source_path", ""),
                    "target_path": t["collection_info"].get("target_path", ""),
                    "target_name": t["collection_info"].get("target_name", ""),
                    "parent_folders": t["parent_folders"],
                    "folder_depth": t["folder_depth"],
                    "file_size": t["file_size"],
                    "file_hash": t["collection_info"].get("file_hash", ""),
                    "collected_at": t["collection_info"].get("collected_at", ""),
                    "parsed_metadata": t["collection_info"].get("parsed_metadata", {})
                }
                for t in collected_templates if t.get("collected", False)
            ],
            "all_files": [
                {
                    "file_name": f["file_name"],
                    "relative_path": f["relative_path"],
                    "parent_folders": f["parent_folders"],
                    "folder_depth": f["folder_depth"],
                    "is_template": f["is_template"],
                    "file_size": f["file_size"]
                }
                for f in all_files
            ]
        }
        
        return manifest
    
    def _analyze_folder_structure(self, files_info: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        分析文件夹结构
        """
        folder_stats = {}
        
        for file_info in files_info:
            folders = file_info["parent_folders"]
            folder_path = "/".join(folders) if folders else "root"
            
            if folder_path not in folder_stats:
                folder_stats[folder_path] = {
                    "file_count": 0,
                    "template_count": 0,
                    "files": []
                }
            
            folder_stats[folder_path]["file_count"] += 1
            if file_info["is_template"]:
                folder_stats[folder_path]["template_count"] += 1
            
            folder_stats[folder_path]["files"].append(file_info["file_name"])
        
        return folder_stats
    
    def save_manifest(self, manifest: Dict[str, Any], output_path: Optional[str] = None):
        """
        保存清单文件
        """
        if output_path is None:
            output_path = self.templates_dir / "collection_manifest.json"
        
        output_path = Path(output_path)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        
        print(f"\n📋 清单已保存: {output_path}")
    
    def run(self):
        """
        运行完整的收集流程
        """
        print("=" * 60)
        print("  📂 模板收集器")
        print(f"  源目录: {self.source_dir}")
        print(f"  目标目录: {self.templates_dir}")
        print("=" * 60)
        print()
        
        # 1. 扫描源目录
        print("🔍 扫描源目录...")
        all_files = self.scan_source_directory()
        print(f"   发现 {len(all_files)} 个文件")
        print()
        
        # 2. 收集模板
        print("📥 收集模板文件...")
        collected = self.collect_templates(all_files)
        print(f"   成功收集 {len([c for c in collected if c.get('collected', False)])} 个模板")
        print()
        
        # 3. 生成清单
        print("📝 生成收集清单...")
        manifest = self.generate_collection_manifest(all_files, collected)
        self.save_manifest(manifest)
        
        # 4. 打印汇总
        print()
        print("=" * 60)
        print("  📊 收集结果汇总")
        print("=" * 60)
        print(f"  扫描文件总数: {manifest['summary']['total_files_scanned']}")
        print(f"  发现模板文件: {manifest['summary']['template_files_found']}")
        print(f"  成功收集: {manifest['summary']['templates_collected']}")
        print(f"  收集失败: {manifest['summary']['collection_errors']}")
        print("=" * 60)
        
        return manifest


if __name__ == "__main__":
    collector = TemplateCollector()
    collector.run()
