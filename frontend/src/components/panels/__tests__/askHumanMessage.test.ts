import { parseAskHumanMessage } from "../askHumanMessage";

test("parses sandbox confirm batch into headline and op rows", () => {
  const parsed = parseAskHumanMessage(
    "确认在本机执行 2 项操作：\n" +
      "1. 执行命令：rm ~/下载/数据文件/a.json && echo 已删除; ls -A ~/下载\n" +
      "2. 写入文件：/tmp/out.txt",
  );
  expect(parsed.headline).toBe("确认在本机执行 2 项操作");
  expect(parsed.ops).toEqual([
    {
      verb: "执行命令",
      detail: "rm ~/下载/数据文件/a.json && echo 已删除; ls -A ~/下载",
    },
    { verb: "写入文件", detail: "/tmp/out.txt" },
  ]);
  expect(parsed.prose).toBeNull();
});

test("keeps an op without a CJK verb prefix detail-only", () => {
  const parsed = parseAskHumanMessage(
    "确认在本机执行 1 项操作：\n1. 上传 3 个文件",
  );
  expect(parsed.ops).toEqual([{ verb: null, detail: "上传 3 个文件" }]);
});

test("does not treat colons inside the command as the verb separator", () => {
  const parsed = parseAskHumanMessage(
    '确认在本机执行 1 项操作：\n1. 执行命令：echo "time: 10" && echo a：b',
  );
  expect(parsed.ops?.[0].verb).toBe("执行命令");
  expect(parsed.ops?.[0].detail).toBe('echo "time: 10" && echo a：b');
});

test("does not treat an ascii-colon command prefix as a CJK verb", () => {
  const parsed = parseAskHumanMessage(
    "确认在本机执行 1 项操作：\n1. rm：-rf /tmp/x",
  );
  expect(parsed.ops?.[0].verb).toBeNull();
  expect(parsed.ops?.[0].detail).toBe("rm：-rf /tmp/x");
});

test("plain multi-line question falls back to headline plus prose", () => {
  const parsed = parseAskHumanMessage("接下来怎么做？\n请选择一个方案继续。");
  expect(parsed.headline).toBe("接下来怎么做？");
  expect(parsed.ops).toBeNull();
  expect(parsed.prose).toBe("请选择一个方案继续。");
});

test("single-line question returns headline only", () => {
  const parsed = parseAskHumanMessage("要继续吗？");
  expect(parsed.headline).toBe("要继续吗？");
  expect(parsed.ops).toBeNull();
  expect(parsed.prose).toBeNull();
});

test("mixed numbered and unnumbered lines are not forced into op rows", () => {
  const parsed = parseAskHumanMessage(
    "确认执行：\n1. 执行命令：ls\n注意：以上操作不可撤销",
  );
  expect(parsed.ops).toBeNull();
  expect(parsed.prose).toBe("1. 执行命令：ls\n注意：以上操作不可撤销");
});

test("empty message yields no headline", () => {
  const parsed = parseAskHumanMessage("");
  expect(parsed.headline).toBeNull();
  expect(parsed.ops).toBeNull();
  expect(parsed.prose).toBeNull();
});

test("collapses to a single-line summary for pill labels", () => {
  const summary = parseAskHumanMessage(
    "确认在本机执行 1 项操作：\n1. 执行命令：rm -rf /tmp",
  ).summary;
  expect(summary).toBe("确认在本机执行 1 项操作： 1. 执行命令：rm -rf /tmp");
});
