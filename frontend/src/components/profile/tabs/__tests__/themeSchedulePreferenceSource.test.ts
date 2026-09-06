import { readFileSync } from "node:fs";

const tabSource = readFileSync(
  new URL("../ProfilePreferencesTab.tsx", import.meta.url),
  "utf8",
);

test("profile preferences tab wires the scheduled theme toggle to the theme context", () => {
  // 配置状态与写入走 ThemeContext（localStorage 镜像 + 后端同步由 Provider 统一负责）
  expect(tabSource).toMatch(/const \{ theme, setTheme, schedule, setSchedule \} = useTheme\(\)/);
  // 开关语义：enabled 翻转，其余字段沿用现值或默认值
  expect(tabSource).toMatch(/setSchedule\(\{ \.\.\./);
  // 时间选择用原生 time 输入
  expect(tabSource).toMatch(/type="time"/);
  // 清空/非法时间不落盘（否则 parseThemeSchedule 会静默丢弃整个偏好）
  expect(tabSource).toMatch(/HHMM\.test\(value\)/);
  // 夜间主题二选一（暗色/护眼），复用既有主题文案
  expect(tabSource).toMatch(/themeScheduleNightTheme/);
  // 开关可访问性
  expect(tabSource).toMatch(/role="switch"/);
});
