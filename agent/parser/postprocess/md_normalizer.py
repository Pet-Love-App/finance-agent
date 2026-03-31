"""
agent/parser/postprocess/md_normalizer.py

对人工编写的 Markdown 或其他源产出的 Markdown 进行标准化清洗。
（主要用于 normalized/*.md 的质量保证）
"""
from __future__ import annotations

import re


class MarkdownNormalizer:

    def normalize(self, md: str) -> str:
        md = self._fix_heading_levels(md)
        md = self._remove_excessive_blank_lines(md)
        md = self._fix_table_format(md)
        md = self._remove_noise(md)
        return md.strip()

    def _fix_heading_levels(self, md: str) -> str:
        """确保标题层级从 # 开始，不跳级"""
        lines = md.split("\n")
        min_level = 6
        for line in lines:
            m = re.match(r'^(#{1,6})\s', line)
            if m:
                min_level = min(min_level, len(m.group(1)))
        if min_level > 1:
            offset = min_level - 1
            new_lines = []
            for line in lines:
                m = re.match(r'^(#{1,6})\s', line)
                if m:
                    new_level = max(1, len(m.group(1)) - offset)
                    line = "#" * new_level + line[len(m.group(1)):]
                new_lines.append(line)
            return "\n".join(new_lines)
        return md

    @staticmethod
    def _remove_excessive_blank_lines(md: str) -> str:
        return re.sub(r'\n{3,}', '\n\n', md)

    @staticmethod
    def _fix_table_format(md: str) -> str:
        md = re.sub(r'([^\n])\n(\|)', r'\1\n\n\2', md)
        md = re.sub(r'(\|[^\n]*\n)([^\|\n])', r'\1\n\2', md)
        return md

    @staticmethod
    def _remove_noise(md: str) -> str:
        """去掉常见噪声：页眉页脚标记、打印说明等"""
        noise_patterns = [
            r'<!-- PAGE \d+ -->',
            r'第\s*\d+\s*页\s*/?\s*共\s*\d+\s*页',
            r'打印日期[：:].+',
            r'Confidential|机密|内部文件',
        ]
        for pattern in noise_patterns:
            md = re.sub(pattern, '', md, flags=re.IGNORECASE)
        return md