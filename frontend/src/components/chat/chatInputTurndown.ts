import TurndownService from "turndown";

/** Shared turndown instance — created once, reused on every paste. */
export const turndown = new TurndownService({
  headingStyle: "atx",
  hr: "---",
  bulletListMarker: "-",
  codeBlockStyle: "fenced",
  emDelimiter: "*",
  strongDelimiter: "**",
});

turndown.addRule("removeEmpty", {
  filter: (node: HTMLElement) => {
    return (
      (node.nodeName === "A" || node.nodeName === "SPAN") &&
      !node.textContent?.trim()
    );
  },
  replacement: () => "",
});

turndown.addRule("table", {
  filter: "table",
  replacement: (_content: string, node: HTMLElement) => {
    const table = node as HTMLTableElement;
    const rows: string[][] = [];
    table.querySelectorAll("tr").forEach((tr) => {
      const cells: string[] = [];
      tr.querySelectorAll("th, td").forEach((cell) => {
        cells.push(
          turndown.turndown(cell.innerHTML).trim().replace(/\n/g, " "),
        );
      });
      rows.push(cells);
    });
    if (rows.length === 0) return "";

    const colCount = Math.max(...rows.map((r) => r.length));
    const normalized = rows.map((r) =>
      r.length < colCount ? [...r, ...Array(colCount - r.length).fill("")] : r,
    );

    const colWidths = Array(colCount).fill(0);
    normalized.forEach((row) =>
      row.forEach((cell, i) => {
        colWidths[i] = Math.max(colWidths[i], cell.length);
      }),
    );

    const pad = (s: string, w: number) =>
      s + " ".repeat(Math.max(0, w - s.length));
    const padRight = (s: string, w: number) =>
      s.length > w ? s.substring(0, w - 1) + "…" : pad(s, w);

    let md = "";
    normalized.forEach((row, ri) => {
      md +=
        "| " +
        row.map((c, ci) => padRight(c, colWidths[ci])).join(" | ") +
        " |\n";
      if (ri === 0) {
        md += "| " + colWidths.map((w) => "-".repeat(w)).join(" | ") + " |\n";
      }
    });
    return md.trim() ? "\n\n" + md + "\n" : "";
  },
});

turndown.addRule("fencedCodeBlock", {
  filter: (node: HTMLElement): boolean => {
    return !!(
      node.nodeName === "PRE" &&
      node.firstChild &&
      (node.firstChild as HTMLElement).nodeName === "CODE"
    );
  },
  replacement: (_content: string, node: HTMLElement) => {
    const codeEl = node.firstChild as HTMLElement;
    const className = codeEl.className || "";
    const langMatch = className.match(/(?:language-|lang-|hljs\s+)(\w+)/);
    const lang = langMatch ? langMatch[1] : "";
    const code = codeEl.textContent || "";
    return "\n\n```" + lang + "\n" + code.replace(/\n$/, "") + "\n```\n\n";
  },
});

export function cleanPastedHtml(div: HTMLDivElement) {
  div
    .querySelectorAll("meta, style, script, title, link")
    .forEach((el) => el.remove());

  div.querySelectorAll("p, div").forEach((el) => {
    if (!el.textContent?.trim() && !el.querySelector("img")) {
      el.remove();
    }
  });

  div.querySelectorAll("*").forEach((el) => {
    el.removeAttribute("class");
    el.removeAttribute("id");
    el.removeAttribute("style");
    el.removeAttribute("data-");
  });

  div.querySelectorAll("div, section").forEach((el) => {
    const parent = el.parentNode;
    if (!parent) return;
    while (el.firstChild) {
      parent.insertBefore(el.firstChild, el);
    }
    parent.removeChild(el);
  });

  div.querySelectorAll("li br").forEach((br) => {
    br.replaceWith(document.createTextNode("\n"));
  });
}
