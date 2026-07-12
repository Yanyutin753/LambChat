import * as XLSX from "xlsx";
import { worksheetToDisplayRows } from "../excelPreviewData.ts";

test("uses formatted worksheet text for date cells", () => {
  const worksheet = XLSX.utils.aoa_to_sheet([["month"], [46143.33383101852]]);
  worksheet.A2.z = "mmm-yy";

  const rows = worksheetToDisplayRows(worksheet, XLSX.utils);

  expect(rows).toEqual([["month"], ["May-26"]]);
});
