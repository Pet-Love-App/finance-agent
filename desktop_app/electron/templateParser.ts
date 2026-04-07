import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

import mammoth from "mammoth";
import * as XLSX from "xlsx";

const EXCEL_PREVIEW_MAX_ROWS = 200;
const EXCEL_PREVIEW_MAX_COLS = 60;

export type SheetPreview = {
  name: string;
  rows: string[][];
  html?: string;
};

export type TemplatePreview = {
  filePath: string;
  fileType: "xlsx" | "xls" | "docx" | "doc" | "pdf" | "unknown";
  updatedAt: string;
  textSections: string[];
  sheets: SheetPreview[];
  htmlContent?: string;
  fileUrl?: string;
  warnings: string[];
};

function extToType(filePath: string): TemplatePreview["fileType"] {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".xlsx") {
    return "xlsx";
  }
  if (ext === ".xls") {
    return "xls";
  }
  if (ext === ".docx") {
    return "docx";
  }
  if (ext === ".doc") {
    return "doc";
  }
  if (ext === ".pdf") {
    return "pdf";
  }
  return "unknown";
}

function stringifyExcelCellValue(cell: XLSX.CellObject | undefined): string {
  if (!cell) return "";
  if (typeof cell.w === "string" && cell.w.length > 0) {
    return normalizeExcelText(cell.w);
  }
  if (cell.v === null || cell.v === undefined) {
    return "";
  }
  return normalizeExcelText(String(cell.v));
}

function shouldFixMojibake(text: string): boolean {
  if (!text) return false;
  if (/[\u4e00-\u9fff]/.test(text)) return false;
  const suspiciousChars = text.match(/[À-ÿ]/g);
  if (!suspiciousChars || suspiciousChars.length < 2) {
    return false;
  }
  // Common UTF-8 mojibake fingerprints like: å¹´ä»½
  return /(?:Ã.|Â.|å.|ä.|æ.|ç.|é.|è.|ö.|ø.)/.test(text);
}

function normalizeExcelText(text: string): string {
  const source = String(text ?? "");
  if (!shouldFixMojibake(source)) {
    return source;
  }

  try {
    const repaired = Buffer.from(source, "latin1").toString("utf8");
    if (!repaired || repaired.includes("�")) {
      return source;
    }

    const repairedCjkCount = (repaired.match(/[\u4e00-\u9fff]/g) ?? []).length;
    const sourceCjkCount = (source.match(/[\u4e00-\u9fff]/g) ?? []).length;
    if (repairedCjkCount > sourceCjkCount) {
      return repaired;
    }
    return source;
  } catch {
    return source;
  }
}

function readExcel(filePath: string): { sheets: SheetPreview[]; warnings: string[] } {
  const workbook = XLSX.readFile(filePath, { cellDates: true });
  const warnings: string[] = [];

  const sheets = workbook.SheetNames.map((sheetName) => {
    const worksheet = workbook.Sheets[sheetName];
    const ref = String(worksheet["!ref"] ?? "");
    const decoded = ref ? XLSX.utils.decode_range(ref) : null;

    if (!decoded) {
      return { name: sheetName, rows: [], html: "" };
    }

    const sourceRowCount = decoded.e.r - decoded.s.r + 1;
    const sourceColCount = decoded.e.c - decoded.s.c + 1;
    const rowCount = Math.min(sourceRowCount, EXCEL_PREVIEW_MAX_ROWS);
    const colCount = Math.min(sourceColCount, EXCEL_PREVIEW_MAX_COLS);
    const normalizedRows: string[][] = [];

    for (let rowOffset = 0; rowOffset < rowCount; rowOffset += 1) {
      const row: string[] = [];
      const rowIndex = decoded.s.r + rowOffset;

      for (let colOffset = 0; colOffset < colCount; colOffset += 1) {
        const colIndex = decoded.s.c + colOffset;
        const cellAddress = XLSX.utils.encode_cell({ r: rowIndex, c: colIndex });
        row.push(stringifyExcelCellValue(worksheet[cellAddress] as XLSX.CellObject | undefined));
      }

      normalizedRows.push(row);
    }

    if (sourceRowCount > EXCEL_PREVIEW_MAX_ROWS || sourceColCount > EXCEL_PREVIEW_MAX_COLS) {
      warnings.push(
        `工作表「${sheetName}」仅展示前 ${EXCEL_PREVIEW_MAX_ROWS} 行、${EXCEL_PREVIEW_MAX_COLS} 列。`
      );
    }

    const htmlSourceRows = normalizedRows.slice(0, 120).map((row) => row.slice(0, 40));
    const html = XLSX.utils.sheet_to_html(XLSX.utils.aoa_to_sheet(htmlSourceRows));

    return { name: sheetName, rows: normalizedRows, html };
  });

  return { sheets, warnings };
}

async function readDocx(filePath: string): Promise<{ textSections: string[]; htmlContent?: string }> {
  const [rawText, htmlResult] = await Promise.all([
    mammoth.extractRawText({ path: filePath }),
    mammoth.convertToHtml({ path: filePath }),
  ]);

  const textBlocks = rawText.value
    .split(/\r?\n\r?\n/g)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 200);
  const htmlContent = String(htmlResult.value ?? "").trim();
  return {
    textSections: textBlocks,
    htmlContent: htmlContent || undefined,
  };
}

function scoreReadableText(text: string): number {
  if (!text) return 0;
  const cjk = (text.match(/[\u4e00-\u9fff]/g) ?? []).length;
  const asciiWord = (text.match(/[A-Za-z]/g) ?? []).length;
  const digits = (text.match(/\d/g) ?? []).length;
  const control = (text.match(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g) ?? []).length;
  return cjk * 2 + asciiWord + digits - control * 4;
}

function toTextSectionsFromRaw(raw: string): string[] {
  const normalized = String(raw ?? "")
    .replace(/\u0000/g, " ")
    .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, "\n")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n");

  const chunks = normalized
    .split(/\n{1,}/g)
    .map((item) => item.replace(/\s+/g, " ").trim())
    .filter((item) => item.length >= 4);

  const deduped: string[] = [];
  const seen = new Set<string>();
  for (const item of chunks) {
    const key = item.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    deduped.push(item);
    if (deduped.length >= 260) break;
  }
  return deduped;
}

function readLegacyDoc(filePath: string): { textSections: string[]; warnings: string[] } {
  const warnings: string[] = [];
  const buffer = fs.readFileSync(filePath);
  const candidates = [buffer.toString("utf8"), buffer.toString("utf16le"), buffer.toString("latin1")];
  let bestRaw = "";
  let bestScore = -Infinity;

  for (const candidate of candidates) {
    const score = scoreReadableText(candidate);
    if (score > bestScore) {
      bestScore = score;
      bestRaw = candidate;
    }
  }

  const sections = toTextSectionsFromRaw(bestRaw);
  if (sections.length === 0) {
    warnings.push("`.doc` 为旧版 Word 二进制格式，未提取到可比对文本，建议另存为 `.docx`。");
  } else {
    warnings.push("`.doc` 已使用兼容模式提取文本，可能与原排版存在差异。");
  }
  return { textSections: sections, warnings };
}

export async function parseTemplate(filePath: string): Promise<TemplatePreview> {
  const fileType = extToType(filePath);
  const stat = fs.statSync(filePath);
  const warnings: string[] = [];

  const base: TemplatePreview = {
    filePath,
    fileType,
    updatedAt: stat.mtime.toISOString(),
    textSections: [],
    sheets: [],
    htmlContent: undefined,
    fileUrl: undefined,
    warnings,
  };

  if (fileType === "xlsx" || fileType === "xls") {
    const excel = readExcel(filePath);
    base.sheets = excel.sheets;
    base.warnings.push(...excel.warnings);
    return base;
  }

  if (fileType === "docx") {
    const docx = await readDocx(filePath);
    base.textSections = docx.textSections;
    base.htmlContent = docx.htmlContent;
    return base;
  }

  if (fileType === "doc") {
    const legacy = readLegacyDoc(filePath);
    base.textSections = legacy.textSections;
    base.warnings.push(...legacy.warnings);
    return base;
  }

  if (fileType === "pdf") {
    base.fileUrl = pathToFileURL(filePath).toString();
    return base;
  }

  warnings.push("当前仅支持 xlsx/xls/docx/doc/pdf 预览。");
  return base;
}
