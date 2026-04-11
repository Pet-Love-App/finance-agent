import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Card, Input, InputNumber, Select, Space, Spin, Switch, Typography } from "antd";

import type { TemplatePreview } from "../types/preview";

type CompareFileEntry = {
  path: string;
  name: string;
  ext: string;
  size: number;
  updatedAt: string;
};

type SheetDiffResult = {
  name: string;
  maxRows: number;
  maxCols: number;
  mismatchKeys: Set<string>;
  mismatchCount: number;
};

type TextDiffResult = {
  maxLines: number;
  mismatchIndexes: Set<number>;
  mismatchCount: number;
};

type CompareMode = "excel" | "doc" | "unsupported" | "none";

type CheckStatus = "matched" | "mismatch" | "warning";

type ProcessCheckItem = {
  key: string;
  label: string;
  status: CheckStatus;
  rule: string;
  budgetValue: string;
  finalValue: string;
  detail: string;
};

type ExtractedProfile = {
  keyValues: Record<string, string>;
  totalAmount: number | null;
  lineItems: Array<{ name: string; amount: number | null }>;
};

type RuleConfig = {
  amountTolerance: number;
  lineItemAmountTolerance: number;
  allowSameMonthForDate: boolean;
  requireApplicantMatch: boolean;
  requireDepartmentMatch: boolean;
  enableFuzzyLineItemName: boolean;
  fuzzyNameMinSimilarity: number;
};

type RuleTemplate = {
  id: string;
  name: string;
  config: RuleConfig;
  updatedAt: string;
};

const { Title, Text } = Typography;
const DEFAULT_RULE_CONFIG: RuleConfig = {
  amountTolerance: 0,
  lineItemAmountTolerance: 0,
  allowSameMonthForDate: true,
  requireApplicantMatch: true,
  requireDepartmentMatch: true,
  enableFuzzyLineItemName: true,
  fuzzyNameMinSimilarity: 0.72,
};
const RULE_TEMPLATE_STORAGE_KEY = "compare_rule_templates_v1";

function normalizeCell(text: string): string {
  return String(text ?? "").replace(/\s+/g, " ").trim();
}

function parseNumericCell(text: string): number | null {
  const normalized = normalizeCell(text).replace(/,/g, "").replace(/[￥¥]/g, "");
  if (!normalized) return null;

  if (/%$/.test(normalized)) {
    const base = Number(normalized.slice(0, -1));
    return Number.isFinite(base) ? base / 100 : null;
  }

  const value = Number(normalized);
  return Number.isFinite(value) ? value : null;
}

function equalsCell(left: string, right: string): boolean {
  const leftNum = parseNumericCell(left);
  const rightNum = parseNumericCell(right);
  if (leftNum !== null && rightNum !== null) {
    return Math.abs(leftNum - rightNum) < 1e-9;
  }
  return normalizeCell(left) === normalizeCell(right);
}

function findSheet(preview: TemplatePreview | null, sheetName: string): string[][] {
  if (!preview) return [];
  return preview.sheets.find((sheet) => sheet.name === sheetName)?.rows ?? [];
}

function buildDocBlocks(preview: TemplatePreview | null): string[] {
  if (!preview) return [];
  const blocks = (preview.textSections ?? [])
    .map((item) => normalizeCell(item))
    .filter(Boolean);
  return blocks.slice(0, 320);
}

function collectPreviewLines(preview: TemplatePreview | null): string[] {
  if (!preview) return [];
  if (preview.fileType === "xlsx" || preview.fileType === "xls") {
    const lines: string[] = [];
    for (const sheet of preview.sheets) {
      for (const row of sheet.rows) {
        const cells = row.map((item) => normalizeCell(item)).filter(Boolean);
        if (cells.length === 0) continue;
        lines.push(cells.join(" | "));
      }
    }
    return lines.slice(0, 1500);
  }
  return buildDocBlocks(preview);
}

function normalizeKeyName(text: string): string {
  const key = normalizeCell(text);
  if (!key) return "";
  if (/活动名称|项目名称|报销事项|活动主题/.test(key)) return "activity";
  if (/报销人|申请人|经办人|负责人/.test(key)) return "applicant";
  if (/部门|院系|单位/.test(key)) return "department";
  if (/日期|时间|发生日期|活动日期/.test(key)) return "date";
  if (/预算总额|预算合计|预算金额|预算总计/.test(key)) return "budget_total";
  if (/决算总额|决算合计|实际支出|报销金额|实际金额/.test(key)) return "final_total";
  if (/总额|合计|总计/.test(key)) return "total";
  return key;
}

function extractKeyValues(lines: string[]): Record<string, string> {
  const keyValues: Record<string, string> = {};
  for (const line of lines) {
    const text = normalizeCell(line);
    if (!text) continue;
    const byColon = text.match(/^([^:：|]{2,30})[:：]\s*(.+)$/);
    if (byColon) {
      const key = normalizeKeyName(byColon[1]);
      const value = normalizeCell(byColon[2]).slice(0, 120);
      if (key && value && !keyValues[key]) {
        keyValues[key] = value;
      }
      continue;
    }
    const byPipe = text.split("|").map((item) => normalizeCell(item));
    if (byPipe.length >= 2) {
      const key = normalizeKeyName(byPipe[0]);
      const value = byPipe[1];
      if (key && value && !keyValues[key]) {
        keyValues[key] = value;
      }
    }
  }
  return keyValues;
}

function extractLineItems(lines: string[]): Array<{ name: string; amount: number | null }> {
  const items: Array<{ name: string; amount: number | null }> = [];
  for (const line of lines) {
    const text = normalizeCell(line);
    if (!text) continue;
    const parts = text.split("|").map((item) => normalizeCell(item)).filter(Boolean);
    if (parts.length < 2) continue;
    const amountCandidate = parts.find((part) => parseNumericCell(part) !== null);
    if (!amountCandidate) continue;
    const amount = parseNumericCell(amountCandidate);
    const name = parts[0].replace(/^[-*•\d.\s]+/, "").trim();
    if (!name || name.length > 40) continue;
    if (/合计|总计|总额|小计/.test(name)) continue;
    items.push({ name, amount });
    if (items.length >= 120) break;
  }
  return items;
}

function extractTotalAmount(lines: string[], keyValues: Record<string, string>, role: "budget" | "final"): number | null {
  const candidates: number[] = [];
  const directKeys =
    role === "budget" ? ["budget_total", "total"] : ["final_total", "total"];
  for (const key of directKeys) {
    const value = keyValues[key];
    const parsed = value ? parseNumericCell(value) : null;
    if (parsed !== null) candidates.push(parsed);
  }

  const rolePattern =
    role === "budget"
      ? /(预算总额|预算合计|预算金额|预算总计|合计|总计)/
      : /(决算总额|决算合计|实际支出|报销金额|实际金额|合计|总计)/;

  for (const line of lines) {
    if (!rolePattern.test(line)) continue;
    const numericMatches = line.match(/[-+]?\d[\d,]*(?:\.\d+)?/g) ?? [];
    for (const matched of numericMatches) {
      const value = parseNumericCell(matched);
      if (value !== null) {
        candidates.push(value);
      }
    }
  }

  if (candidates.length === 0) return null;
  return Math.max(...candidates);
}

function buildProfile(preview: TemplatePreview | null, role: "budget" | "final"): ExtractedProfile {
  const lines = collectPreviewLines(preview);
  const keyValues = extractKeyValues(lines);
  const lineItems = extractLineItems(lines);
  const totalAmount = extractTotalAmount(lines, keyValues, role);
  return {
    keyValues,
    totalAmount,
    lineItems,
  };
}

function getProfileValue(profile: ExtractedProfile, keys: string[]): string {
  for (const key of keys) {
    const value = profile.keyValues[key];
    if (value) return value;
  }
  return "";
}

function parseDateParts(value: string): { year: number; month: number; day: number } | null {
  const text = normalizeCell(value);
  if (!text) return null;
  const match = text.match(/(20\d{2})[^\d]{0,3}(\d{1,2})[^\d]{0,3}(\d{1,2})?/);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3] ?? "1");
  if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) return null;
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  return { year, month, day };
}

function isDateMatched(budgetValue: string, finalValue: string, allowSameMonthForDate: boolean): boolean {
  const budgetDate = parseDateParts(budgetValue);
  const finalDate = parseDateParts(finalValue);
  if (!budgetDate || !finalDate) {
    return normalizeCell(budgetValue) === normalizeCell(finalValue);
  }
  if (budgetDate.year === finalDate.year && budgetDate.month === finalDate.month && budgetDate.day === finalDate.day) {
    return true;
  }
  if (allowSameMonthForDate && budgetDate.year === finalDate.year && budgetDate.month === finalDate.month) {
    return true;
  }
  return false;
}

function simpleSimilarity(left: string, right: string): number {
  const a = normalizeCell(left);
  const b = normalizeCell(right);
  if (!a || !b) return 0;
  if (a === b) return 1;
  const setA = new Set(a);
  const setB = new Set(b);
  let intersection = 0;
  for (const token of setA) {
    if (setB.has(token)) intersection += 1;
  }
  const union = new Set([...setA, ...setB]).size;
  return union === 0 ? 0 : intersection / union;
}

function compareFieldItem(
  key: string,
  label: string,
  rule: string,
  budgetValue: string,
  finalValue: string,
  matcher?: (budget: string, final: string) => boolean
): ProcessCheckItem {
  if (!budgetValue || !finalValue) {
    return {
      key,
      label,
      status: "warning",
      rule,
      budgetValue: budgetValue || "(未识别)",
      finalValue: finalValue || "(未识别)",
      detail: "任一侧未识别到该字段，建议人工复核。",
    };
  }
  const matched = matcher ? matcher(budgetValue, finalValue) : normalizeCell(budgetValue) === normalizeCell(finalValue);
  return {
    key,
    label,
    status: matched ? "matched" : "mismatch",
    rule,
    budgetValue,
    finalValue,
    detail: matched ? "字段一致。" : "字段值不一致，请核对表内基础信息。",
  };
}

function buildLineItemSummary(budget: ExtractedProfile, final: ExtractedProfile, config: RuleConfig): ProcessCheckItem {
  const budgetMap = new Map<string, number | null>();
  for (const item of budget.lineItems) {
    const key = normalizeCell(item.name);
    if (!key) continue;
    budgetMap.set(key, item.amount);
  }

  let missingCount = 0;
  let exceedCount = 0;
  let comparableCount = 0;

  const findBudgetAmount = (name: string): number | null | undefined => {
    const normalized = normalizeCell(name);
    if (budgetMap.has(normalized)) {
      return budgetMap.get(normalized);
    }
    if (!config.enableFuzzyLineItemName) {
      return undefined;
    }
    let bestKey = "";
    let bestScore = 0;
    for (const key of budgetMap.keys()) {
      const score = simpleSimilarity(normalized, key);
      if (score > bestScore) {
        bestScore = score;
        bestKey = key;
      }
    }
    if (bestKey && bestScore >= config.fuzzyNameMinSimilarity) {
      return budgetMap.get(bestKey);
    }
    return undefined;
  };

  for (const item of final.lineItems) {
    if (!normalizeCell(item.name)) continue;
    const budgetAmount = findBudgetAmount(item.name);
    if (budgetAmount === undefined) {
      missingCount += 1;
      continue;
    }
    if (budgetAmount === null || item.amount === null) continue;
    comparableCount += 1;
    if (item.amount > budgetAmount + config.lineItemAmountTolerance + 1e-9) {
      exceedCount += 1;
    }
  }

  const status: CheckStatus =
    missingCount === 0 && exceedCount === 0
      ? "matched"
      : comparableCount === 0 && budget.lineItems.length === 0 && final.lineItems.length === 0
        ? "warning"
        : "mismatch";

  return {
    key: "line_items",
    label: "费用明细项匹配",
    status,
    rule: `决算项应在预算项中存在，且对应金额不应超过预算金额（容差 ${config.lineItemAmountTolerance.toFixed(2)}）`,
    budgetValue: `预算明细 ${budget.lineItems.length} 项`,
    finalValue: `决算明细 ${final.lineItems.length} 项`,
    detail:
      status === "matched"
        ? "明细项匹配且金额未超预算。"
        : status === "warning"
          ? "两侧未识别出结构化明细，建议人工复核。"
          : `存在 ${missingCount} 项决算明细未在预算中找到，${exceedCount} 项金额超预算。`,
  };
}

function buildAmountSummary(budget: ExtractedProfile, final: ExtractedProfile, config: RuleConfig): ProcessCheckItem {
  if (budget.totalAmount === null || final.totalAmount === null) {
    return {
      key: "total_amount",
      label: "总金额规则核对",
      status: "warning",
      rule: `决算总额应小于或等于预算总额（容差 ${config.amountTolerance.toFixed(2)}）`,
      budgetValue: budget.totalAmount === null ? "(未识别)" : String(budget.totalAmount),
      finalValue: final.totalAmount === null ? "(未识别)" : String(final.totalAmount),
      detail: "未能识别其中一侧总额，建议人工复核。",
    };
  }

  const matched = final.totalAmount <= budget.totalAmount + config.amountTolerance + 1e-9;
  return {
    key: "total_amount",
    label: "总金额规则核对",
    status: matched ? "matched" : "mismatch",
    rule: `决算总额应小于或等于预算总额（容差 ${config.amountTolerance.toFixed(2)}）`,
    budgetValue: budget.totalAmount.toFixed(2),
    finalValue: final.totalAmount.toFixed(2),
    detail: matched
      ? "总额符合规则。"
      : `决算总额超出预算 ${(final.totalAmount - budget.totalAmount - config.amountTolerance).toFixed(2)}（已扣除容差）。`,
  };
}

function buildProcessChecks(
  finalPreview: TemplatePreview | null,
  budgetPreview: TemplatePreview | null,
  config: RuleConfig
): ProcessCheckItem[] {
  if (!finalPreview || !budgetPreview) return [];
  const budgetProfile = buildProfile(budgetPreview, "budget");
  const finalProfile = buildProfile(finalPreview, "final");

  const applicantBudget = getProfileValue(budgetProfile, ["applicant"]);
  const applicantFinal = getProfileValue(finalProfile, ["applicant"]);
  const departmentBudget = getProfileValue(budgetProfile, ["department"]);
  const departmentFinal = getProfileValue(finalProfile, ["department"]);

  const applicantCheck = config.requireApplicantMatch
    ? compareFieldItem("applicant", "报销人/申请人", "经办主体应一致", applicantBudget, applicantFinal)
    : {
        key: "applicant",
        label: "报销人/申请人",
        status: "warning" as const,
        rule: "当前配置为提示项（不参与强校验）",
        budgetValue: applicantBudget || "(未识别)",
        finalValue: applicantFinal || "(未识别)",
        detail: "该字段未启用强制匹配，仅提示查看。",
      };

  const departmentCheck = config.requireDepartmentMatch
    ? compareFieldItem("department", "部门/单位", "归属部门应一致", departmentBudget, departmentFinal)
    : {
        key: "department",
        label: "部门/单位",
        status: "warning" as const,
        rule: "当前配置为提示项（不参与强校验）",
        budgetValue: departmentBudget || "(未识别)",
        finalValue: departmentFinal || "(未识别)",
        detail: "该字段未启用强制匹配，仅提示查看。",
      };

  const checks: ProcessCheckItem[] = [
    compareFieldItem(
      "activity",
      "活动/报销事项",
      "决算表与预算表的活动名称或报销事项应一致",
      getProfileValue(budgetProfile, ["activity"]),
      getProfileValue(finalProfile, ["activity"])
    ),
    applicantCheck,
    departmentCheck,
    compareFieldItem(
      "date",
      "活动日期",
      config.allowSameMonthForDate ? "活动日期应一致或在同一月份内" : "活动日期应严格一致",
      getProfileValue(budgetProfile, ["date"]),
      getProfileValue(finalProfile, ["date"]),
      (budgetValue, finalValue) => isDateMatched(budgetValue, finalValue, config.allowSameMonthForDate)
    ),
    buildAmountSummary(budgetProfile, finalProfile, config),
    buildLineItemSummary(budgetProfile, finalProfile, config),
  ];

  return checks;
}

function buildWorkbookDiff(finalPreview: TemplatePreview | null, budgetPreview: TemplatePreview | null): SheetDiffResult[] {
  if (!finalPreview || !budgetPreview) return [];
  if (!["xlsx", "xls"].includes(finalPreview.fileType) || !["xlsx", "xls"].includes(budgetPreview.fileType)) {
    return [];
  }

  const sheetNames = new Set<string>([
    ...finalPreview.sheets.map((sheet) => sheet.name),
    ...budgetPreview.sheets.map((sheet) => sheet.name),
  ]);

  const result: SheetDiffResult[] = [];
  for (const sheetName of sheetNames) {
    const finalRows = findSheet(finalPreview, sheetName);
    const budgetRows = findSheet(budgetPreview, sheetName);
    const maxRows = Math.max(finalRows.length, budgetRows.length);
    const maxCols = Math.max(
      finalRows.reduce((max, row) => Math.max(max, row.length), 0),
      budgetRows.reduce((max, row) => Math.max(max, row.length), 0)
    );

    const mismatchKeys = new Set<string>();
    for (let rowIndex = 0; rowIndex < maxRows; rowIndex += 1) {
      for (let colIndex = 0; colIndex < maxCols; colIndex += 1) {
        const finalCell = finalRows[rowIndex]?.[colIndex] ?? "";
        const budgetCell = budgetRows[rowIndex]?.[colIndex] ?? "";
        if (!equalsCell(finalCell, budgetCell)) {
          mismatchKeys.add(`${rowIndex}:${colIndex}`);
        }
      }
    }

    result.push({
      name: sheetName,
      maxRows,
      maxCols,
      mismatchKeys,
      mismatchCount: mismatchKeys.size,
    });
  }

  return result.sort((a, b) => b.mismatchCount - a.mismatchCount || a.name.localeCompare(b.name, "zh-Hans-CN"));
}

function buildDocumentDiff(finalPreview: TemplatePreview | null, budgetPreview: TemplatePreview | null): TextDiffResult {
  const finalBlocks = buildDocBlocks(finalPreview);
  const budgetBlocks = buildDocBlocks(budgetPreview);
  const maxLines = Math.max(finalBlocks.length, budgetBlocks.length);
  const mismatchIndexes = new Set<number>();

  for (let index = 0; index < maxLines; index += 1) {
    const left = finalBlocks[index] ?? "";
    const right = budgetBlocks[index] ?? "";
    if (!equalsCell(left, right)) {
      mismatchIndexes.add(index);
    }
  }

  return {
    maxLines,
    mismatchIndexes,
    mismatchCount: mismatchIndexes.size,
  };
}

function detectCompareMode(finalPreview: TemplatePreview | null, budgetPreview: TemplatePreview | null): CompareMode {
  if (!finalPreview || !budgetPreview) return "none";
  const excelTypes = new Set(["xlsx", "xls"]);
  const docTypes = new Set(["doc", "docx"]);

  if (excelTypes.has(finalPreview.fileType) && excelTypes.has(budgetPreview.fileType)) {
    return "excel";
  }
  if (docTypes.has(finalPreview.fileType) && docTypes.has(budgetPreview.fileType)) {
    return "doc";
  }
  return "unsupported";
}

function toExcelColumnLabel(index: number): string {
  let current = index + 1;
  let label = "";
  while (current > 0) {
    const remainder = (current - 1) % 26;
    label = String.fromCharCode(65 + remainder) + label;
    current = Math.floor((current - 1) / 26);
  }
  return label;
}

function renderSheetTable(
  title: string,
  preview: TemplatePreview | null,
  sheetDiff: SheetDiffResult | null
) {
  if (!preview) {
    return <div className="compare-empty">请选择文件并开始核对</div>;
  }

  if (!["xlsx", "xls"].includes(preview.fileType)) {
    return <div className="compare-empty">当前文件不是 Excel，暂不支持单元格高亮。</div>;
  }

  const rows = findSheet(preview, sheetDiff?.name ?? preview.sheets[0]?.name ?? "");
  const maxRows = sheetDiff?.maxRows ?? rows.length;
  const maxCols = sheetDiff?.maxCols ?? rows.reduce((max, row) => Math.max(max, row.length), 0);
  const mismatches = sheetDiff?.mismatchKeys ?? new Set<string>();

  return (
    <Card size="small" className="compare-pane-card" title={title}>
      <div className="compare-table-wrap">
        <table className="excel-preview-table compare-table">
          <thead>
            <tr>
              <th className="excel-index-cell">#</th>
              {Array.from({ length: maxCols }, (_, index) => (
                <th key={`head-${index}`}>{toExcelColumnLabel(index)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: maxRows }, (_, rowIndex) => (
              <tr key={`row-${rowIndex}`}>
                <th className="excel-row-index">{rowIndex + 1}</th>
                {Array.from({ length: maxCols }, (_, colIndex) => {
                  const key = `${rowIndex}:${colIndex}`;
                  const value = rows[rowIndex]?.[colIndex] ?? "";
                  const mismatch = mismatches.has(key);
                  return (
                    <td key={key} className={mismatch ? "compare-cell-mismatch" : undefined} title={mismatch ? "该单元格不匹配" : ""}>
                      <span className="excel-cell-text">{value || "∅"}</span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function renderDocTable(title: string, preview: TemplatePreview | null, textDiff: TextDiffResult) {
  if (!preview) {
    return <div className="compare-empty">请选择文件并开始核对</div>;
  }
  const blocks = buildDocBlocks(preview);
  const maxLines = Math.max(textDiff.maxLines, blocks.length);

  return (
    <Card size="small" className="compare-pane-card" title={title}>
      <div className="compare-doc-wrap">
        {maxLines === 0 ? (
          <div className="compare-empty">未解析到可比较文本，建议将文档另存为 `.docx` 后重试。</div>
        ) : (
          <div className="compare-doc-list">
            {Array.from({ length: maxLines }, (_, index) => {
              const mismatch = textDiff.mismatchIndexes.has(index);
              const value = blocks[index] ?? "";
              return (
                <div key={`doc-line-${index}`} className={`compare-doc-line ${mismatch ? "compare-doc-line-mismatch" : ""}`}>
                  <span className="compare-doc-index">{index + 1}</span>
                  <span className="compare-doc-text">{value || "∅"}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </Card>
  );
}

function renderGenericPreview(title: string, preview: TemplatePreview | null) {
  if (!preview) {
    return <div className="compare-empty">请选择文件并开始核对</div>;
  }

  if (preview.fileType === "xlsx" || preview.fileType === "xls") {
    const sheet = preview.sheets[0];
    const rows = sheet?.rows ?? [];
    const maxRows = Math.min(rows.length, 120);
    const maxCols = Math.min(rows.reduce((max, row) => Math.max(max, row.length), 0), 36);

    return (
      <Card size="small" className="compare-pane-card" title={`${title}${sheet ? `（${sheet.name}）` : ""}`}>
        <div className="compare-table-wrap">
          {maxRows === 0 || maxCols === 0 ? (
            <div className="compare-empty">未解析到可预览内容</div>
          ) : (
            <table className="excel-preview-table compare-table">
              <thead>
                <tr>
                  <th className="excel-index-cell">#</th>
                  {Array.from({ length: maxCols }, (_, index) => (
                    <th key={`head-${index}`}>{toExcelColumnLabel(index)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Array.from({ length: maxRows }, (_, rowIndex) => (
                  <tr key={`row-${rowIndex}`}>
                    <th className="excel-row-index">{rowIndex + 1}</th>
                    {Array.from({ length: maxCols }, (_, colIndex) => {
                      const value = rows[rowIndex]?.[colIndex] ?? "";
                      return (
                        <td key={`${rowIndex}:${colIndex}`}>
                          <span className="excel-cell-text">{value || "∅"}</span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </Card>
    );
  }

  if (preview.fileType === "pdf") {
    return (
      <Card size="small" className="compare-pane-card" title={title}>
        <div className="compare-doc-wrap">
          {preview.fileUrl ? (
            <iframe
              className="pdf-preview-frame"
              src={`${preview.fileUrl}#page=1&zoom=110`}
              title={preview.filePath}
            />
          ) : (
            <div className="compare-empty">当前 PDF 无法内嵌显示，请使用系统应用打开。</div>
          )}
        </div>
      </Card>
    );
  }

  const blocks = buildDocBlocks(preview);
  return (
    <Card size="small" className="compare-pane-card" title={title}>
      <div className="compare-doc-wrap">
        {blocks.length === 0 ? (
          <div className="compare-empty">未解析到可比较文本</div>
        ) : (
          <div className="compare-doc-list">
            {blocks.map((value, index) => (
              <div key={`doc-line-${index}`} className="compare-doc-line">
                <span className="compare-doc-index">{index + 1}</span>
                <span className="compare-doc-text">{value || "∅"}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}

export function CompareWindow() {
  const bridge = window.templateApi;
  const [boundDir, setBoundDir] = useState<string>("");
  const [files, setFiles] = useState<CompareFileEntry[]>([]);
  const [finalFilePath, setFinalFilePath] = useState<string>("");
  const [budgetFilePath, setBudgetFilePath] = useState<string>("");
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string>("");
  const [finalPreview, setFinalPreview] = useState<TemplatePreview | null>(null);
  const [budgetPreview, setBudgetPreview] = useState<TemplatePreview | null>(null);
  const [activeSheet, setActiveSheet] = useState<string>("");
  const [ruleConfig, setRuleConfig] = useState<RuleConfig>(DEFAULT_RULE_CONFIG);
  const [ruleTemplates, setRuleTemplates] = useState<RuleTemplate[]>([]);
  const [selectedRuleTemplateId, setSelectedRuleTemplateId] = useState<string>("");
  const [ruleTemplateName, setRuleTemplateName] = useState<string>("默认模板");

  const fileOptions = useMemo(
    () =>
      files.map((file) => ({
        label: file.name,
        value: file.path,
      })),
    [files]
  );
  const ruleTemplateOptions = useMemo(
    () =>
      ruleTemplates.map((item) => ({
        label: `${item.name}（${new Date(item.updatedAt).toLocaleDateString()}）`,
        value: item.id,
      })),
    [ruleTemplates]
  );

  const diffBySheet = useMemo(() => buildWorkbookDiff(finalPreview, budgetPreview), [finalPreview, budgetPreview]);
  const compareMode = useMemo(() => detectCompareMode(finalPreview, budgetPreview), [finalPreview, budgetPreview]);
  const docDiff = useMemo(() => buildDocumentDiff(finalPreview, budgetPreview), [finalPreview, budgetPreview]);
  const processChecks = useMemo(
    () => buildProcessChecks(finalPreview, budgetPreview, ruleConfig),
    [finalPreview, budgetPreview, ruleConfig]
  );
  const checkStats = useMemo(() => {
    const matched = processChecks.filter((item) => item.status === "matched").length;
    const mismatch = processChecks.filter((item) => item.status === "mismatch").length;
    const warning = processChecks.filter((item) => item.status === "warning").length;
    return { matched, mismatch, warning, total: processChecks.length };
  }, [processChecks]);
  const totalMismatch = useMemo(() => {
    if (compareMode === "excel") {
      return diffBySheet.reduce((sum, item) => sum + item.mismatchCount, 0);
    }
    if (compareMode === "doc") {
      return docDiff.mismatchCount;
    }
    return 0;
  }, [compareMode, diffBySheet, docDiff.mismatchCount]);
  const parseSummary = useMemo(() => {
    const toSummary = (label: string, preview: TemplatePreview | null) => {
      if (!preview) return `${label}: 未解析`;
      return `${label}: ${preview.fileType} / sheets=${preview.sheets.length} / text=${preview.textSections.length}`;
    };
    return `${toSummary("决算", finalPreview)}；${toSummary("预算", budgetPreview)}`;
  }, [finalPreview, budgetPreview]);
  const activeSheetDiff = useMemo(
    () => diffBySheet.find((item) => item.name === activeSheet) ?? diffBySheet[0] ?? null,
    [diffBySheet, activeSheet]
  );

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(RULE_TEMPLATE_STORAGE_KEY);
      if (!raw) {
        return;
      }
      const parsed = JSON.parse(raw) as RuleTemplate[];
      if (!Array.isArray(parsed)) {
        return;
      }
      const normalized = parsed
        .filter((item) => item && typeof item === "object" && item.id && item.name && item.config)
        .map((item) => ({
          id: String(item.id),
          name: String(item.name),
          updatedAt: String(item.updatedAt || new Date().toISOString()),
          config: {
            ...DEFAULT_RULE_CONFIG,
            ...item.config,
          },
        }));
      setRuleTemplates(normalized);
      if (normalized.length > 0) {
        setSelectedRuleTemplateId(normalized[0].id);
        setRuleTemplateName(normalized[0].name);
      }
    } catch {
      // ignore local storage parse errors
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(RULE_TEMPLATE_STORAGE_KEY, JSON.stringify(ruleTemplates));
    } catch {
      // ignore local storage write errors
    }
  }, [ruleTemplates]);

  const loadBoundFiles = async () => {
    if (!bridge) return;
    setLoadingFiles(true);
    setError("");
    try {
      const dir = await bridge.getCompareBoundDir?.();
      if (dir) {
        setBoundDir(dir);
      }
      const listed = await bridge.listCompareBoundFiles?.();
      if (!listed?.ok) {
        setError(listed?.error || "读取绑定目录文件失败");
        return;
      }
      const fetchedFiles = listed.files ?? [];
      setFiles(fetchedFiles);
      setBoundDir(listed.dir || dir || "");
      if (!finalFilePath) {
        const finalCandidate = fetchedFiles.find((item) => /决算|final/i.test(item.name));
        if (finalCandidate) setFinalFilePath(finalCandidate.path);
      }
      if (!budgetFilePath) {
        const budgetCandidate = fetchedFiles.find((item) => /预算|budget/i.test(item.name));
        if (budgetCandidate) setBudgetFilePath(budgetCandidate.path);
      }
    } finally {
      setLoadingFiles(false);
    }
  };

  useEffect(() => {
    void loadBoundFiles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pickBoundDir = async () => {
    if (!bridge?.pickCompareBoundDir) return;
    const selected = await bridge.pickCompareBoundDir();
    if (!selected?.ok || !selected.dir) {
      if (selected?.error) {
        setError(selected.error);
      }
      return;
    }
    setBoundDir(selected.dir);
    await bridge.setCompareBoundDir?.(selected.dir);
    await loadBoundFiles();
  };

  const pickUploadFile = async (role: "final" | "budget") => {
    if (!bridge?.pickCompareFile) return;
    const selected = await bridge.pickCompareFile(role);
    if (!selected?.ok || !selected.path) {
      if (selected?.error) setError(selected.error);
      return;
    }
    if (role === "final") {
      setFinalFilePath(selected.path);
    } else {
      setBudgetFilePath(selected.path);
    }
  };

  const startCompare = async () => {
    if (!bridge?.getComparePreview) return;
    if (!finalFilePath || !budgetFilePath) {
      setError("请先分别选择决算表和预算表文件。");
      return;
    }
    setChecking(true);
    setError("");
    try {
      const [finalResult, budgetResult] = await Promise.all([
        bridge.getComparePreview(finalFilePath),
        bridge.getComparePreview(budgetFilePath),
      ]);
      if (!finalResult?.ok || !finalResult.preview) {
        setError(finalResult?.error || "决算表解析失败");
        return;
      }
      if (!budgetResult?.ok || !budgetResult.preview) {
        setError(budgetResult?.error || "预算表解析失败");
        return;
      }
      setFinalPreview(finalResult.preview);
      setBudgetPreview(budgetResult.preview);
      setActiveSheet("");
    } finally {
      setChecking(false);
    }
  };

  const saveRuleTemplate = () => {
    const name = normalizeCell(ruleTemplateName);
    if (!name) {
      setError("模板名称不能为空。");
      return;
    }
    setError("");
    const now = new Date().toISOString();
    setRuleTemplates((prev) => {
      const existing = prev.find((item) => normalizeCell(item.name) === name);
      if (existing) {
        const next = prev.map((item) =>
          item.id === existing.id ? { ...item, config: { ...ruleConfig }, updatedAt: now, name } : item
        );
        setSelectedRuleTemplateId(existing.id);
        return next;
      }
      const id = `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
      const nextTemplate: RuleTemplate = {
        id,
        name,
        config: { ...ruleConfig },
        updatedAt: now,
      };
      setSelectedRuleTemplateId(id);
      return [nextTemplate, ...prev];
    });
  };

  const applySelectedRuleTemplate = () => {
    if (!selectedRuleTemplateId) return;
    const target = ruleTemplates.find((item) => item.id === selectedRuleTemplateId);
    if (!target) return;
    setRuleConfig({ ...DEFAULT_RULE_CONFIG, ...target.config });
    setRuleTemplateName(target.name);
  };

  const deleteSelectedRuleTemplate = () => {
    if (!selectedRuleTemplateId) return;
    setRuleTemplates((prev) => prev.filter((item) => item.id !== selectedRuleTemplateId));
    setSelectedRuleTemplateId("");
  };

  const resetRuleConfig = () => {
    setRuleConfig(DEFAULT_RULE_CONFIG);
    setRuleTemplateName("默认模板");
  };

  return (
    <div className="compare-window">
      <header className="compare-header">
        <div>
          <Title level={4}>决算表 vs 预算表可视化核对</Title>
          <Text type="secondary">支持从绑定目录选取，也支持上传单个文件；核对后自动高亮不匹配单元格。</Text>
        </div>
      </header>

      <Card size="small" className="compare-control-card">
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Space wrap>
            <Button onClick={() => void pickBoundDir()}>选择绑定目录</Button>
            <Button onClick={() => void loadBoundFiles()} loading={loadingFiles}>
              刷新目录文件
            </Button>
            <Text type="secondary">{boundDir || "未绑定目录"}</Text>
          </Space>
          <div className="compare-file-select-grid">
            <Card size="small" title="决算表">
              <Space direction="vertical" style={{ width: "100%" }}>
                <Select
                  showSearch
                  optionFilterProp="label"
                  placeholder="从绑定目录选择决算表"
                  value={finalFilePath || undefined}
                  options={fileOptions}
                  onChange={(value) => setFinalFilePath(value)}
                />
                <Button onClick={() => void pickUploadFile("final")}>上传决算表</Button>
              </Space>
            </Card>
            <Card size="small" title="预算表">
              <Space direction="vertical" style={{ width: "100%" }}>
                <Select
                  showSearch
                  optionFilterProp="label"
                  placeholder="从绑定目录选择预算表"
                  value={budgetFilePath || undefined}
                  options={fileOptions}
                  onChange={(value) => setBudgetFilePath(value)}
                />
                <Button onClick={() => void pickUploadFile("budget")}>上传预算表</Button>
              </Space>
            </Card>
          </div>
          <Space>
            <Button type="primary" onClick={() => void startCompare()} loading={checking}>
              开始核对流程
            </Button>
            {(compareMode === "excel" || compareMode === "doc") && (
              <Text>
                不匹配总数: <b>{totalMismatch}</b>
              </Text>
            )}
          </Space>
          {compareMode === "excel" && diffBySheet.length > 0 && (
            <Select
              style={{ maxWidth: 420 }}
              value={activeSheetDiff?.name}
              options={diffBySheet.map((item) => ({
                label: `${item.name}（不匹配 ${item.mismatchCount}）`,
                value: item.name,
              }))}
              onChange={(value) => setActiveSheet(String(value))}
            />
          )}
          {error && <Alert type="error" message={error} />}
          {(finalPreview || budgetPreview) && <Alert type="info" message={parseSummary} />}
        </Space>
      </Card>

      <Card size="small" className="compare-rule-card" title="核对规则配置">
        <div className="compare-rule-toolbar">
          <Input
            value={ruleTemplateName}
            onChange={(event) => setRuleTemplateName(event.target.value)}
            placeholder="输入模板名称"
            style={{ width: 220 }}
          />
          <Button onClick={saveRuleTemplate}>保存模板</Button>
          <Select
            placeholder="选择已保存模板"
            value={selectedRuleTemplateId || undefined}
            options={ruleTemplateOptions}
            onChange={(value) => setSelectedRuleTemplateId(String(value))}
            style={{ minWidth: 260 }}
          />
          <Button onClick={applySelectedRuleTemplate} disabled={!selectedRuleTemplateId}>
            应用模板
          </Button>
          <Button onClick={deleteSelectedRuleTemplate} disabled={!selectedRuleTemplateId}>
            删除模板
          </Button>
          <Button onClick={resetRuleConfig}>恢复默认</Button>
        </div>
        <div className="compare-rule-grid">
          <div className="compare-rule-item">
            <span>总额容差（元）</span>
            <InputNumber
              min={0}
              step={10}
              value={ruleConfig.amountTolerance}
              onChange={(value) =>
                setRuleConfig((prev) => ({ ...prev, amountTolerance: Math.max(0, Number(value) || 0) }))
              }
            />
          </div>
          <div className="compare-rule-item">
            <span>明细金额容差（元）</span>
            <InputNumber
              min={0}
              step={1}
              value={ruleConfig.lineItemAmountTolerance}
              onChange={(value) =>
                setRuleConfig((prev) => ({ ...prev, lineItemAmountTolerance: Math.max(0, Number(value) || 0) }))
              }
            />
          </div>
          <div className="compare-rule-item">
            <span>日期同月视为匹配</span>
            <Switch
              checked={ruleConfig.allowSameMonthForDate}
              onChange={(checked) => setRuleConfig((prev) => ({ ...prev, allowSameMonthForDate: checked }))}
            />
          </div>
          <div className="compare-rule-item">
            <span>报销人强制匹配</span>
            <Switch
              checked={ruleConfig.requireApplicantMatch}
              onChange={(checked) => setRuleConfig((prev) => ({ ...prev, requireApplicantMatch: checked }))}
            />
          </div>
          <div className="compare-rule-item">
            <span>部门强制匹配</span>
            <Switch
              checked={ruleConfig.requireDepartmentMatch}
              onChange={(checked) => setRuleConfig((prev) => ({ ...prev, requireDepartmentMatch: checked }))}
            />
          </div>
          <div className="compare-rule-item">
            <span>明细名称模糊匹配</span>
            <Switch
              checked={ruleConfig.enableFuzzyLineItemName}
              onChange={(checked) => setRuleConfig((prev) => ({ ...prev, enableFuzzyLineItemName: checked }))}
            />
          </div>
          <div className="compare-rule-item">
            <span>模糊匹配阈值</span>
            <InputNumber
              min={0.5}
              max={1}
              step={0.01}
              value={ruleConfig.fuzzyNameMinSimilarity}
              disabled={!ruleConfig.enableFuzzyLineItemName}
              onChange={(value) =>
                setRuleConfig((prev) => ({
                  ...prev,
                  fuzzyNameMinSimilarity: Math.max(0.5, Math.min(1, Number(value) || 0.72)),
                }))
              }
            />
          </div>
        </div>
      </Card>

      {processChecks.length > 0 && (
        <Card size="small" className="compare-process-card" title="报销流程逐项核对结果">
          <div className="compare-process-summary">
            <span className="matched">匹配 {checkStats.matched}</span>
            <span className="mismatch">不匹配 {checkStats.mismatch}</span>
            <span className="warning">待确认 {checkStats.warning}</span>
          </div>
          <div className="compare-process-list">
            {processChecks.map((item) => (
              <div key={item.key} className="compare-process-item">
                <div className="compare-process-title">
                  <span>{item.label}</span>
                  <span className={`compare-status compare-status-${item.status}`}>
                    {item.status === "matched" ? "匹配" : item.status === "mismatch" ? "不匹配" : "待确认"}
                  </span>
                </div>
                <div className="compare-process-rule">规则：{item.rule}</div>
                <div className="compare-process-values">
                  <span>预算：{item.budgetValue}</span>
                  <span>决算：{item.finalValue}</span>
                </div>
                <div className="compare-process-detail">{item.detail}</div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <div className="compare-panels">
        {checking ? (
          <div className="compare-loading">
            <Spin />
            <Text>正在解析并比对文件...</Text>
          </div>
        ) : compareMode === "unsupported" ? (
          <>
            <div className="compare-loading">
              <Text>当前仅支持同类型高亮比对：Excel 对 Excel，或 doc/docx 对 doc/docx。</Text>
              <Text type="secondary">已展示原始预览，可先人工核对内容。</Text>
            </div>
            {renderGenericPreview("决算表预览", finalPreview)}
            {renderGenericPreview("预算表预览", budgetPreview)}
          </>
        ) : compareMode === "doc" ? (
          <>
            {renderDocTable("决算表预览", finalPreview, docDiff)}
            {renderDocTable("预算表预览", budgetPreview, docDiff)}
          </>
        ) : (
          <>
            {renderSheetTable("决算表预览", finalPreview, activeSheetDiff)}
            {renderSheetTable("预算表预览", budgetPreview, activeSheetDiff)}
          </>
        )}
      </div>
    </div>
  );
}
